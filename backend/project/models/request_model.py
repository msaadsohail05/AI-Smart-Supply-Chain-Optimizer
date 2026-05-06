from pydantic import BaseModel
from typing import Dict

class DeliveryRequest(BaseModel):
    deliveries: Dict[str, int]
    priority: str = "cost"
    deadline: str = None
