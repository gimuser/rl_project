# app/database/repository.py

from datetime import datetime
from typing import Optional
from app.database.database import (
    client,
    db,
    alerts_collection,
    decisions_collection,
    rewards_collection,
    evaluations_collection,
    pipeline_collection,
    training_collection,
)
from app.schemas import Alert, AlertCreate, Decision, DecisionCreate, Reward, RewardCreate, DashboardSummary
from app.utils.logger import logger


# ==========================================
# 1. ALERTS MANAGEMENT
# ==========================================
def get_alerts_from_db(skip: int = 0, limit: int = 10) -> list[Alert]:
    """Récupère la liste des alertes depuis MongoDB avec pagination."""
    alerts = []
    for doc in alerts_collection.find().skip(skip).limit(limit):
        alerts.append(
            Alert(
                id=doc["id"],
                title=doc["title"],
                severity=doc["severity"],
                source=doc["source"],
            )
        )
    logger.info(f"{len(alerts)} alerts retrieved")
    return alerts


def create_alert_in_db(alert: AlertCreate) -> Alert:
    """Ajoute une nouvelle alerte dans MongoDB."""
    last_alert = alerts_collection.find_one(sort=[("id", -1)])
    new_id = (last_alert["id"] + 1) if last_alert else 1

    new_alert = {
        "id": new_id,
        "title": alert.title,
        "severity": alert.severity,
        "source": alert.source,
    }

    alerts_collection.insert_one(new_alert)
    logger.info(f"Alert {new_id} created successfully")
    return Alert(**new_alert)


def get_alert_by_id_from_db(alert_id: int) -> Optional[Alert]:
    """Récupère une alerte par son ID."""
    document = alerts_collection.find_one({"id": alert_id})
    if document is None:
        logger.warning(f"Alert {alert_id} not found")
        return None

    logger.info(f"Alert {alert_id} retrieved successfully")
    return Alert(
        id=document["id"],
        title=document["title"],
        severity=document["severity"],
        source=document["source"],
    )


def update_alert_in_db(alert_id: int, alert: AlertCreate) -> Optional[Alert]:
    """Met à jour une alerte existante."""
    result = alerts_collection.update_one(
        {"id": alert_id},
        {
            "$set": {
                "title": alert.title,
                "severity": alert.severity,
                "source": alert.source,
            }
        },
    )

    if result.matched_count == 0:
        logger.warning(f"Alert {alert_id} not found for update")
        return None

    logger.info(f"Alert {alert_id} updated successfully")
    return get_alert_by_id_from_db(alert_id)


def delete_alert_from_db(alert_id: int) -> bool:
    """Supprime une alerte de MongoDB."""
    result = alerts_collection.delete_one({"id": alert_id})
    if result.deleted_count == 0:
        logger.warning(f"Alert {alert_id} not found for deletion")
        return False

    logger.info(f"Alert {alert_id} deleted successfully")
    return True


# ==========================================
# 2. DECISIONS MANAGEMENT (Ikram)
# ==========================================
def create_decision_in_db(decision: DecisionCreate) -> Decision:
    """Enregistre une nouvelle décision du RL Agent."""
    last_decision = decisions_collection.find_one(sort=[("id", -1)])
    new_id = (last_decision["id"] + 1) if last_decision else 1

    new_decision_dict = {
        "id": new_id,
        "incident_id": decision.incident_id,
        "action": decision.action,
    }

    decisions_collection.insert_one(new_decision_dict)
    logger.info(f"Decision {new_id} created successfully")
    return Decision(**new_decision_dict)


def get_decisions_from_db(skip: int = 0, limit: int = 10) -> list[Decision]:
    """Récupère la liste des décisions enregistrées."""
    decisions = []
    for doc in decisions_collection.find().skip(skip).limit(limit):
        decisions.append(Decision(**doc))
    logger.info(f"{len(decisions)} decisions retrieved")
    return decisions


# ==========================================
# 3. REWARDS MANAGEMENT (Hiba)
# ==========================================
def create_reward_in_db(reward: RewardCreate) -> Reward:
    """Enregistre une nouvelle récompense calculée."""
    last_reward = rewards_collection.find_one(sort=[("id", -1)])
    new_id = (last_reward["id"] + 1) if last_reward else 1

    new_reward_dict = {"id": new_id, **reward.model_dump()}

    rewards_collection.insert_one(new_reward_dict)
    logger.info(f"Reward {new_id} created successfully")
    return Reward(**new_reward_dict)


def get_rewards_from_db(skip: int = 0, limit: int = 10) -> list[Reward]:
    """Récupère la liste des récompenses."""
    rewards = []
    for doc in rewards_collection.find().skip(skip).limit(limit):
        rewards.append(Reward(**doc))
    logger.info(f"{len(rewards)} rewards retrieved")
    return rewards


def get_reward_statistics_from_db() -> dict[str, float | None]:
    """Calcule les statistiques de récompenses."""
    total_rewards = rewards_collection.count_documents({})
    if total_rewards == 0:
        return {"mean_reward": None, "max_reward": None, "min_reward": None}

    pipeline = [{"$group": {"_id": None, "avg_reward": {"$avg": "$reward_value"}, "max_reward": {"$max": "$reward_value"}, "min_reward": {"$min": "$reward_value"}}}]
    result = list(rewards_collection.aggregate(pipeline))
    if not result:
        return {"mean_reward": None, "max_reward": None, "min_reward": None}

    stats = result[0]
    return {
        "mean_reward": float(stats["avg_reward"]) if stats.get("avg_reward") is not None else None,
        "max_reward": float(stats["max_reward"]) if stats.get("max_reward") is not None else None,
        "min_reward": float(stats["min_reward"]) if stats.get("min_reward") is not None else None,
    }


# ==========================================
# 4. DASHBOARD SUMMARY (Mohammed)
# ==========================================
def get_dashboard_summary_from_db() -> DashboardSummary:
    """Backward-compatible delegation to the real dashboard aggregation."""
    from app.services.dashboard_service import get_enhanced_dashboard_summary

    return get_enhanced_dashboard_summary()
