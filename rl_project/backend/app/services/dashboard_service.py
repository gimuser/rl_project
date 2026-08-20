import json
from pathlib import Path

from app.database.database import (
    client,
    alerts_collection,
    decisions_collection,
    rewards_collection,
)
from app.schemas.dashboard_schema import DashboardSummary


ROOT = Path(__file__).resolve().parents[3]

TRAIN_METRICS = (
    ROOT / "models" / "training_metrics.json"
)

TEST_METRICS = (
    ROOT / "models" / "real_test_metrics.json"
)


def _load(path):

    if not path.exists():
        return {}

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def get_enhanced_dashboard_summary():

    train = _load(
        TRAIN_METRICS
    )

    test = _load(
        TEST_METRICS
    )

    try:
        database_status = "healthy"

        client.admin.command(
            "ping"
        )

    except Exception:
        database_status = "unhealthy"

    # ------------------------------------------------------------------
    # AUTHORITATIVE REAL TRAINING SCHEMA
    #
    # training_metrics.json:
    # {
    #   "config": {...},
    #   "metrics": [...]
    # }
    #
    # real_test_metrics.json:
    # {
    #   "test_rows": ...,
    #   "average_reward": ...,
    #   ...
    # }
    # ------------------------------------------------------------------

    history = (
        train.get("metrics")
        if isinstance(
            train.get("metrics"),
            list,
        )
        else []
    )

    # The authoritative training rows are stored on each epoch record.
    train_rows = (
        int(history[-1].get("rows", 0))
        if history
        else 0
    )

    # Test rows are stored directly in the authoritative test metrics.
    test_rows = int(
        test.get(
            "test_rows",
            0,
        )
    )

    total_real_alerts = (
        train_rows + test_rows
    )

    # Real model evaluation.
    average_reward = float(
        test.get(
            "average_reward",
            0.0,
        )
    )

    # The project does not expose a classical supervised accuracy
    # metric in real_test_metrics.json. Do not fabricate one.
    accuracy = 0.0

    latency = float(
        test.get(
            "average_latency_ms",
            0.0,
        )
    )

    current_episode = (
        int(history[-1].get("epoch", 0))
        if history
        else 0
    )

    # The model/training state is authoritative from persisted artifacts.
    model_path = (
        ROOT
        / "models"
        / "real_dqn_agent.pt"
    )

    training_status = (
        "completed"
        if (
            model_path.exists()
            and bool(history)
        )
        else "not_trained"
    )

    try:
        total_decisions = (
            decisions_collection.count_documents({})
        )

        total_rewards = (
            rewards_collection.count_documents({})
        )

    except Exception:
        total_decisions = 0
        total_rewards = 0

    return DashboardSummary(
        total_alerts=total_real_alerts,
        processed_alerts=test_rows,
        total_decisions=total_decisions,
        total_rewards=total_rewards,
        average_reward=average_reward,
        average_latency=latency,
        accuracy=accuracy,
        database_status=database_status,
        training_status=training_status,
        current_episode=current_episode,
    )

