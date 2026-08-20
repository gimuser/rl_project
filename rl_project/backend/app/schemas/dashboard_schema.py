from pydantic import BaseModel, ConfigDict

class DashboardSummary(BaseModel):
    total_alerts: int | None
    processed_alerts: int | None
    total_decisions: int | None
    total_rewards: int | None
    average_reward: float | None
    average_latency: float | None
    accuracy: float | None
    database_status: str
    training_status: str
    current_episode: int | None

    model_config = ConfigDict(from_attributes=True)
