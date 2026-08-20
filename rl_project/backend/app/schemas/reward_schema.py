from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, Any
from datetime import datetime

class RewardCreate(BaseModel):
    decision_id: int
    reward_value: float
    metrics: Dict[str, Any] = Field(default_factory=dict)

class Reward(RewardCreate):
    id: int
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(from_attributes=True)