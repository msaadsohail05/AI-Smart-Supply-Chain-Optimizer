import random
from typing import Dict, List, Sequence, Tuple


Chromosome = List[List[str]]


def generate_initial_population(
    locations: Sequence[str],
    num_vehicles: int,
    population_size: int,
) -> List[Chromosome]:
    population: List[Chromosome] = []
    locations = list(locations)

    for _ in range(population_size):
        shuffled = locations[:]
        random.shuffle(shuffled)
        plan = [[] for _ in range(num_vehicles)]
        for index, loc in enumerate(shuffled):
            plan[index % num_vehicles].append(loc)
        for route in plan:
            random.shuffle(route)
        population.append(plan)

    return population


def calculate_fitness(chromosome: Chromosome, cost_lookup: Dict[Tuple[str, str], float]) -> float:
    total_cost = 0.0
    penalty = 10_000

    for route in chromosome:
        if not route:
            continue

        current = "Warehouse"
        for loc in route:
            total_cost += cost_lookup.get((current, loc), penalty)
            current = loc

    return total_cost


def selection(population: List[Chromosome], fitness_scores: List[float], tournament_size: int = 3) -> Chromosome:
    indices = random.sample(range(len(population)), k=min(tournament_size, len(population)))
    best_index = min(indices, key=lambda i: fitness_scores[i])
    return population[best_index]


def crossover(parent1: Chromosome, parent2: Chromosome) -> Chromosome:
    flat1 = [loc for route in parent1 for loc in route]
    flat2 = [loc for route in parent2 for loc in route]
    if not flat1:
        return [route[:] for route in parent2]

    cut = random.randint(1, len(flat1))
    prefix = flat1[:cut]
    remainder = [loc for loc in flat2 if loc not in prefix]
    combined = prefix + remainder

    num_vehicles = len(parent1)
    child = [[] for _ in range(num_vehicles)]
    for index, loc in enumerate(combined):
        child[index % num_vehicles].append(loc)
    return child


def mutation(chromosome: Chromosome, mutation_rate: float) -> Chromosome:
    mutated = [route[:] for route in chromosome]

    if random.random() < mutation_rate:
        all_locations = [loc for route in mutated for loc in route]
        if len(all_locations) >= 2:
            loc_a, loc_b = random.sample(all_locations, 2)
            _swap_locations(mutated, loc_a, loc_b)

    if random.random() < mutation_rate:
        origin_routes = [route for route in mutated if route]
        if origin_routes:
            source = random.choice(origin_routes)
            loc = random.choice(source)
            source.remove(loc)
            random.choice(mutated).append(loc)

    for route in mutated:
        if random.random() < mutation_rate:
            random.shuffle(route)

    return mutated


def evolve_population(
    population: List[Chromosome],
    cost_lookup: Dict[Tuple[str, str], float],
    mutation_rate: float = 0.1,
    elitism: int = 1,
) -> List[Chromosome]:
    fitness_scores = [calculate_fitness(chromosome, cost_lookup) for chromosome in population]
    ranked = [chrom for _, chrom in sorted(zip(fitness_scores, population), key=lambda pair: pair[0])]
    next_generation = ranked[:elitism]

    while len(next_generation) < len(population):
        parent1 = selection(population, fitness_scores)
        parent2 = selection(population, fitness_scores)
        child = crossover(parent1, parent2)
        child = mutation(child, mutation_rate)
        next_generation.append(child)

    return next_generation


def genetic_algorithm(
    deliveries: Dict[str, int],
    cost_lookup: Dict[Tuple[str, str], float],
    num_vehicles: int,
    generations: int = 200,
    population_size: int = 50,
    mutation_rate: float = 0.1,
) -> Dict[str, object]:
    locations = list(deliveries.keys())
    population = generate_initial_population(locations, num_vehicles, population_size)

    for _ in range(generations):
        population = evolve_population(population, cost_lookup, mutation_rate)

    fitness_scores = [calculate_fitness(chromosome, cost_lookup) for chromosome in population]
    best_index = min(range(len(population)), key=lambda i: fitness_scores[i])
    best_plan = population[best_index]

    return {
        "best_plan": best_plan,
        "total_cost": fitness_scores[best_index],
    }


def _swap_locations(chromosome: Chromosome, loc_a: str, loc_b: str) -> None:
    pos_a = _find_location(chromosome, loc_a)
    pos_b = _find_location(chromosome, loc_b)
    if pos_a and pos_b:
        route_a, idx_a = pos_a
        route_b, idx_b = pos_b
        route_a[idx_a], route_b[idx_b] = route_b[idx_b], route_a[idx_a]


def _find_location(chromosome: Chromosome, location: str):
    for route in chromosome:
        if location in route:
            return route, route.index(location)
    return None
