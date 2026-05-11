import os
import random
from typing import Dict, List, Optional, Sequence, Tuple


VEHICLES = {
    "small_truck": {"speed": 70, "fuel_cost": 6.5, "capacity": 8},
    "medium_truck": {"speed": 65, "fuel_cost": 8.0, "capacity": 15},
    "truck": {"speed": 60, "fuel_cost": 10.0, "capacity": 30},
    "heavy_truck": {"speed": 55, "fuel_cost": 12.5, "capacity": 40},
    "refrigerated_truck": {"speed": 55, "fuel_cost": 12.0, "capacity": 25},
}

ROUTES = {
    "highway": {"factor": 1.0},
    "expressway": {"factor": 0.8},
    "city": {"factor": 1.2},
}

WAREHOUSE_NAME = os.getenv("WAREHOUSE_NAME", "Central Warehouse Karachi")

Chromosome = Dict[str, List]


def normalize_vehicle_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in VEHICLES:
        return cleaned
    if cleaned.endswith("s") and cleaned[:-1] in VEHICLES:
        return cleaned[:-1]
    return None


def normalize_route_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
    return cleaned if cleaned in ROUTES else None


def generate_initial_population(
    locations: Sequence[str],
    num_vehicles: int,
    vehicle_options: Sequence[str],
    route_options: Sequence[str],
    population_size: int,
) -> List[Chromosome]:
    population: List[Chromosome] = []
    locations = list(locations)

    for _ in range(population_size):
        shuffled = locations[:]
        random.shuffle(shuffled)
        routes = [[] for _ in range(num_vehicles)]
        for index, loc in enumerate(shuffled):
            routes[index % num_vehicles].append(loc)
        for route in routes:
            random.shuffle(route)

        population.append(
            {
                "routes": routes,
                "vehicles": [random.choice(vehicle_options) for _ in range(num_vehicles)],
                "route_types": [random.choice(route_options) for _ in range(num_vehicles)],
            }
        )

    return population


def _route_distance(
    route: List[str],
    distance_lookup: Dict[Tuple[str, str], float],
    depot: str = WAREHOUSE_NAME,
    penalty: float = 10_000,
) -> float:
    if not route:
        return 0.0

    total = 0.0
    current = depot
    for loc in route:
        total += distance_lookup.get((current, loc), penalty)
        current = loc
    return total


def calculate_fitness(
    chromosome: Chromosome,
    deliveries: Dict[str, int],
    distance_lookup: Dict[Tuple[str, str], float],
    budget: Optional[float] = None,
    time_limit: Optional[float] = None,
    priority: str = "cost",
    constraints: Optional[List[str]] = None,
) -> float:
    total_cost = 0.0
    total_time = 0.0
    penalty = 0.0
    assigned: List[str] = []
    constraints = [c.lower() for c in (constraints or [])]
    has_fragile = any("fragile" in c for c in constraints)
    has_medical = any("medical" in c for c in constraints)

    routes = chromosome["routes"]
    vehicles = chromosome["vehicles"]
    route_types = chromosome["route_types"]

    for index, route in enumerate(routes):
        if not route:
            continue

        vehicle = vehicles[index]
        route_type = route_types[index]
        vehicle_meta = VEHICLES.get(vehicle)
        route_meta = ROUTES.get(route_type)
        if not vehicle_meta or not route_meta:
            penalty += 10_000
            continue

        route_units = sum(deliveries.get(loc, 0) for loc in route)
        if route_units > vehicle_meta["capacity"]:
            penalty += (route_units - vehicle_meta["capacity"]) * 100

        distance = _route_distance(route, distance_lookup)
        factor = route_meta["factor"]
        total_cost += distance * vehicle_meta["fuel_cost"] * factor
        total_time += (distance / vehicle_meta["speed"]) * factor

        if has_fragile and vehicle in {"truck", "heavy_truck"}:
            penalty += 30
        if has_medical and vehicle != "refrigerated_truck":
            penalty += 50

        assigned.extend(route)

    required = set(deliveries.keys())
    if set(assigned) != required:
        penalty += 10_000
    if len(assigned) != len(set(assigned)):
        penalty += 5_000

    if budget is not None and total_cost > budget:
        penalty += 100
    if time_limit is not None and total_time > time_limit:
        penalty += 80

    if priority == "time":
        return total_time * 2 + total_cost + penalty
    return total_cost * 2 + total_time + penalty


def selection(
    population: List[Chromosome],
    fitness_scores: List[float],
    tournament_size: int = 3,
) -> Chromosome:
    indices = random.sample(range(len(population)), k=min(tournament_size, len(population)))
    best_index = min(indices, key=lambda i: fitness_scores[i])
    return population[best_index]


def crossover(parent1: Chromosome, parent2: Chromosome) -> Chromosome:
    flat1 = [loc for route in parent1["routes"] for loc in route]
    flat2 = [loc for route in parent2["routes"] for loc in route]
    if not flat1:
        return {
            "routes": [route[:] for route in parent2["routes"]],
            "vehicles": parent2["vehicles"][:],
            "route_types": parent2["route_types"][:],
        }

    cut = random.randint(1, len(flat1))
    prefix = flat1[:cut]
    remainder = [loc for loc in flat2 if loc not in prefix]
    combined = prefix + remainder

    num_vehicles = len(parent1["routes"])
    routes = [[] for _ in range(num_vehicles)]
    for index, loc in enumerate(combined):
        routes[index % num_vehicles].append(loc)

    vehicles = [
        random.choice([parent1["vehicles"][i], parent2["vehicles"][i]])
        for i in range(num_vehicles)
    ]
    route_types = [
        random.choice([parent1["route_types"][i], parent2["route_types"][i]])
        for i in range(num_vehicles)
    ]

    return {
        "routes": routes,
        "vehicles": vehicles,
        "route_types": route_types,
    }


def mutation(
    chromosome: Chromosome,
    mutation_rate: float,
    vehicle_options: Sequence[str],
    route_options: Sequence[str],
) -> Chromosome:
    routes = [route[:] for route in chromosome["routes"]]
    vehicles = chromosome["vehicles"][:]
    route_types = chromosome["route_types"][:]

    if random.random() < mutation_rate:
        all_locations = [loc for route in routes for loc in route]
        if len(all_locations) >= 2:
            loc_a, loc_b = random.sample(all_locations, 2)
            _swap_locations(routes, loc_a, loc_b)

    if random.random() < mutation_rate:
        origin_routes = [route for route in routes if route]
        if origin_routes:
            source = random.choice(origin_routes)
            loc = random.choice(source)
            source.remove(loc)
            random.choice(routes).append(loc)

    for route in routes:
        if random.random() < mutation_rate:
            random.shuffle(route)

    for index in range(len(vehicles)):
        if random.random() < mutation_rate:
            vehicles[index] = random.choice(vehicle_options)
        if random.random() < mutation_rate:
            route_types[index] = random.choice(route_options)

    return {
        "routes": routes,
        "vehicles": vehicles,
        "route_types": route_types,
    }


def evolve_population(
    population: List[Chromosome],
    deliveries: Dict[str, int],
    distance_lookup: Dict[Tuple[str, str], float],
    vehicle_options: Sequence[str],
    route_options: Sequence[str],
    budget: Optional[float],
    time_limit: Optional[float],
    priority: str,
    constraints: Optional[List[str]],
    mutation_rate: float = 0.1,
    elitism: int = 1,
) -> List[Chromosome]:
    fitness_scores = [
        calculate_fitness(
            chromosome,
            deliveries,
            distance_lookup,
            budget=budget,
            time_limit=time_limit,
            priority=priority,
            constraints=constraints,
        )
        for chromosome in population
    ]
    ranked = [chrom for _, chrom in sorted(zip(fitness_scores, population), key=lambda pair: pair[0])]
    next_generation = ranked[:elitism]

    while len(next_generation) < len(population):
        parent1 = selection(population, fitness_scores)
        parent2 = selection(population, fitness_scores)
        child = crossover(parent1, parent2)
        child = mutation(child, mutation_rate, vehicle_options, route_options)
        next_generation.append(child)

    return next_generation


def _plan_metrics(
    chromosome: Chromosome,
    distance_lookup: Dict[Tuple[str, str], float],
) -> Dict[str, object]:
    total_distance = 0.0
    total_cost = 0.0
    total_time = 0.0
    per_vehicle: List[Dict[str, object]] = []

    for index, route in enumerate(chromosome["routes"]):
        vehicle = chromosome["vehicles"][index]
        route_type = chromosome["route_types"][index]
        vehicle_meta = VEHICLES[vehicle]
        route_meta = ROUTES[route_type]
        distance = _route_distance(route, distance_lookup)
        factor = route_meta["factor"]
        cost = distance * vehicle_meta["fuel_cost"] * factor
        time_hours = (distance / vehicle_meta["speed"]) * factor

        per_vehicle.append(
            {
                "vehicle": vehicle,
                "route_type": route_type,
                "stops": route,
                "distance": distance,
                "cost": cost,
                "time_hours": time_hours,
            }
        )

        total_distance += distance
        total_cost += cost
        total_time += time_hours

    return {
        "total_distance": total_distance,
        "total_cost": total_cost,
        "total_time": total_time,
        "per_vehicle": per_vehicle,
    }


def genetic_algorithm(
    deliveries: Dict[str, int],
    distance_lookup: Dict[Tuple[str, str], float],
    num_vehicles: int,
    budget: Optional[float] = None,
    time_limit: Optional[float] = None,
    priority: str = "cost",
    constraints: Optional[List[str]] = None,
    fixed_vehicle: Optional[str] = None,
    fixed_route: Optional[str] = None,
    generations: int = 200,
    population_size: int = 50,
    mutation_rate: float = 0.1,
) -> Dict[str, object]:
    locations = list(deliveries.keys())
    vehicle_options = [fixed_vehicle] if fixed_vehicle else list(VEHICLES.keys())
    route_options = [fixed_route] if fixed_route else list(ROUTES.keys())

    population = generate_initial_population(
        locations,
        num_vehicles,
        vehicle_options,
        route_options,
        population_size,
    )

    for _ in range(generations):
        population = evolve_population(
            population,
            deliveries,
            distance_lookup,
            vehicle_options,
            route_options,
            budget,
            time_limit,
            priority,
            constraints,
            mutation_rate,
        )

    fitness_scores = [
        calculate_fitness(
            chromosome,
            deliveries,
            distance_lookup,
            budget=budget,
            time_limit=time_limit,
            priority=priority,
            constraints=constraints,
        )
        for chromosome in population
    ]
    best_index = min(range(len(population)), key=lambda i: fitness_scores[i])
    best_plan = population[best_index]
    metrics = _plan_metrics(best_plan, distance_lookup)

    return {
        "best_plan": best_plan["routes"],
        "vehicle_plan": best_plan["vehicles"],
        "route_plan": best_plan["route_types"],
        "total_cost": metrics["total_cost"],
        "total_distance": metrics["total_distance"],
        "total_time": metrics["total_time"],
        "per_vehicle": metrics["per_vehicle"],
        "fitness_score": fitness_scores[best_index],
    }


def _swap_locations(routes: List[List[str]], loc_a: str, loc_b: str) -> None:
    pos_a = _find_location(routes, loc_a)
    pos_b = _find_location(routes, loc_b)
    if pos_a and pos_b:
        route_a, idx_a = pos_a
        route_b, idx_b = pos_b
        route_a[idx_a], route_b[idx_b] = route_b[idx_b], route_a[idx_a]


def _find_location(routes: List[List[str]], location: str):
    for route in routes:
        if location in route:
            return route, route.index(location)
    return None
