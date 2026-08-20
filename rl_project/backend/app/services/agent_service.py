"""Inference service backed by the trained RL model."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from app.rl_agent.dqn import DQNAgent

from app.environment.triage_env import (
    OBSERVATION_COLUMNS,
)

from app.environment.action_space import (
    ACTION_NAMES,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[3]

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "real_dqn_agent.pt"
)

_agent = None


def _load_agent():
    global _agent

    if _agent is not None:
        return _agent

    if not MODEL_PATH.exists():
        raise RuntimeError(
            "No trained RL model exists. "
            "Train the agent first."
        )

    checkpoint = torch.load(
        MODEL_PATH,
        map_location="cpu",
    )

    _agent = DQNAgent(
        state_dim=int(
            checkpoint["state_dim"]
        ),
        action_dim=int(
            checkpoint["action_dim"]
        ),
    )

    _agent.model.load_state_dict(
        checkpoint["state_dict"]
    )

    _agent.target_model.load_state_dict(
        checkpoint[
            "target_state_dict"
        ]
    )

    return _agent


def get_agent_status():
    return {
        "status": (
            "trained"
            if MODEL_PATH.exists()
            else "not_trained"
        ),
        "model_path": str(
            MODEL_PATH
        ),
        "observation_columns":
            OBSERVATION_COLUMNS,
        "action_space":
            ACTION_NAMES,
    }


def act_on_event(event):
    agent = _load_agent()

    missing = [
        column
        for column in OBSERVATION_COLUMNS
        if column not in event
    ]

    if missing:
        raise ValueError(
            f"Missing observation fields: "
            f"{missing}"
        )

    state = np.asarray(
        [
            float(event[column])
            for column in OBSERVATION_COLUMNS
        ],
        dtype=np.float32,
    )

    action = agent.act(
        state,
        evaluate=True,
    )

    return {
        "action_id": action,
        "action":
            ACTION_NAMES[action],
        "model":
            str(MODEL_PATH),
        "observation_columns":
            OBSERVATION_COLUMNS,
    }
