"""Tests for reward semantics derived from the processed dataset."""

import pytest

from app.reward.outcomes import CLOSE, ESCALATE, HUMAN_REVIEW, expected_action, historical_outcome_reward


@pytest.mark.parametrize(
    ("incident_grade", "action", "expected"),
    [
        (0, CLOSE, 8.0),
        (1, CLOSE, 8.0),
        (2, ESCALATE, 20.0),
        (3, HUMAN_REVIEW, 3.0),
    ],
)
def test_historical_reward_matches_expected_action(incident_grade, action, expected):
    assert historical_outcome_reward(incident_grade, action) == expected


def test_expected_action_uses_dataset_target_encoding():
    assert expected_action(2) == ESCALATE
    assert expected_action(3) == HUMAN_REVIEW


def test_invalid_action_is_rejected():
    with pytest.raises(ValueError):
        historical_outcome_reward(2, 99)
