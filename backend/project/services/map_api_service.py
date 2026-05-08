"""Service for fetching real-world map data using OpenRouteService."""

import json
import os
import urllib.request


ORS_BASE_URL = "https://api.openrouteservice.org"


def fetch_route_costs(locations, provider_config=None):
    graph = fetch_graph(locations, provider_config)
    costs = {}
    for origin, neighbors in graph.items():
        for destination, metrics in neighbors.items():
            costs[(origin, destination)] = metrics.get("cost")
    return costs


def fetch_graph(locations, provider_config=None):
    provider_config = provider_config or {}
    provider = provider_config.get("provider", "openrouteservice")
    if provider != "openrouteservice":
        raise ValueError("Unsupported provider")

    api_key = provider_config.get("api_key") or os.getenv("OPENROUTESERVICE_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTESERVICE_API_KEY is not set")

    coordinates = provider_config.get("coordinates")
    if not coordinates:
        raise ValueError("coordinates are required for OpenRouteService")

    if not locations:
        locations = list(coordinates.keys())

    profile = provider_config.get("profile", "driving-car")
    cost_per_km = provider_config.get("cost_per_km", 10)

    return _fetch_graph_openrouteservice(
        locations=locations,
        coordinates=coordinates,
        api_key=api_key,
        profile=profile,
        cost_per_km=cost_per_km,
    )


def _fetch_graph_openrouteservice(locations, coordinates, api_key, profile, cost_per_km):
    coords_list = []
    for name in locations:
        if name not in coordinates:
            raise ValueError(f"Missing coordinates for {name}")
        coords_list.append(list(coordinates[name]))

    payload = {
        "locations": coords_list,
        "metrics": ["distance", "duration"],
        "units": "km",
    }

    url = f"{ORS_BASE_URL}/v2/matrix/{profile}"
    response_data = _post_json(url, payload, api_key)
    distances = response_data.get("distances") or []
    durations = response_data.get("durations") or []

    graph = {}
    for i, origin in enumerate(locations):
        for j, destination in enumerate(locations):
            if i == j:
                continue

            try:
                distance = distances[i][j]
                duration = durations[i][j]
            except (IndexError, TypeError):
                continue

            if distance is None or duration is None:
                continue

            graph.setdefault(origin, {})[destination] = {
                "distance": distance,
                "time": duration / 60,
                "cost": distance * cost_per_km,
            }

    return graph


def _post_json(url, payload, api_key):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))
