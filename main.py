from typing import Dict, List, Optional, Tuple

from fastapi import Body, FastAPI
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from services.astar_service import astar
from services.csp_service import validate
from services.ga_service import genetic_algorithm
from services.llm_service import parse_input
from services.map_api_service import fetch_graph

load_dotenv()

app = FastAPI()


class OptimizeRequest(BaseModel):
    text: Optional[str] = None
    deliveries: Dict[str, int] = Field(default_factory=dict)
    deadlines: Dict[str, str] = Field(default_factory=dict)
    num_vehicles: int = 3
    vehicle_capacity: int = 10
    coordinates: Dict[str, Tuple[float, float]] = Field(default_factory=dict)
    cost_per_km: float = 10
    use_llm: bool = True
    use_astar_for_costs: bool = False


class RouteRequest(BaseModel):
    start: str
    goal: str
    coordinates: Dict[str, Tuple[float, float]]


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/extract")
def extract_constraints(request: OptimizeRequest):
    return parse_input({"text": request.text or ""}, use_llm=request.use_llm)


@app.post("/text")
def parse_text(text: str = Body(..., embed=True), use_llm: bool = True):
    return parse_input({"text": text}, use_llm=use_llm)


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


@app.post("/optimize")
def optimize(request: OptimizeRequest):
    extracted = {}
    if request.text:
        extracted = parse_input({"text": request.text}, use_llm=request.use_llm)

    deliveries = dict(request.deliveries)
    if not deliveries:
        deliveries = _deliveries_from_extraction(extracted)

    if not deliveries:
        return {"error": "no_deliveries"}

    deadlines = dict(request.deadlines)
    if not deadlines and extracted.get("deadline"):
        deadline_value = extracted.get("deadline")
        deadlines = {destination: deadline_value for destination in deliveries.keys()}

    locations = ["Warehouse"] + list(deliveries.keys())

    graph = fetch_graph(
        locations,
        {
            "provider": "openrouteservice",
            "coordinates": request.coordinates,
            "cost_per_km": request.cost_per_km,
        },
    )

    cost_lookup, time_lookup = _build_lookup_tables(graph)

    if request.use_astar_for_costs:
        cost_lookup = _build_astar_costs(graph, request.coordinates, deliveries.keys())

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
        "extracted": extracted,
        "deliveries": deliveries,
        "plan": result,
        "valid": is_valid,
    }


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
