"""Agent-related API routes.

Provides a small router to query agent status and request an action for an
incoming event. Uses `app.services.agent_service` for behavior.
"""

from fastapi import APIRouter, HTTPException
from app.data_pipeline.contract import DataContractError
from app.services.agent_service import get_agent_status, act_on_event
from app.services.model_service import ModelUnavailableError

router = APIRouter(prefix="/api/agent", tags=["Agent"])


@router.get("/status")
def api_agent_status():
	return get_agent_status()


@router.post("/act")
def api_act(payload: dict):
    try:
        return act_on_event(payload)
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DataContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
