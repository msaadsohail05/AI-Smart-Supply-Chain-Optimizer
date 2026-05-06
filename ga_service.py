import random

def generate_population(locations, num_vehicles):
    population = []

    for _ in range(10):
        plan = [[] for _ in range(num_vehicles)]
        for loc in locations:
            vehicle = random.randint(0, num_vehicles - 1)
            plan[vehicle].append(loc)
        population.append(plan)

    return population

def fitness(plan, cost_lookup):
    total_cost = 0

    for route in plan:
        if not route:
            continue

        cost = 0
        current = "W"

        for loc in route:
            cost += cost_lookup.get((current, loc), 1000)
            current = loc

        total_cost += cost

    return total_cost