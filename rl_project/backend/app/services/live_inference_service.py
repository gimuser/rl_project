from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from app.rl_agent.offline_algorithms import build_model, algorithm_metadata
from app.rl_agent.triage_env import ACTIONS, FEATURES
from app.services.model_versioning import ensure_model_version
from app.services.live_alert_service import alerts_collection, activity_collection, analysts_collection

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "real_dqn_agent.pt"
INFERENCE_META_PATH = Path(__file__).resolve().parents[3] / "models" / "live_inference.json"
DEFAULT_CONFIDENCE_THRESHOLD = 0.60
DEFAULT_MARGIN_THRESHOLD = 0.15


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values, axis=1, keepdims=True)
    exp = np.exp(np.clip(shifted, -50, 50))
    return exp / np.maximum(exp.sum(axis=1, keepdims=True), 1e-12)


def _least_loaded_analyst() -> dict[str, Any] | None:
    analysts = list(analysts_collection.find({"active": True}, {"_id": 0}))
    if not analysts:
        return None
    scored = []
    for analyst in analysts:
        analyst_id = analyst.get("analyst_id")
        capacity = int(analyst.get("capacity", 0) or 0)
        load = alerts_collection.count_documents({
            "assigned_analyst": analyst_id,
            "status": {"$in": ["HUMAN_REVIEW_PENDING", "ESCALATED", "OPEN"]},
        })
        scored.append((load, -max(capacity - load, 0), analyst))
    available = [x for x in scored if x[0] < int(x[2].get("capacity", 0) or 0)]
    pool = available or scored
    pool.sort(key=lambda x: (x[0], x[1], str(x[2].get("analyst_id", ""))))
    return pool[0][2] if pool else None


def _feature_matrix(document: dict[str, Any]) -> np.ndarray:
    processed = document.get("processed") or {}
    missing = [n for n in FEATURES if n not in processed]
    if missing:
        raise ValueError(f"Alert {document.get('alert_id')} missing processed features: {missing}")
    return np.asarray([[float(processed[name]) for name in FEATURES]], dtype=np.float32)


def _load_model(*, model_path: Path | None = None, model_name: str | None = None):
    path = model_path or MODEL_PATH
    if not path.exists():
        raise FileNotFoundError(f"Trained model not found: {path}")
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    algorithm = str(checkpoint.get("algorithm") or model_name or "double_dqn").lower()
    metadata = ensure_model_version(
        model_path=path,
        model_name=model_name or algorithm,
        extra={"algorithm": algorithm, "inference_role": "champion_live_evaluation"},
    )
    model = build_model(
        algorithm,
        input_dim=len(FEATURES),
        n_actions=len(ACTIONS),
        learning_rate=1e-3,
        gamma=float(checkpoint.get("gamma", 0.95)),
        hidden_dim=128,
    )
    model.load(str(path))
    return model, {**(metadata or {}), "algorithm": algorithm, "algorithm_metadata": algorithm_metadata(algorithm)}


def run_live_inference(
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    margin_threshold: float = DEFAULT_MARGIN_THRESHOLD,
    only_uninferred: bool = True,
    model_path: str | None = None,
    model_name: str | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    """Run the trained champion on one live decision cycle.

    When cycle_id is supplied, inference is restricted to that exact cycle.
    This prevents an old/previous live cycle from being mixed with a fresh
    80-alert holdout.
    """
    selected_model_path = Path(model_path) if model_path else None
    model, model_meta = _load_model(model_path=selected_model_path, model_name=model_name)

    query: dict[str, Any] = {}
    if cycle_id:
        query["cycle_id"] = cycle_id
    if only_uninferred:
        query["agent.status"] = {"$in": ["WAITING_INFERENCE", None]}

    documents = list(alerts_collection.find(query, {"_id": 0}).sort("timestamp", 1))

    now = utc_now()
    active_cycle = alerts_collection.find_one(
        {"cycle_id": cycle_id} if cycle_id else {},
        {"_id": 0, "cycle_id": 1, "decision_cycle_id": 1},
    ) or {}
    resolved_cycle_id = (
        cycle_id
        or active_cycle.get("cycle_id")
        or active_cycle.get("decision_cycle_id")
        or f"CYCLE-INFER-{int(now.timestamp())}"
    )

    counts = {name: 0 for name in ACTIONS.values()}
    routed = 0
    errors: list[dict[str, Any]] = []
    processed = 0
    start = time.perf_counter()

    for document in documents:
        alert_id = str(document.get("alert_id"))
        try:
            states = _feature_matrix(document)
            q_values = model.q_values(states)[0]
            probabilities = _softmax(q_values.reshape(1, -1))[0]

            order = np.argsort(probabilities)[::-1]
            top_action = int(order[0])
            second_action = int(order[1]) if len(order) > 1 else top_action
            confidence = float(probabilities[top_action])
            margin = float(probabilities[top_action] - probabilities[second_action])

            selected_action = top_action
            uncertainty_reason = None
            if top_action != 2:
                if confidence < confidence_threshold:
                    selected_action = 2
                    uncertainty_reason = "LOW_CONFIDENCE"
                elif margin < margin_threshold:
                    selected_action = 2
                    uncertainty_reason = "LOW_MARGIN"

            action_name = ACTIONS[selected_action]
            timestamp = utc_now()
            requires_human = action_name == "human_review"
            status = (
                "HUMAN_REVIEW_PENDING"
                if requires_human
                else "MODEL_ALLOWED"
                if action_name == "allow"
                else "MODEL_BLOCKED"
            )

            assigned_analyst = None
            if requires_human:
                analyst = _least_loaded_analyst()
                if analyst:
                    assigned_analyst = analyst.get("analyst_id")
                    routed += 1

            q_map = {ACTIONS[index]: float(value) for index, value in enumerate(q_values)}
            probability_map = {
                ACTIONS[index]: float(value)
                for index, value in enumerate(probabilities)
            }

            agent_state = {
                "status": "INFERRED",
                "action": action_name,
                "model_action": ACTIONS[top_action],
                "confidence": confidence,
                "q_values": q_map,
                "action_probabilities": probability_map,
                "confidence_threshold": float(confidence_threshold),
                "margin_threshold": float(margin_threshold),
                "action_margin": margin,
                "uncertainty_reason": uncertainty_reason,
                "model_version": model_meta.get("model_version"),
                "model_name": model_meta.get("model_name") or model_name,
                "algorithm": model_meta.get("algorithm"),
                "algorithm_metadata": model_meta.get("algorithm_metadata"),
                "candidate_model_path": str(selected_model_path) if selected_model_path else str(MODEL_PATH),
                "requires_human_review": requires_human,
                "inference_timestamp": timestamp,
                "decision_cycle_id": resolved_cycle_id,
            }

            alerts_collection.update_one(
                {"alert_id": alert_id},
                {
                    "$set": {
                        "status": status,
                        "agent": agent_state,
                        "assigned_analyst": assigned_analyst,
                        "updated_at": timestamp,
                        "cycle_id": resolved_cycle_id,
                        "decision_cycle_id": resolved_cycle_id,
                    }
                },
            )

            activity_collection.insert_one({
                "alert_id": alert_id,
                "cycle_id": resolved_cycle_id,
                "decision_cycle_id": resolved_cycle_id,
                "actor": "agent",
                "action": "AGENT_INFERENCE",
                "details": {
                    "action": action_name,
                    "model_action": ACTIONS[top_action],
                    "confidence": confidence,
                    "action_margin": margin,
                    "uncertainty_reason": uncertainty_reason,
                    "model_version": model_meta.get("model_version"),
                    "algorithm": model_meta.get("algorithm"),
                },
                "timestamp": timestamp,
            })

            if requires_human:
                activity_collection.insert_one({
                    "alert_id": alert_id,
                    "cycle_id": resolved_cycle_id,
                    "decision_cycle_id": resolved_cycle_id,
                    "actor": "system",
                    "action": "HUMAN_REVIEW_ROUTED",
                    "details": {
                        "analyst_id": assigned_analyst,
                        "reason": uncertainty_reason or "MODEL_REQUESTED_REVIEW",
                        "confidence": confidence,
                        "model_version": model_meta.get("model_version"),
                        "algorithm": model_meta.get("algorithm"),
                    },
                    "timestamp": timestamp,
                })

            counts[action_name] += 1
            processed += 1

        except Exception as exc:
            errors.append({"alert_id": alert_id, "error": str(exc)})
            activity_collection.insert_one({
                "alert_id": alert_id,
                "cycle_id": resolved_cycle_id,
                "decision_cycle_id": resolved_cycle_id,
                "actor": "system",
                "action": "AGENT_INFERENCE_ERROR",
                "details": {
                    "error": str(exc),
                    "model_version": model_meta.get("model_version"),
                    "algorithm": model_meta.get("algorithm"),
                },
                "timestamp": utc_now(),
            })

    elapsed = time.perf_counter() - start
    summary = {
        "status": "completed" if not errors else "completed_with_errors",
        "cycle_id": resolved_cycle_id,
        "decision_cycle_id": resolved_cycle_id,
        "model_version": model_meta.get("model_version"),
        "model_name": model_meta.get("model_name") or model_name,
        "algorithm": model_meta.get("algorithm"),
        "confidence_threshold": confidence_threshold,
        "margin_threshold": margin_threshold,
        "alerts_considered": len(documents),
        "alerts_processed": processed,
        "human_review_routed": routed,
        "action_distribution": counts,
        "errors": errors,
        "duration_seconds": elapsed,
    }
    INFERENCE_META_PATH.write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    return summary


def get_inference_status() -> dict[str, Any]:
    try:
        if INFERENCE_META_PATH.exists():
            payload = json.loads(INFERENCE_META_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    return {
        "status": "idle",
        "message": "No live inference cycle has been recorded yet.",
        "alerts_considered": 0,
        "alerts_processed": 0,
        "human_review_routed": 0,
        "action_distribution": {name: 0 for name in ACTIONS.values()},
    }
