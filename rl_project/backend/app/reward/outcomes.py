"""Canonical action IDs, names, and reward logic for the processed dataset."""

from __future__ import annotations

from typing import Any


CLOSE = 0
ESCALATE = 1
HUMAN_REVIEW = 2
ACTION_NAMES = {
    CLOSE: "close_recommendation",
    ESCALATE: "escalate_for_human_review",
    HUMAN_REVIEW: "human_review",
}

# The processed dataset encodes the target as numeric IncidentGrade values.
# We map those grades to the canonical action IDs defined above.
EXPECTED_ACTION_BY_GRADE = {0: CLOSE, 1: CLOSE, 2: ESCALATE, 3: HUMAN_REVIEW}


def validate_action_mapping(action_dim: int | None = None) -> None:
    expected_dim = len(ACTION_NAMES)
    if action_dim is not None and action_dim != expected_dim:
        raise ValueError(f"Action space mismatch: expected {expected_dim} actions, got {action_dim}")


def expected_action(incident_grade: int) -> int:
    try:
        return EXPECTED_ACTION_BY_GRADE[int(incident_grade)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported IncidentGrade value: {incident_grade!r}") from exc


def historical_outcome_reward(incident_grade: int, action: int) -> float:
    """Reward the agent using the numeric processed outcome labels."""
    if action not in ACTION_NAMES:
        raise ValueError(f"Unsupported action id: {action!r}")
    target = expected_action(incident_grade)
    if action == target:
        return {CLOSE: 8.0, ESCALATE: 20.0, HUMAN_REVIEW: 3.0}[target]
    if int(incident_grade) == 2 and action == CLOSE:
        return -40.0
    if int(incident_grade) in (0, 1) and action == ESCALATE:
        return -15.0
    if int(incident_grade) == 3 and action != HUMAN_REVIEW:
        return -8.0
    return -12.0


def feedback_reward(
    *,
    outcome: str,
    decision_correct: bool | None,
    processing_time_seconds: float | None,
) -> tuple[float, dict[str, Any]]:
    """Calculate a persisted reward from a real human/executor result."""
    if outcome == "failed":
        base = -20.0
    elif decision_correct is True:
        base = 10.0
    elif decision_correct is False:
        base = -15.0
    elif outcome == "approved":
        base = 2.0
    elif outcome in {"rejected", "cancelled"}:
        base = -5.0
    elif outcome == "executed":
        base = 1.0
    else:
        raise ValueError(f"Unsupported feedback outcome: {outcome!r}")

    latency_penalty = 0.0
    if processing_time_seconds is not None:
        if processing_time_seconds < 0:
            raise ValueError("processing_time_seconds must be >= 0")
        latency_penalty = min(float(processing_time_seconds) * 0.1, 8.0)
    reward = max(-50.0, min(50.0, base - latency_penalty))
    return reward, {
        "outcome": outcome,
        "decision_correct": decision_correct,
        "processing_time_seconds": processing_time_seconds,
        "base_reward": base,
        "latency_penalty": latency_penalty,
    }

