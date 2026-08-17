"""Verified reward contract for the real IncidentGrade dataset."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAPPING_PATH = ROOT / "models" / "incidentgrade_mapping.json"

ACTION_CLOSE = 0
ACTION_ESCALATE = 1
ACTION_HUMAN_VALIDATION = 2


def load_mapping() -> dict[int, str]:
    if not MAPPING_PATH.exists():
        raise FileNotFoundError(
            f"Verified IncidentGrade mapping missing: {MAPPING_PATH}"
        )

    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))

    if not data.get("verified"):
        raise RuntimeError("IncidentGrade mapping is not verified.")

    return {
        int(code): label
        for code, label in data["numeric_to_label"].items()
    }


def grade_from_numeric(value: int) -> str:
    mapping = load_mapping()

    value = int(value)

    if value not in mapping:
        raise ValueError(
            f"Unknown verified IncidentGrade code: {value}"
        )

    return mapping[value]


def reward_for(label: str, action: int) -> float:
    """
    Reward based exclusively on the verified real IncidentGrade.

    Actions:
      0 = close alert
      1 = escalate
      2 = request human validation

    Unknown/other real labels receive neutral reward rather than
    inventing security semantics.
    """

    label = str(label).strip()

    if label == "TruePositive":
        if action == ACTION_ESCALATE:
            return 2.0
        if action == ACTION_HUMAN_VALIDATION:
            return 1.0
        return -2.0

    if label == "FalsePositive":
        if action == ACTION_CLOSE:
            return 1.5
        if action == ACTION_HUMAN_VALIDATION:
            return 0.25
        return -2.0

    if label == "BenignPositive":
        if action == ACTION_CLOSE:
            return 1.5
        if action == ACTION_HUMAN_VALIDATION:
            return 0.25
        return -2.0

    # Real but semantically unknown class:
    # do not fabricate a security outcome.
    return 0.0
