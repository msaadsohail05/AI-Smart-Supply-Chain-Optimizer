import os
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from pymongo import MongoClient
from pydantic import BaseModel

from services.astar_service import astar
from services.csp_service import validate
from services.ga_service import (
    genetic_algorithm,
    normalize_route_type,
    normalize_vehicle_type,
)
from services.graph_service import build_graph
from services.llm_service import parse_input, summarize_plan
from services.map_api_service import fetch_graph

load_dotenv()

WAREHOUSE_NAME = os.getenv("WAREHOUSE_NAME", "Central Warehouse Karachi")

app = FastAPI()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "ai_supply_chain")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "delivery_inputs")

_mongo_client = MongoClient(MONGO_URI) if MONGO_URI else None
_collection = (
    _mongo_client[MONGO_DB][MONGO_COLLECTION] if _mongo_client else None
)


class UserInput(BaseModel):
    text: str


class ProcessRequest(BaseModel):
    coordinates: Optional[Dict[str, Tuple[Optional[float], Optional[float]]]] = None
    cost_per_km: float = 10
    provider: str = "openrouteservice"
    profile: str = "driving-car"
    api_key: Optional[str] = None
    num_vehicles: int = 3
    vehicle_capacity: int = 10
    use_astar_for_costs: bool = True


class RouteRequest(BaseModel):
    start: str
    goal: str
    coordinates: Dict[str, Tuple[float, float]]

#backend test code
@app.get("/")
def root():
    return {"status": "ok"}

#saad's code
@app.post("/test-llm")
def test_llm(data: UserInput):
    try:
        result = parse_input(
            data.text,
            use_llm=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    return {
        "success": True,
        "result": result
    }

#posting parsed LLM inputs to MongoDB and listing them back
@app.post("/llm-inputs")
def add_llm_input(data: UserInput):
    collection = _get_collection()
    try:
        parsed = parse_input(data.text, use_llm=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    payload = dict(parsed)
    result = collection.insert_one(payload)
    return {
        "success": True,
        "id": str(result.inserted_id),
        "parsed": parsed,
    }

#displaying all parsed LLM inputs from MongoDB
@app.get("/llm-inputs")
def list_llm_inputs():
    collection = _get_collection()
    items = [_serialize_doc(doc) for doc in collection.find({})]
    return {"items": items}

#processing all parsed LLM inputs from MongoDB to build a graph
@app.get("/llm-process")
def process_llm_inputs():
    pipeline = _run_llm_pipeline(ProcessRequest())
    summary_payload = {
        "inputs": pipeline["inputs"],
        "deliveries": pipeline["deliveries"],
        "deadlines": pipeline["deadlines"],
        "plan": pipeline["plan"],
        "valid": pipeline["valid"],
    }
    try:
        summary = summarize_plan(summary_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    return {"summary": summary}

#delete all parsed LLM inputs from MongoDB
@app.delete("/llm-inputs")
def clear_llm_inputs():
    collection = _get_collection()
    result = collection.delete_many({})
    return {"deleted": result.deleted_count}


@app.post("/route")
def route(request: RouteRequest):
    graph = fetch_graph(
        [request.start, request.goal],
        {
            "provider": "openrouteservice",
            "coordinates": request.coordinates,
        },
    )

    return astar(graph, request.start, request.goal, coordinates=request.coordinates)


def _deliveries_from_extraction(extracted: Dict[str, object]) -> Dict[str, int]:
    destinations = extracted.get("destinations") or []
    packages = extracted.get("packages")
    if not destinations:
        return {}

    if isinstance(packages, int) and packages > 0:
        # Even split for per-location delivery counts.
        base = packages // len(destinations)
        remainder = packages % len(destinations)
        deliveries = {}
        for index, destination in enumerate(destinations):
            deliveries[destination] = base + (1 if index < remainder else 0)
        return deliveries

    return {destination: 1 for destination in destinations}


def _deliveries_from_inputs(items: List[Dict[str, object]]) -> Dict[str, int]:
    merged: Dict[str, int] = {}
    for item in items:
        deliveries = _deliveries_from_extraction(item)
        for destination, count in deliveries.items():
            merged[destination] = merged.get(destination, 0) + count
    return merged


def _deadlines_from_inputs(
    items: List[Dict[str, object]],
    deliveries: Dict[str, int],
) -> Dict[str, str]:
    deadlines: Dict[str, str] = {}
    for item in items:
        deadline_value = item.get("deadline") if isinstance(item, dict) else None
        destinations = item.get("destinations") if isinstance(item, dict) else None
        if not deadline_value or not isinstance(destinations, list):
            continue
        for destination in destinations:
            if destination in deliveries and destination not in deadlines:
                deadlines[destination] = str(deadline_value)
    return deadlines


def _build_lookup_tables(graph: Dict[str, Dict[str, Dict[str, float]]]):
    distance_lookup: Dict[Tuple[str, str], float] = {}
    time_lookup: Dict[Tuple[str, str], float] = {}

    for origin, neighbors in graph.items():
        for destination, metrics in neighbors.items():
            distance_lookup[(origin, destination)] = metrics.get("distance", 0)
            time_lookup[(origin, destination)] = metrics.get("time", 0)

    return distance_lookup, time_lookup


def _build_astar_distances(
    graph: Dict[str, Dict[str, Dict[str, float]]],
    coordinates: Optional[Dict[str, Tuple[float, float]]],
    destinations,
):
    distance_lookup: Dict[Tuple[str, str], float] = {}
    nodes = [WAREHOUSE_NAME] + list(destinations)

    for origin in nodes:
        for destination in nodes:
            if origin == destination:
                continue
            result = astar(graph, origin, destination, coordinates)
            total_distance = result.get("total_distance") if isinstance(result, dict) else None
            if total_distance is not None:
                distance_lookup[(origin, destination)] = total_distance

    return distance_lookup


def _sanitize_coordinates(
    coordinates: Optional[Dict[str, Tuple[Optional[float], Optional[float]]]]
) -> Optional[Dict[str, Tuple[float, float]]]:
    if not coordinates:
        return None

    cleaned: Dict[str, Tuple[float, float]] = {}
    for key, value in coordinates.items():
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            continue
        lat, lon = value
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            cleaned[str(key)] = (float(lat), float(lon))

    return cleaned or None


def _run_llm_pipeline(request: ProcessRequest) -> Dict[str, object]:
    collection = _get_collection()
    docs = list(collection.find({}))
    if not docs:
        return {"error": "no_inputs"}

    payloads = [_strip_id(doc) for doc in docs]
    deliveries = _deliveries_from_inputs(payloads)
    if not deliveries:
        return {"error": "no_deliveries"}

    deadlines = _deadlines_from_inputs(payloads, deliveries)

    locations = [WAREHOUSE_NAME] + list(deliveries.keys())

    coordinates = _sanitize_coordinates(request.coordinates)

    provider_config = {
        "provider": request.provider,
        "coordinates": coordinates,
        "cost_per_km": request.cost_per_km,
        "profile": request.profile,
    }
    if request.api_key:
        provider_config["api_key"] = request.api_key

    graph = build_graph(locations, provider_config)
    distance_lookup, time_lookup = _build_lookup_tables(graph)

    if request.use_astar_for_costs:
        distance_lookup = _build_astar_distances(
            graph,
            coordinates,
            deliveries.keys(),
        )

    budget, time_limit, priority, constraints, fixed_vehicle, fixed_route = _plan_inputs(
        payloads
    )

    ga_attempts = int(os.getenv("GA_ATTEMPTS", "5"))
    candidates = []
    for _ in range(max(1, ga_attempts)):
        candidate = genetic_algorithm(
            deliveries=deliveries,
            distance_lookup=distance_lookup,
            num_vehicles=request.num_vehicles,
            budget=budget,
            time_limit=time_limit,
            priority=priority,
            constraints=constraints,
            fixed_vehicle=fixed_vehicle,
            fixed_route=fixed_route,
        )
        is_valid = validate(
            candidate["best_plan"],
            deliveries,
            candidate["vehicle_plan"],
            candidate["route_plan"],
            deadlines=deadlines or None,
            distance_lookup=distance_lookup if deadlines else None,
        )
        candidates.append((candidate, is_valid))

    valid_candidates = [item for item in candidates if item[1]]
    if valid_candidates:
        result, is_valid = min(
            valid_candidates,
            key=lambda item: item[0].get("fitness_score", float("inf")),
        )
    else:
        result, is_valid = min(
            candidates,
            key=lambda item: item[0].get("fitness_score", float("inf")),
        )

    return {
        "inputs": payloads,
        "deliveries": deliveries,
        "deadlines": deadlines,
        "plan": result,
        "valid": is_valid,
        "graph": graph,
    }


def _plan_inputs(items: List[Dict[str, object]]):
    budgets = _collect_numbers(items, ["budget"])
    time_limits = _collect_numbers(items, ["time_hrs", "time_limit"])
    priority = _priority_from_inputs(items)
    constraints = _constraints_from_inputs(items)
    fixed_vehicle = _fixed_vehicle_from_inputs(items)
    fixed_route = _fixed_route_from_inputs(items)

    budget = min(budgets) if budgets else None
    time_limit = min(time_limits) if time_limits else None
    return budget, time_limit, priority, constraints, fixed_vehicle, fixed_route


def _collect_numbers(items: List[Dict[str, object]], keys: List[str]) -> List[float]:
    values: List[float] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = item.get(key)
            if isinstance(value, (int, float)):
                values.append(float(value))
    return values


def _priority_from_inputs(items: List[Dict[str, object]]) -> str:
    for item in items:
        if not isinstance(item, dict):
            continue
        objective = item.get("objective")
        if isinstance(objective, str) and "time" in objective.lower():
            return "time"
    return "cost"


def _constraints_from_inputs(items: List[Dict[str, object]]) -> List[str]:
    merged: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("constraints", "extra_constraints"):
            value = item.get(key)
            if isinstance(value, list):
                for entry in value:
                    if isinstance(entry, str):
                        merged.append(entry)
    return merged


def _fixed_vehicle_from_inputs(items: List[Dict[str, object]]) -> Optional[str]:
    for item in items:
        if not isinstance(item, dict):
            continue
        vehicle_type = item.get("vehicle_type")
        if isinstance(vehicle_type, str):
            normalized = normalize_vehicle_type(vehicle_type)
            if normalized:
                return normalized
    return None


def _fixed_route_from_inputs(items: List[Dict[str, object]]) -> Optional[str]:
    for item in items:
        if not isinstance(item, dict):
            continue
        route_type = item.get("route") or item.get("route_type")
        if isinstance(route_type, str):
            normalized = normalize_route_type(route_type)
            if normalized:
                return normalized
    return None


def _get_collection():
    if _collection is None:
        raise HTTPException(status_code=500, detail="MongoDB is not configured")
    return _collection


def _serialize_doc(doc: Dict[str, object]) -> Dict[str, object]:
    payload = dict(doc)
    if "_id" in payload:
        payload["_id"] = str(payload["_id"])
    return payload


def _strip_id(doc: Dict[str, object]) -> Dict[str, object]:
    payload = dict(doc)
    payload.pop("_id", None)
    return payload


def _locations_from_inputs(items: List[Dict[str, object]]) -> List[str]:
    locations: List[str] = []
    seen = set()
    has_source = False

    for item in items:
        source = item.get("source") if isinstance(item, dict) else None
        if isinstance(source, str) and source:
            has_source = True
            if source not in seen:
                seen.add(source)
                locations.append(source)

        destinations = item.get("destinations") if isinstance(item, dict) else None
        if isinstance(destinations, list):
            for destination in destinations:
                if isinstance(destination, str) and destination:
                    if destination not in seen:
                        seen.add(destination)
                        locations.append(destination)

    if not has_source and locations:
        if WAREHOUSE_NAME not in seen:
            locations.insert(0, WAREHOUSE_NAME)

    return locations
