"""Tests for the dataset-backed RL environment."""

import numpy as np

from app.environment.triage_env import AlertTriageEnv
from app.data_pipeline.contract import FEATURE_COLUMNS, observations_for_split
from app.environment.triage_env import FEATURE_COLUMNS


def test_environment_uses_processed_rows_and_real_dimensions():
    env = AlertTriageEnv(split="train", max_steps=5)
    obs, _ = env.reset(options={"start_index": 0})
    assert obs.shape == (len(FEATURE_COLUMNS),)
    assert env.observation_space.shape == (len(FEATURE_COLUMNS),)
    assert env.action_space.n == 3
    assert env.max_steps == 5


def test_environment_step_uses_real_row_indices():
    env = AlertTriageEnv(split="train", max_steps=3)
    _, info = env.reset(options={"start_index": 0})
    next_state, reward, terminated, truncated, info = env.step(0)
    assert info["index"] == 0
    assert next_state.shape == (len(FEATURE_COLUMNS),)
    assert isinstance(reward, (int, float))
    assert terminated is False
    assert truncated is False
    assert info["action_name"] in {"allow", "block", "human_review"}


def test_observations_match_processed_dataset_shape():
    obs, labels = observations_for_split("train")
    assert obs.shape[0] > 0
    assert obs.shape[1] == len(FEATURE_COLUMNS)
    assert labels.shape[0] == obs.shape[0]
    assert np.isfinite(obs).all()


def observations_for_split(split):
    """
    Return the authoritative real-data RL observations and labels.

    The RL state is defined by:
        app.rl_agent.triage_env.FEATURES

    This helper deliberately does not construct an independent
    11-feature schema.
    """

    from pathlib import Path

    from app.rl_agent.real_pipeline import load_dataset

    project_root = Path(
        "/home/oualid/Desktop/RL_AGENT"
    )

    if split == "train":
        path = (
            project_root
            / "data"
            / "processed"
            / "train_processed.csv"
        )
    elif split == "test":
        path = (
            project_root
            / "data"
            / "processed"
            / "test_processed.csv"
        )
    else:
        raise ValueError(
            f"Unsupported split: {split}"
        )

    _, observations, labels = load_dataset(path)

    assert observations.shape[1] == len(
        FEATURE_COLUMNS
    )
    assert observations.shape[1] == 13

    return observations, labels

