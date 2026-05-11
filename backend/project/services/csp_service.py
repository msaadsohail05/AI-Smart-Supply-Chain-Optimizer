import os

from .map_api_service import fetch_graph

WAREHOUSE_NAME = os.getenv("WAREHOUSE_NAME", "Central Warehouse Karachi")


EXAMPLE_GRAPH = {
    WAREHOUSE_NAME: {
        "DHA": {"distance": 20, "time": 30, "cost": 200},
        "Clifton": {"distance": 18, "time": 25, "cost": 180},
    },
    "DHA": {
        "Clifton": {"distance": 5, "time": 10, "cost": 50},
        "Korangi": {"distance": 12, "time": 20, "cost": 120},
    },
    "Clifton": {
        "Saddar": {"distance": 8, "time": 12, "cost": 80},
    },
}


def build_graph(locations, provider_config=None):
    return fetch_graph(locations, provider_config)
