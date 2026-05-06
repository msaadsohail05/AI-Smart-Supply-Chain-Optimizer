from fastapi import FastAPI
from models.request_model import DeliveryRequest
from services.ga_service import generate_population, fitness
from services.csp_service import validate

app = FastAPI()

@app.get("/")
def root():
    print("First api of the project")
    
@app.post("/optimize")
def optimize(request: DeliveryRequest):
    deliveries = request.deliveries
    locations = list(deliveries.keys())

    population = generate_population(locations, num_vehicles=3)

    best_plan = None
    best_cost = float("inf")

    cost_lookup = {
        ("W", "DHA"): 200,
        ("W", "Clifton"): 180,
        ("W", "Saddar"): 100,
    }

    for plan in population:
        if not validate(plan, deliveries, capacity=10):
            continue

        cost = fitness(plan, cost_lookup)

        if cost < best_cost:
            best_cost = cost
            best_plan = plan

    return {
        "best_plan": best_plan,
        "cost": best_cost
    }