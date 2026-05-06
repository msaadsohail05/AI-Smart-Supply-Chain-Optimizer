def validate(plan, deliveries, capacity):
    for route in plan:
        total = sum(deliveries[loc] for loc in route)
        if total > capacity:
            return False
    return True