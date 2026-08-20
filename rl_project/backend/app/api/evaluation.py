"""Evaluation API routes.

Expose small endpoints to compute evaluation artifacts using
`app.services.evaluation_service`.
"""

from fastapi import APIRouter
from typing import List
from app.services.evaluation_service import confusion_matrix, reward_summary

router = APIRouter(prefix="/api/evaluation", tags=["Evaluation"])


@router.post("/confusion")
def api_confusion(preds: List[int], targets: List[int]):
	return confusion_matrix(preds, targets)


@router.post("/reward-summary")
def api_reward_summary(rewards: List[float]):
	return reward_summary(rewards)


__all__ = ["router"]

