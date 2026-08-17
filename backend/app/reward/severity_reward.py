"""Reward calculation using the verified real IncidentGrade mapping."""

from dataclasses import dataclass
from typing import Any, Dict

from .real_reward import reward_for, grade_from_numeric


@dataclass
class SeverityReward:

    def compute(
        self,
        incident: Dict[str, Any],
        action: int,
    ) -> float:

        raw_grade = incident.get("IncidentGrade")

        if raw_grade is None:
            raise ValueError(
                "IncidentGrade is required for historical reward calculation."
            )

        if isinstance(raw_grade, str):
            grade = raw_grade.strip()
        else:
            grade = grade_from_numeric(int(raw_grade))

        return reward_for(grade, int(action))
