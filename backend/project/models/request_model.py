from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class DeliveryRequest(BaseModel):
    source: Optional[str] = None
    destinations: List[str] = Field(default_factory=list)
    deadline: Optional[str] = None
    budget: Optional[float] = None
    objective: Optional[str] = None
    packages: Optional[int] = None
    vehicle_type: Optional[str] = None
    avoid: Optional[str] = None
    deliveries: Dict[str, int] = Field(default_factory=dict)
    priority: str = "cost"
    constraints: List[str] = Field(default_factory=list)
