"""Schemas for inference API requests/responses."""

from pydantic import BaseModel, Field
from typing import Any, Dict


class InferenceRequest(BaseModel):
	features: Dict[str, Any]


class InferenceResponse(BaseModel):
	action: str
	score: float = Field(0.0)


__all__ = ["InferenceRequest", "InferenceResponse"]

