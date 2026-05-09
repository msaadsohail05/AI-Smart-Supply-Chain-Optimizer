# AI Supply Chain Manager

End-to-end pipeline for extracting delivery constraints, building a weighted graph from real-world routes, and optimizing multi-vehicle delivery plans.

## Pipeline Overview
- LLM parses user text into structured constraints
- OpenRouteService returns real-world distance/time metrics
- Graph uses weighted adjacency dictionaries
- A* computes optimal path costs
- GA assigns deliveries to vehicles and sequences routes
- CSP validates capacity and deadlines

## Environment Variables
- OPENAI_API_KEY
- OPENROUTESERVICE_API_KEY
- OPENAI_MODEL (optional, default: gpt-4o-mini)

Create a `.env` file at the repo root (see `.env.example`) and populate the keys.

## Backend Setup
```
pip install -r backend/requirements.txt
```

## Graph Format
```
graph = {
    "Warehouse": {
        "DHA": {"distance": 20, "time": 30, "cost": 200},
        "Clifton": {"distance": 18, "time": 25, "cost": 180}
    }
}
```

## Coordinates Format
```
coordinates = {
    "Warehouse": (0, 0),
    "DHA": (5, 8),
    "Clifton": (4, 5)
}
```

## Quick Usage
```
from backend.project.services.llm_service import parse_input
from backend.project.services.map_api_service import fetch_graph
from backend.project.services.astar_service import astar
from backend.project.services.ga_service import genetic_algorithm
from backend.project.services.csp_service import validate

text = "Deliver from Warehouse to DHA and Clifton before 4 PM"
request = parse_input(text)

locations = ["Warehouse"] + request["destinations"]
coordinates = {
    "Warehouse": (0, 0),
    "DHA": (5, 8),
    "Clifton": (4, 5)
}

graph = fetch_graph(
    locations,
    {
        "provider": "openrouteservice",
        "coordinates": coordinates,
        "cost_per_km": 10,
    },
)

# Build cost lookup from graph edges
cost_lookup = {
    (origin, destination): metrics["cost"]
    for origin, neighbors in graph.items()
    for destination, metrics in neighbors.items()
}

plan = genetic_algorithm(
    deliveries={"DHA": 5, "Clifton": 3},
    cost_lookup=cost_lookup,
    num_vehicles=2,
)

# Deadline validation example (minutes from 00:00)
valid = validate(
    plan["best_plan"],
    deliveries={"DHA": 5, "Clifton": 3},
    capacity=10,
    deadlines={"DHA": "16:00", "Clifton": "17:00"},
    time_lookup={("Warehouse", "DHA"): 30, ("DHA", "Clifton"): 15},
)
```

## Notes
- The GA treats each location as a single delivery (with package count).
- CSP validates capacity and optional deadlines when provided.
- A* optimizes by cost and returns distance/time totals.
