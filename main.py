import os
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from pymongo import MongoClient
from pydantic import BaseModel

from services.astar_service import astar
from services.csp_service import validate
from services.ga_service import genetic_algorithm
from services.graph_service import build_graph
from services.llm_service import parse_input
from services.map_api_service import fetch_graph

load_dotenv()

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
    coordinates: Optional[Dict[str, Tuple[float, float]]] = None
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

    result = collection.insert_one(parsed)
    return {"success": True, "id": str(result.inserted_id),"parsed" : parsed}

#displaying all parsed LLM inputs from MongoDB
@app.get("/llm-inputs")
def list_llm_inputs():
    collection = _get_collection()
    items = [_serialize_doc(doc) for doc in collection.find({})]
    return {"items": items}

#processing all parsed LLM inputs from MongoDB to build a graph
@app.post("/llm-process")
def process_llm_inputs(request: ProcessRequest):
    collection = _get_collection()
    docs = list(collection.find({}))
    if not docs:
        return {"error": "no_inputs"}

    payloads = [_strip_id(doc) for doc in docs]
    deliveries = _deliveries_from_inputs(payloads)
    if not deliveries:
        return {"error": "no_deliveries"}

    deadlines = _deadlines_from_inputs(payloads, deliveries)

    locations = ["Warehouse"] + list(deliveries.keys())

    provider_config = {
        "provider": request.provider,
        "coordinates": request.coordinates,
        "cost_per_km": request.cost_per_km,
        "profile": request.profile,
    }
    if request.api_key:
        provider_config["api_key"] = request.api_key

    graph = build_graph(locations, provider_config)
    cost_lookup, time_lookup = _build_lookup_tables(graph)

    if request.use_astar_for_costs:
        cost_lookup = _build_astar_costs(
            graph,
            request.coordinates,
            deliveries.keys(),
        )

    result = genetic_algorithm(
        deliveries=deliveries,
        cost_lookup=cost_lookup,
        num_vehicles=request.num_vehicles,
    )

    is_valid = validate(
        result["best_plan"],
        deliveries,
        request.vehicle_capacity,
        deadlines=deadlines or None,
        time_lookup=time_lookup if deadlines else None,
    )

    return {
        "inputs": payloads,
        "deliveries": deliveries,
        "deadlines": deadlines,
        "plan": result,
        "valid": is_valid,
        "graph": graph,
    }

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
    cost_lookup: Dict[Tuple[str, str], float] = {}
    time_lookup: Dict[Tuple[str, str], float] = {}

    for origin, neighbors in graph.items():
        for destination, metrics in neighbors.items():
            cost_lookup[(origin, destination)] = metrics.get("cost", 0)
            time_lookup[(origin, destination)] = metrics.get("time", 0)

    return cost_lookup, time_lookup


def _build_astar_costs(
    graph: Dict[str, Dict[str, Dict[str, float]]],
    coordinates: Dict[str, Tuple[float, float]],
    destinations,
):
    cost_lookup: Dict[Tuple[str, str], float] = {}
    nodes = ["Warehouse"] + list(destinations)

    for origin in nodes:
        for destination in nodes:
            if origin == destination:
                continue
            result = astar(graph, origin, destination, coordinates)
            total_cost = result.get("total_cost") if isinstance(result, dict) else None
            if total_cost is not None:
                cost_lookup[(origin, destination)] = total_cost

    return cost_lookup


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
        if "Warehouse" not in seen:
            locations.insert(0, "Warehouse")

    return locations
