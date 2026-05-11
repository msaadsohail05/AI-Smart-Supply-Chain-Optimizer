import os
from typing import Dict, List, Optional, Tuple

from services.ga_service import ROUTES, VEHICLES

WAREHOUSE_NAME = os.getenv("WAREHOUSE_NAME", "Central Warehouse Karachi")


def validate(
    plan: List[List[str]],
    deliveries: Dict[str, int],
    vehicle_plan: List[str],
    route_plan: List[str],
    deadlines: Optional[Dict[str, str]] = None,
    distance_lookup: Optional[Dict[Tuple[str, str], float]] = None,
    start_time: int = 0,
    depot: str = WAREHOUSE_NAME,
) -> bool:
    if len(vehicle_plan) != len(plan) or len(route_plan) != len(plan):
        return False

    required = set(deliveries.keys())
    assigned = []

    for index, route in enumerate(plan):
        if not route:
            continue

        vehicle_type = vehicle_plan[index]
        route_type = route_plan[index]
        vehicle_meta = VEHICLES.get(vehicle_type)
        route_meta = ROUTES.get(route_type)
        if not vehicle_meta or not route_meta:
            return False

        capacity = vehicle_meta["capacity"]
        speed = vehicle_meta["speed"]
        factor = route_meta["factor"]

        total = 0
        current_time = start_time
        current_node = depot
        for loc in route:
            if loc not in deliveries:
                return False
            total += deliveries[loc]
            assigned.append(loc)

            if deadlines is not None:
                if distance_lookup is None:
                    return False

                distance = distance_lookup.get((current_node, loc))
                if distance is None:
                    return False

                current_time += (distance / speed) * 60 * factor
                deadline_value = deadlines.get(loc)
                if deadline_value is None:
                    return False

                deadline_minutes = _deadline_to_minutes(deadline_value)
                if deadline_minutes is None:
                    return False

                if current_time > deadline_minutes:
                    return False

                current_node = loc

        if total > capacity:
            return False

    if set(assigned) != required:
        return False

    if len(assigned) != len(set(assigned)):
        return False

    return True


def _deadline_to_minutes(value: str) -> Optional[int]:
    value = value.strip()
    if value.isdigit():
        return int(value)

    if ":" not in value:
        return None

    parts = value.split(":")
    if len(parts) != 2:
        return None

    hour_part, minute_part = parts
    if not hour_part.isdigit() or not minute_part.isdigit():
        return None

    hour = int(hour_part)
    minute = int(minute_part)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    return hour * 60 + minute
