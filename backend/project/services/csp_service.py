import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime


WAREHOUSE_NAME = os.getenv("WAREHOUSE_NAME", "Central Warehouse Karachi")


def validate(
    plan: List[List[str]],
    deliveries: Dict[str, int],
    vehicle_plan: List[str],
    route_plan: List[str],
    deadlines: Optional[Dict[str, str]] = None,
    distance_lookup: Optional[Dict[Tuple[str, str], float]] = None,
    time_lookup: Optional[Dict[Tuple[str, str], float]] = None,
    depot: str = None,
    verbose: bool = True,
) -> bool:
    """
    Validate a delivery plan against all constraints.
    """
    depot = depot or WAREHOUSE_NAME
    
    # Filter out empty routes for validation
    non_empty_plan = []
    non_empty_vehicles = []
    non_empty_route_types = []
    
    for i, route in enumerate(plan):
        if route:  # Only include non-empty routes
            non_empty_plan.append(route)
            if i < len(vehicle_plan):
                non_empty_vehicles.append(vehicle_plan[i])
            if i < len(route_plan):
                non_empty_route_types.append(route_plan[i])
    
    # If no non-empty routes, validation fails
    if not non_empty_plan:
        if verbose:
            print("CSP: No non-empty routes found")
        return False
    
    all_checks_passed = True

    # Check 1: All deliveries are covered exactly once
    coverage_ok, missing, duplicates = _check_coverage(non_empty_plan, deliveries)
    if not coverage_ok:
        if verbose:
            if missing:
                print(f"CSP: Missing locations: {missing}")
            if duplicates:
                print(f"CSP: Duplicate locations: {duplicates}")
        all_checks_passed = False

    # Check 2: Vehicle capacity constraints
    capacity_ok, overloads = _check_capacity(non_empty_plan, deliveries, non_empty_vehicles)
    if not capacity_ok:
        if verbose:
            for vehicle_idx, total, capacity in overloads:
                print(f"CSP: Vehicle {vehicle_idx + 1} overloaded: {total}/{capacity} packages")
        all_checks_passed = False

    # Check 3: Deadline constraints (if provided)
    if deadlines and (distance_lookup or time_lookup):
        deadlines_ok, missed_deadlines = _check_deadlines(
            non_empty_plan, deadlines, distance_lookup, time_lookup, depot
        )
        if not deadlines_ok:
            if verbose:
                for loc, eta, deadline in missed_deadlines:
                    print(f"CSP: Deadline missed for {loc}: ETA={eta:.0f}min, Deadline={deadline}min")
            all_checks_passed = False

    # Check 4: Route consistency
    consistency_ok, invalid = _check_route_consistency(non_empty_plan)
    if not consistency_ok:
        if verbose:
            for orig, dest in invalid:
                print(f"CSP: Invalid route segment: {orig} -> {dest}")
        all_checks_passed = False

    if all_checks_passed and verbose:
        print("CSP: All validation checks passed")

    return all_checks_passed


def _check_coverage(plan: List[List[str]], deliveries: Dict[str, int]) -> Tuple[bool, set, set]:
    """Check that every delivery location appears exactly once."""
    required = set(deliveries.keys())
    assigned = set()
    duplicates = set()

    for route in plan:
        for location in route:
            if location in assigned:
                duplicates.add(location)
            assigned.add(location)

    missing = required - assigned

    return (len(missing) == 0 and len(duplicates) == 0), missing, duplicates


def _check_capacity(
    plan: List[List[str]],
    deliveries: Dict[str, int],
    vehicle_plan: List[str],
) -> Tuple[bool, List[Tuple[int, int, int]]]:
    """Check that no vehicle exceeds its capacity."""
    vehicle_capacities = {
        "small_truck": 8,
        "medium_truck": 15,
        "truck": 30,
        "heavy_truck": 40,
        "refrigerated_truck": 25,
    }

    overloads = []

    for i, route in enumerate(plan):
        if not route:
            continue

        vehicle = vehicle_plan[i] if i < len(vehicle_plan) else "truck"
        capacity = vehicle_capacities.get(vehicle, 30)

        total_packages = sum(deliveries.get(location, 0) for location in route)

        if total_packages > capacity:
            overloads.append((i, total_packages, capacity))

    return (len(overloads) == 0), overloads


def _check_deadlines(
    plan: List[List[str]],
    deadlines: Dict[str, str],
    distance_lookup: Optional[Dict[Tuple[str, str], float]],
    time_lookup: Optional[Dict[Tuple[str, str], float]],
    depot: str,
) -> Tuple[bool, List[Tuple[str, float, float]]]:
    """
    Check that all deadlines are met based on travel times.
    """

    # Use time_lookup if provided, otherwise estimate from distance (1 km = 2 minutes)
    def get_travel_time(origin: str, destination: str) -> float:
        if time_lookup and (origin, destination) in time_lookup:
            return time_lookup[(origin, destination)]
        if distance_lookup and (origin, destination) in distance_lookup:
            # Estimate 2 minutes per km (30 km/h average speed)
            return distance_lookup[(origin, destination)] * 2
        return 0

    missed = []

    for route in plan:
        if not route:
            continue

        current_time = 0.0
        current_location = depot

        for location in route:
            # Add travel time to this location
            travel_time = get_travel_time(current_location, location)
            current_time += travel_time

            # Check deadline for this location
            if location in deadlines:
                deadline_minutes = _parse_deadline(deadlines[location])
                if deadline_minutes is not None and current_time > deadline_minutes:
                    missed.append((location, current_time, deadline_minutes))

            # Add service time at stop (15 minutes for unloading)
            current_time += 15
            current_location = location

    return (len(missed) == 0), missed


def _check_route_consistency(plan: List[List[str]]) -> Tuple[bool, List[Tuple[str, str]]]:
    """Check for basic route consistency."""
    invalid = []

    for route in plan:
        for i in range(len(route) - 1):
            if route[i] == route[i + 1]:
                invalid.append((route[i], route[i + 1]))

    return (len(invalid) == 0), invalid


def _parse_deadline(deadline: str) -> Optional[float]:
    """
    Parse deadline string to minutes.
    Supports:
    - "60" -> 60 minutes
    - "2h" -> 120 minutes
    - "14:30" -> minutes since midnight
    - "2:30 PM" -> minutes since midnight
    """
    if not deadline:
        return None

    deadline = deadline.strip().lower()

    # Try direct integer (minutes)
    try:
        return float(deadline)
    except ValueError:
        pass

    # Try format like "2h" or "2.5h"
    if deadline.endswith("h"):
        try:
            hours = float(deadline[:-1])
            return hours * 60
        except ValueError:
            pass

    # Try format like "14:30" or "2:30 PM"
    try:
        if " " in deadline:
            # Handle AM/PM
            dt = datetime.strptime(deadline, "%I:%M %p")
            return dt.hour * 60 + dt.minute
        if ":" in deadline:
            parts = deadline.split(":")
            if len(parts) == 2:
                hours = int(parts[0])
                minutes = int(parts[1])
                return hours * 60 + minutes
    except (ValueError, TypeError):
        pass

    return None


def validate_with_details(
    plan: List[List[str]],
    deliveries: Dict[str, int],
    vehicle_plan: List[str],
    route_plan: List[str],
    deadlines: Optional[Dict[str, str]] = None,
    distance_lookup: Optional[Dict[Tuple[str, str], float]] = None,
    time_lookup: Optional[Dict[Tuple[str, str], float]] = None,
    depot: str = None,
) -> Dict:
    """
    Validate and return detailed results including what passed/failed.

    Returns:
        Dictionary with validation results and details
    """
    depot = depot or WAREHOUSE_NAME

    coverage_ok, missing, duplicates = _check_coverage(plan, deliveries)
    capacity_ok, overloads = _check_capacity(plan, deliveries, vehicle_plan)
    deadlines_ok, missed_deadlines = True, []
    consistency_ok, invalid = _check_route_consistency(plan)

    if deadlines and (distance_lookup or time_lookup):
        deadlines_ok, missed_deadlines = _check_deadlines(
            plan, deadlines, distance_lookup, time_lookup, depot
        )

    return {
        "valid": coverage_ok and capacity_ok and deadlines_ok and consistency_ok,
        "checks": {
            "coverage": coverage_ok,
            "capacity": capacity_ok,
            "deadlines": deadlines_ok,
            "consistency": consistency_ok,
        },
        "details": {
            "missing_locations": list(missing),
            "duplicate_locations": list(duplicates),
            "capacity_overloads": [
                {"vehicle": idx + 1, "packages": total, "capacity": cap}
                for idx, total, cap in overloads
            ],
            "missed_deadlines": [
                {"location": loc, "eta_minutes": eta, "deadline_minutes": dl}
                for loc, eta, dl in missed_deadlines
            ],
            "invalid_segments": [
                {"from": orig, "to": dest}
                for orig, dest in invalid
            ],
        },
    }
