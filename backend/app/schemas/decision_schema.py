from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

class DecisionCreate(BaseModel):
    incident_id: int
    action: str

class Decision(DecisionCreate):
    id: int
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(from_attributes=True)