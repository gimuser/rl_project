"""Schemas for training endpoints."""

from pydantic import BaseModel, Field
from typing import List


class TrainingStatus(BaseModel):
	status: str
	current_epoch: int = Field(0)


class TrainingHistoryItem(BaseModel):
	epoch: int
	loss: float


class TrainingHistory(BaseModel):
	history: List[TrainingHistoryItem]


class TrainingCheckpoints(BaseModel):
	checkpoints: List[str]


__all__ = ["TrainingStatus", "TrainingHistory", "TrainingCheckpoints"]

