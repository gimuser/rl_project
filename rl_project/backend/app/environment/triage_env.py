"""Application triage environment backed by the real processed data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import gymnasium as gym
from gymnasium import spaces

FEATURE_COLUMNS = [
    "Category",
    "MitreTechniques",
    "ActionGrouped",
    "ActionGranular",
    "EntityType",
    "EvidenceRole",
    "ThreatFamily",
    "OSFamily",
    "SuspicionLevel",
    "hour",
    "day",
    "month",
    "is_weekend",
]

from app.rl_agent.real_pipeline import (
    TRAIN_PATH,
    TEST_PATH,
    load_dataset,
    reward_matrix,
    apply_normalization,
    fit_normalization,
)


class RealTriageEnv(gym.Env):

    metadata = {
        "render_modes": []
    }

    def __init__(
        self,
        split="train",
        max_steps=None,
    ):

        super().__init__()

        if split == "train":

            path = TRAIN_PATH

        elif split == "test":

            path = TEST_PATH

        else:

            raise ValueError(
                "split must be 'train' or 'test'"
            )

        _, raw_X, labels = (
            load_dataset(path)
        )

        # Environment normalization is fitted on the selected
        # split only for compatibility.
        normalization = fit_normalization(
            raw_X
        )

        self.states = apply_normalization(
            raw_X,
            normalization,
        )

        self.labels = labels

        self.rewards = reward_matrix(
            labels
        )

        self.index = 0

        self.max_steps = (
            max_steps
        )

        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(
                self.states.shape[1],
            ),
            dtype=np.float32,
        )

        self.action_space = spaces.Discrete(
            3
        )

    def reset(
        self,
        *,
        seed=None,
        options=None,
    ):

        super().reset(
            seed=seed
        )

        self.index = 0

        return (
            self.states[
                self.index
            ],
            {},
        )

    def step(
        self,
        action,
    ):

        action = int(action)

        if not self.action_space.contains(
            action
        ):
            raise ValueError(
                f"Invalid action: {action}"
            )

        current_index = self.index

        reward = float(
            self.rewards[
                current_index,
                action,
            ]
        )

        self.index += 1

        terminated = (
            self.index
            >= len(self.states)
        )

        if (
            self.max_steps is not None
            and self.index
            >= self.max_steps
        ):
            terminated = True

        if terminated:

            next_state = np.zeros(
                self.states.shape[1],
                dtype=np.float32,
            )

        else:

            next_state = self.states[
                self.index
            ]

        action_name = {
            0: "allow",
            1: "block",
            2: "human_review",
        }[action]

        info = {
            "index": current_index,
            "row_index": current_index,
            "action_name": action_name,
            "incident_grade":
                int(
                    self.labels[
                        current_index
                    ]
                ),
        }

        return (
            next_state,
            reward,
            terminated,
            False,
            info,
        )


TriageEnv = RealTriageEnv
AlertTriageEnv = RealTriageEnv

OBSERVATION_COLUMNS = []
