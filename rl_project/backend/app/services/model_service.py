"""Validated DQN model lifecycle and inference service."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import torch

from app.config.settings import settings
from app.data_pipeline.contract import (
    FEATURE_COLUMNS,
    SCHEMA_VERSION,
    feature_schema,
    observation_from_alert,
)
from app.reward.outcomes import ACTION_NAMES
from app.rl_agent.dqn import DoubleDQN


logger = logging.getLogger(__name__)

ALGORITHM = "dqn"
ACTION_DIM = len(ACTION_NAMES)
STATE_DIM = len(FEATURE_COLUMNS)


class ModelUnavailableError(RuntimeError):
    """The model cannot safely serve an inference request."""


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, Path):
        return str(value)

    raise TypeError(
        f"Unsupported model metadata value: {type(value).__name__}"
    )


def _artifact_paths() -> tuple[Path, Path]:
    return settings.model_path, settings.model_metadata_path


def _read_metadata() -> dict[str, Any]:
    _, metadata_path = _artifact_paths()

    try:
        with metadata_path.open(encoding="utf-8") as file:
            metadata = json.load(file)

    except FileNotFoundError:
        # The real DQN artifact predates the metadata service.
        # We therefore create safe metadata from the authoritative
        # project contract rather than fabricating evaluation metrics.
        return {
            "model_version": "real-dqn-artifact",
            "trained_at": None,
            "algorithm": ALGORITHM,
            "feature_schema_version": SCHEMA_VERSION,
            "feature_schema": feature_schema(),
            "state_dim": STATE_DIM,
            "action_dim": ACTION_DIM,
            "actions": ACTION_NAMES,
            "training": None,
            "evaluation": None,
        }

    except (OSError, json.JSONDecodeError) as exc:
        raise ModelUnavailableError(
            f"Model metadata cannot be read: {exc}"
        ) from exc

    expected = {
        "algorithm": ALGORITHM,
        "feature_schema_version": SCHEMA_VERSION,
        "state_dim": STATE_DIM,
        "action_dim": ACTION_DIM,
    }

    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ModelUnavailableError(
                f"Model metadata has incompatible {key}: "
                f"{metadata.get(key)!r}"
            )

    return metadata


def _build_agent() -> DoubleDQN:
    return DoubleDQN(
        input_dim=STATE_DIM,
        n_actions=ACTION_DIM,
        learning_rate=1e-3,
        gamma=0.95,
        hidden_dim=128,
        device="cpu",
    )


@lru_cache(maxsize=1)
def _load_model_cached(
    model_mtime_ns: int,
    metadata_mtime_ns: int,
) -> tuple[DoubleDQN, dict[str, Any]]:

    del model_mtime_ns
    del metadata_mtime_ns

    model_path, _ = _artifact_paths()

    metadata = _read_metadata()

    if not model_path.is_file():
        raise ModelUnavailableError(
            "No trained model artifact is available"
        )

    try:
        agent = _build_agent()

        # Load the authoritative DoubleDQN checkpoint.
        agent.load(str(model_path))

        agent.online.eval()
        agent.target.eval()

    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:

        raise ModelUnavailableError(
            f"Trained DQN model cannot be loaded: {exc}"
        ) from exc

    return agent, metadata


def load_model() -> tuple[DoubleDQN, dict[str, Any]]:
    model_path, metadata_path = _artifact_paths()

    if not model_path.is_file():
        raise ModelUnavailableError(
            "No trained model artifact is available"
        )

    # Metadata is optional for the already verified real artifact.
    metadata_mtime_ns = (
        metadata_path.stat().st_mtime_ns
        if metadata_path.is_file()
        else 0
    )

    return _load_model_cached(
        model_path.stat().st_mtime_ns,
        metadata_mtime_ns,
    )


def invalidate_model_cache() -> None:
    _load_model_cached.cache_clear()


def save_trained_model(
    model: DoubleDQN,
    *,
    training_metadata: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:

    model_path, metadata_path = _artifact_paths()

    model_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata = {
        "model_version": datetime.now(UTC).strftime(
            "dqn-%Y%m%dT%H%M%SZ"
        ),
        "trained_at": datetime.now(UTC).isoformat(),
        "algorithm": ALGORITHM,
        "feature_schema_version": SCHEMA_VERSION,
        "feature_schema": feature_schema(),
        "state_dim": STATE_DIM,
        "action_dim": ACTION_DIM,
        "actions": ACTION_NAMES,
        "training": training_metadata,
        "evaluation": evaluation,
    }

    temporary_model = model_path.with_suffix(
        model_path.suffix + ".tmp"
    )

    temporary_metadata = metadata_path.with_suffix(
        metadata_path.suffix + ".tmp"
    )

    try:

        model.save(str(temporary_model))

        temporary_metadata.write_text(
            json.dumps(
                metadata,
                indent=2,
                sort_keys=True,
                default=_json_default,
            ),
            encoding="utf-8",
        )

        os.replace(
            temporary_model,
            model_path,
        )

        os.replace(
            temporary_metadata,
            metadata_path,
        )

    finally:

        for path in (
            temporary_model,
            temporary_metadata,
        ):

            if path.exists():
                path.unlink(
                    missing_ok=True
                )

    invalidate_model_cache()

    logger.info(
        "Saved trained DQN model version %s",
        metadata["model_version"],
    )

    return metadata


def get_model_status() -> dict[str, Any]:

    model_path, metadata_path = _artifact_paths()

    base = {
        "algorithm": ALGORITHM,
        "feature_schema_version": SCHEMA_VERSION,
        "state_dim": STATE_DIM,
        "action_dim": ACTION_DIM,
        "actions": ACTION_NAMES,
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
    }

    if not model_path.is_file():

        return {
            **base,
            "status": "UNAVAILABLE",
            "message": (
                "No trained model artifact is available."
            ),
        }

    try:

        _, metadata = load_model()

    except ModelUnavailableError as exc:

        return {
            **base,
            "status": "ERROR",
            "message": str(exc),
        }

    return {
        **base,
        "status": "READY",
        "model_version": metadata.get(
            "model_version"
        ),
        "trained_at": metadata.get(
            "trained_at"
        ),
        "evaluation": metadata.get(
            "evaluation"
        ),
        "training": metadata.get(
            "training"
        ),
    }


def predict(
    alert: dict[str, Any],
) -> dict[str, Any]:

    agent, metadata = load_model()

    observation = observation_from_alert(
        alert
    )

    observation_array = np.asarray(
        observation,
        dtype=np.float32,
    )

    if observation_array.shape != (
        STATE_DIM,
    ):
        raise ModelUnavailableError(
            "Observation dimension mismatch: "
            f"expected {STATE_DIM}, "
            f"got {observation_array.shape}"
        )

    started = perf_counter()

    with torch.no_grad():

        x = torch.as_tensor(
            observation_array,
            dtype=torch.float32,
            device=agent.device,
        ).unsqueeze(0)

        scores_tensor = agent.online(
            x
        ).squeeze(0)

        probabilities = torch.softmax(
            scores_tensor,
            dim=0,
        )

        action = int(
            torch.argmax(
                scores_tensor
            ).item()
        )

    latency_ms = (
        perf_counter() - started
    ) * 1000

    return {
        "action_index": action,
        "action": ACTION_NAMES[action],
        "confidence": round(
            float(
                probabilities[action].item()
            ),
            6,
        ),
        "model_version": metadata.get(
            "model_version",
            "real-dqn-artifact",
        ),
        "feature_schema_version": (
            SCHEMA_VERSION
        ),
        "inference_latency_ms": round(
            latency_ms,
            3,
        ),
        "recommendation_status": (
            "PENDING_HUMAN_VALIDATION"
        ),
        "execution_status": (
            "NOT_EXECUTED"
        ),
        "observation": (
            observation_array
            .astype(float)
            .round(8)
            .tolist()
        ),
    }