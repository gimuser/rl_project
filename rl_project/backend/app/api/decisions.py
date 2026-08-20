from fastapi import APIRouter
from app.schemas import Decision, DecisionCreate
from app.database.repository import create_decision_in_db, get_decisions_from_db

# إزالة prefix="/decisions"
router = APIRouter(tags=["Decisions"])


@router.get("", response_model=list[Decision])
def get_decisions(skip: int = 0, limit: int = 10):
    """Récupère la liste des décisions prises par le RL Agent."""
    return get_decisions_from_db(skip=skip, limit=limit)


@router.post("", response_model=Decision)
def add_decision(decision: DecisionCreate):
    """Enregistre une nouvelle décision du RL Agent."""
    return create_decision_in_db(decision)