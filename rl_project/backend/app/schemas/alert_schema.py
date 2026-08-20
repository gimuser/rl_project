# app/schemas/alert_schema.py
from pydantic import BaseModel, ConfigDict
from typing import Optional

class AlertBase(BaseModel):
    title: str
    severity: str
    source: str

class AlertCreate(AlertBase):
    pass  # كياخد title, severity, source أوتوماتيكياً من AlertBase

class Alert(AlertBase):
    id: str | int

    model_config = ConfigDict(from_attributes=True)