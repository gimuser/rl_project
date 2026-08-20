from fastapi import APIRouter
from app.schemas import Reward, RewardCreate
from app.database.repository import (
    create_reward_in_db,
    get_rewards_from_db,
    get_reward_statistics_from_db,
)

# إزالة prefix="/rewards"
router = APIRouter(tags=["Rewards"])


@router.get("", response_model=list[Reward])
def get_rewards(skip: int = 0, limit: int = 10):
    """Récupère la liste des récompenses calculées."""
    return get_rewards_from_db(skip=skip, limit=limit)


@router.post("", response_model=Reward)
def add_reward(reward: RewardCreate):
    """Enregistre une nouvelle récompense calculée."""
    return create_reward_in_db(reward)


@router.get("/statistics")
def get_reward_stats():
    """Statistiques globales sur les récompenses."""
    return get_reward_statistics_from_db()
