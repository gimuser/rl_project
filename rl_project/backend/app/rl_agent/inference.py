from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .dqn import DoubleDQN
from .triage_env import ACTIONS, FEATURES


def predict_dataframe(
    df: pd.DataFrame,
    model_path: str = "models/real_dqn_agent.pt",
):

    missing = [
        x
        for x in FEATURES
        if x not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing features: {missing}"
        )

    model = DoubleDQN(
        input_dim=len(FEATURES),
        n_actions=len(ACTIONS),
        gamma=0.95,
    )

    model.load(model_path)

    states = df[
        FEATURES
    ].astype(
        np.float32
    ).values

    q = model.q_values(
        states
    )

    actions = q.argmax(
        axis=1
    )

    result = df.copy()

    result["action"] = actions

    result["action_name"] = [
        ACTIONS[int(x)]
        for x in actions
    ]

    result["q_allow"] = q[:, 0]
    result["q_block"] = q[:, 1]
    result["q_human_review"] = q[:, 2]

    return result


def predict_csv(
    csv_path: str,
    output_path: str = "models/new_data_predictions.csv",
    model_path: str = "models/real_dqn_agent.pt",
):

    df = pd.read_csv(csv_path)

    result = predict_dataframe(
        df,
        model_path=model_path,
    )

    Path(
        output_path
    ).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        output_path,
        index=False,
    )

    return result
