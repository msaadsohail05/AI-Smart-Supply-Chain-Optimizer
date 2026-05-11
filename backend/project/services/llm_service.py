"""Service for fetching real-world map data using OpenRouteService."""

import json
import os
import urllib.parse
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
    if not coordinates:
        coordinates = _geocode_locations(locations, api_key)

    coords_list = []
    for name in locations:
        if name not in coordinates:
            raise ValueError(f"Missing coordinates for {name}")
        coords_list.append(list(coordinates[name]))

    graph = {}
    for i, origin in enumerate(locations):
        for j, destination in enumerate(locations):
            if i == j:
                continue

            start = coordinates[origin]
            end = coordinates[destination]
            summary = _fetch_directions_summary(start, end, api_key, profile)
            if not summary:
                continue

            distance_km = summary["distance_km"]
            duration_min = summary["duration_min"]

            graph.setdefault(origin, {})[destination] = {
                "distance": distance_km,
                "time": duration_min,
                "cost": distance_km * cost_per_km,
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


def _get_json(url, api_key):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        method="GET",
    )

    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _geocode_locations(locations, api_key):
    coordinates = {}
    for name in locations:
        coordinates[name] = _geocode_location(name, api_key)
    return coordinates


def _geocode_location(name, api_key):
    query = urllib.parse.quote(name)
    url = f"{ORS_BASE_URL}/geocode/search?api_key={api_key}&text={query}"
    response_data = _get_json(url, api_key)
    features = response_data.get("features") or []
    if not features:
        raise ValueError(f"No geocode results for {name}")

    coords = features[0].get("geometry", {}).get("coordinates")
    if not coords or len(coords) < 2:
        raise ValueError(f"Invalid geocode response for {name}")

    return (coords[0], coords[1])


def _fetch_directions_summary(start, end, api_key, profile):
    if not start or not end:
        return None

    start_param = f"{start[0]},{start[1]}"
    end_param = f"{end[0]},{end[1]}"
    url = (
        f"{ORS_BASE_URL}/v2/directions/{profile}"
        f"?api_key={api_key}&start={start_param}&end={end_param}"
    )
    response_data = _get_json(url, api_key)
    features = response_data.get("features") or []
    if not features:
        return None

    summary = features[0].get("properties", {}).get("summary") or {}
    distance_m = summary.get("distance")
    duration_s = summary.get("duration")
    if distance_m is None or duration_s is None:
        return None

    return {
        "distance_km": distance_m / 1000,
        "duration_min": duration_s / 60,
    }
