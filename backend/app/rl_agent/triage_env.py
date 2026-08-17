from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


FEATURES = [
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

INCIDENT_ID = "IncidentId"
TARGET = "IncidentGrade"

ACTIONS = {
    0: "allow",
    1: "block",
    2: "human_review",
}

LABELS = {
    0: "BenignPositive",
    1: "FalsePositive",
    2: "TruePositive",
    3: "Unknown",
}


REWARD_TABLE = {
    0: {
        0: 1.5,
        1: -1.0,
        2: 0.25,
    },
    1: {
        0: 1.5,
        1: -2.0,
        2: 0.25,
    },
    2: {
        0: -2.0,
        1: 2.0,
        2: 1.0,
    },
    3: {
        0: -1.0,
        1: 0.5,
        2: 1.5,
    },
}


def find_timestamp_column(df: pd.DataFrame) -> Optional[str]:

    candidates = [
        "Timestamp",
        "timestamp",
        "TimeStamp",
        "EventTime",
        "event_time",
        "CreatedTime",
        "CreatedAt",
        "Date",
        "date",
        "Time",
        "time",
    ]

    for c in candidates:
        if c in df.columns:
            return c

    return None


def sort_incidents(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Optional[str]]:

    timestamp_col = find_timestamp_column(df)

    if timestamp_col is not None:

        parsed = pd.to_datetime(
            df[timestamp_col],
            errors="coerce",
            utc=True,
        )

        df = df.copy()
        df["_rl_timestamp"] = parsed

        df = df.sort_values(
            [INCIDENT_ID, "_rl_timestamp"],
            kind="stable",
        )

        return df, timestamp_col

    # No timestamp:
    # preserve original source order.
    df = df.copy()
    df["_rl_original_order"] = np.arange(len(df))

    df = df.sort_values(
        [INCIDENT_ID, "_rl_original_order"],
        kind="stable",
    )

    return df, None


def reward_for(
    label: int,
    action: int,
) -> float:

    return float(
        REWARD_TABLE.get(
            int(label),
            REWARD_TABLE[3],
        ).get(
            int(action),
            0.0,
        )
    )


def make_transitions(
    df: pd.DataFrame,
) -> List[Tuple]:

    """
    Create real transitions inside each IncidentId.

    Important:
    IncidentId is the episode boundary and is NOT a state feature.
    """

    df, timestamp_col = sort_incidents(df)

    transitions = []

    for incident_id, group in df.groupby(
        INCIDENT_ID,
        sort=False,
    ):

        rows = group.reset_index(drop=True)

        states = rows[FEATURES].astype(np.float32).values

        labels = rows[TARGET].astype(int).values

        n = len(rows)

        for i in range(n):

            next_state = (
                states[i + 1]
                if i + 1 < n
                else states[i]
            )

            done = i == n - 1

            # Action used here is the behavior/observed action
            # only if an action column exists.
            action = None

            for action_col in [
                "Action",
                "action",
                "AgentAction",
                "agent_action",
            ]:
                if action_col in rows.columns:
                    action = rows.iloc[i][action_col]
                    break

            if action is None:
                # Historical offline dataset has no recorded agent
                # action. We generate all possible candidate actions
                # during training/evaluation instead of pretending
                # there was a real historical action.
                continue

            try:
                action = int(action)
            except Exception:
                continue

            if action not in ACTIONS:
                continue

            reward = reward_for(
                labels[i],
                action,
            )

            transitions.append(
                (
                    states[i],
                    action,
                    reward,
                    next_state,
                    done,
                    str(incident_id),
                    int(labels[i]),
                    i,
                )
            )

    return transitions


def make_offline_transition_table(
    df: pd.DataFrame,
) -> pd.DataFrame:

    """
    Build transitions where every possible action is evaluated
    against the historical IncidentGrade.

    This is useful when the dataset contains no historical agent action.
    """

    df, timestamp_col = sort_incidents(df)

    records = []

    for incident_id, group in df.groupby(
        INCIDENT_ID,
        sort=False,
    ):

        rows = group.reset_index(drop=True)

        states = rows[FEATURES].astype(np.float32).values
        labels = rows[TARGET].astype(int).values

        for i in range(len(rows)):

            next_state = (
                states[i + 1]
                if i + 1 < len(rows)
                else states[i]
            )

            done = i == len(rows) - 1

            for action in ACTIONS:

                records.append(
                    {
                        "IncidentId": str(incident_id),
                        "step": i,
                        "action": action,
                        "label": int(labels[i]),
                        "reward": reward_for(
                            int(labels[i]),
                            action,
                        ),
                        "done": bool(done),
                        "state": states[i],
                        "next_state": next_state,
                    }
                )

    return pd.DataFrame(records)


def incident_split(
    df: pd.DataFrame,
    train_ratio: float = 0.8,
    seed: int = 42,
):

    incidents = (
        df[INCIDENT_ID]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .values
    )

    rng = np.random.default_rng(seed)

    incidents = incidents.copy()
    rng.shuffle(incidents)

    n_train = int(
        len(incidents) * train_ratio
    )

    train_ids = set(
        incidents[:n_train]
    )

    test_ids = set(
        incidents[n_train:]
    )

    train = df[
        df[INCIDENT_ID]
        .astype(str)
        .isin(train_ids)
    ].copy()

    test = df[
        df[INCIDENT_ID]
        .astype(str)
        .isin(test_ids)
    ].copy()

    overlap = (
        set(train[INCIDENT_ID].astype(str))
        &
        set(test[INCIDENT_ID].astype(str))
    )

    if overlap:
        raise RuntimeError(
            f"Incident leakage detected: {len(overlap)} overlapping incidents"
        )

    return train, test


def save_split_report(
    train: pd.DataFrame,
    test: pd.DataFrame,
    path: str,
):

    report = {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_incidents": int(
            train[INCIDENT_ID].astype(str).nunique()
        ),
        "test_incidents": int(
            test[INCIDENT_ID].astype(str).nunique()
        ),
        "incident_overlap": int(
            len(
                set(train[INCIDENT_ID].astype(str))
                &
                set(test[INCIDENT_ID].astype(str))
            )
        ),
        "features": FEATURES,
        "incident_id": INCIDENT_ID,
        "target": TARGET,
    }

    Path(path).write_text(
        json.dumps(
            report,
            indent=2,
        )
    )
