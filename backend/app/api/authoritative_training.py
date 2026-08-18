from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.authoritative_training_control import models, start, status
from app.services.force_training_stop import stop as force_stop
from app.services.training_history import archive_current_run, list_runs, load_run

router = APIRouter(prefix="/api/training-control", tags=["Authoritative Training Control"])


class TrainingStartRequest(BaseModel):
    model_names: list[str] = Field(default_factory=list)
    training: dict[str, Any] = Field(default_factory=dict)
    model_configs: list[dict[str, Any]] = Field(default_factory=list)
    rewards: dict[str, dict[str, float]] = Field(default_factory=dict)


def _finite_number(value: Any, *, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid numeric value for {name}: {value}") from exc
    if not (-1e12 < parsed < 1e12):
        raise HTTPException(status_code=400, detail=f"Out-of-range value for {name}: {value}")
    return parsed


def _bounded_int(value: Any, *, name: str, low: int, high: int) -> int:
    parsed = int(_finite_number(value, name=name))
    if parsed < low or parsed > high:
        raise HTTPException(status_code=400, detail=f"{name} must be between {low} and {high}.")
    return parsed


def _bounded_float(value: Any, *, name: str, low: float, high: float) -> float:
    parsed = _finite_number(value, name=name)
    if parsed < low or parsed > high:
        raise HTTPException(status_code=400, detail=f"{name} must be between {low} and {high}.")
    return parsed


def _prepare_training_environment(request: TrainingStartRequest) -> tuple[dict[str, str], dict[str, str | None]]:
    """Validate and temporarily expose UI-selected parameters to the trainer subprocess."""
    if not request.model_names:
        raise HTTPException(status_code=400, detail="Select at least one model candidate before starting training.")

    available = models().get("models", [])
    available_names = {str(item.get("name")) for item in available}
    unknown = [name for name in request.model_names if name not in available_names]
    if unknown:
        raise HTTPException(status_code=400, detail={"message": "Unknown model candidate(s).", "invalid_models": unknown})

    training_defaults: dict[str, tuple[Any, str]] = {
        "max_epochs": (4000, "REAL_RL_MAX_EPOCHS"),
        "min_epochs": (20, "REAL_RL_MIN_EPOCHS"),
        "patience": (10, "REAL_RL_PATIENCE"),
        "validation_every": (2, "REAL_RL_EVAL_EVERY"),
        "min_delta": (0.001, "REAL_RL_MIN_DELTA"),
        "max_total_updates": (5_000_000, "REAL_RL_MAX_TOTAL_UPDATES"),
        "chunk_size": (100_000, "REAL_RL_CHUNK_SIZE"),
        "train_ratio": (0.80, "REAL_RL_TRAIN_RATIO_WITHIN_TRAIN_VAL"),
        "validation_seed": (4242, "REAL_RL_VALIDATION_SEED"),
        "seed": (42, "REAL_RL_SEED"),
        "target_update": (1, "REAL_RL_TARGET_UPDATE"),
        "metric_sample_rows": (10_000, "REAL_RL_METRIC_SAMPLE_ROWS"),
    }
    env_updates: dict[str, str] = {}

    env_updates["REAL_RL_MAX_EPOCHS"] = str(_bounded_int(request.training.get("max_epochs", training_defaults["max_epochs"][0]), name="max_epochs", low=1, high=100_000))
    env_updates["REAL_RL_MIN_EPOCHS"] = str(_bounded_int(request.training.get("min_epochs", training_defaults["min_epochs"][0]), name="min_epochs", low=1, high=100_000))
    if int(env_updates["REAL_RL_MIN_EPOCHS"]) > int(env_updates["REAL_RL_MAX_EPOCHS"]):
        raise HTTPException(status_code=400, detail="min_epochs cannot exceed max_epochs.")
    env_updates["REAL_RL_PATIENCE"] = str(_bounded_int(request.training.get("patience", training_defaults["patience"][0]), name="patience", low=1, high=10_000))
    env_updates["REAL_RL_EVAL_EVERY"] = str(_bounded_int(request.training.get("validation_every", training_defaults["validation_every"][0]), name="validation_every", low=1, high=10_000))
    env_updates["REAL_RL_MIN_DELTA"] = str(_bounded_float(request.training.get("min_delta", training_defaults["min_delta"][0]), name="min_delta", low=0.0, high=10.0))
    env_updates["REAL_RL_MAX_TOTAL_UPDATES"] = str(_bounded_int(request.training.get("max_total_updates", training_defaults["max_total_updates"][0]), name="max_total_updates", low=1, high=100_000_000))
    env_updates["REAL_RL_CHUNK_SIZE"] = str(_bounded_int(request.training.get("chunk_size", training_defaults["chunk_size"][0]), name="chunk_size", low=1_000, high=1_000_000))
    env_updates["REAL_RL_TRAIN_RATIO_WITHIN_TRAIN_VAL"] = str(_bounded_float(request.training.get("train_ratio", training_defaults["train_ratio"][0]), name="train_ratio", low=0.50, high=0.95))
    env_updates["REAL_RL_VALIDATION_SEED"] = str(_bounded_int(request.training.get("validation_seed", training_defaults["validation_seed"][0]), name="validation_seed", low=0, high=2_147_483_647))
    env_updates["REAL_RL_SEED"] = str(_bounded_int(request.training.get("seed", training_defaults["seed"][0]), name="seed", low=0, high=2_147_483_647))
    env_updates["REAL_RL_TARGET_UPDATE"] = str(_bounded_int(request.training.get("target_update", training_defaults["target_update"][0]), name="target_update", low=1, high=10_000))
    env_updates["REAL_RL_METRIC_SAMPLE_ROWS"] = str(_bounded_int(request.training.get("metric_sample_rows", training_defaults["metric_sample_rows"][0]), name="metric_sample_rows", low=0, high=1_000_000))

    model_configs: list[dict[str, Any]] = []
    algorithm_params: dict[str, dict[str, Any]] = {}
    requested = {str(cfg.get("name")): cfg for cfg in request.model_configs}

    for name in request.model_names:
        base = next((dict(item) for item in available if str(item.get("name")) == name), {"name": name, "algorithm": name})
        cfg = {**base, **requested.get(name, {})}
        cfg["name"] = name
        cfg["algorithm"] = str(cfg.get("algorithm", name))
        cfg["learning_rate"] = _bounded_float(cfg.get("learning_rate", 0.001), name=f"{name}.learning_rate", low=1e-7, high=1.0)
        cfg["gamma"] = _bounded_float(cfg.get("gamma", 0.95), name=f"{name}.gamma", low=0.0, high=1.0)
        cfg["batch_size"] = _bounded_int(cfg.get("batch_size", 2048), name=f"{name}.batch_size", low=32, high=16_384)
        cfg["max_total_updates"] = _bounded_int(cfg.get("max_total_updates", env_updates["REAL_RL_MAX_TOTAL_UPDATES"]), name=f"{name}.max_total_updates", low=1, high=100_000_000)
        cfg["hidden_dim"] = _bounded_int(cfg.get("hidden_dim", 128), name=f"{name}.hidden_dim", low=16, high=2048)
        model_configs.append(cfg)
        algorithm_params[name] = {
            "hidden_dim": cfg["hidden_dim"],
            "cql_alpha": _bounded_float(cfg.get("cql_alpha", 1.0), name=f"{name}.cql_alpha", low=0.0, high=100.0),
            "iql_expectile": _bounded_float(cfg.get("iql_expectile", 0.7), name=f"{name}.iql_expectile", low=0.01, high=0.99),
            "iql_beta": _bounded_float(cfg.get("iql_beta", 3.0), name=f"{name}.iql_beta", low=0.01, high=100.0),
            "bcq_threshold": _bounded_float(cfg.get("bcq_threshold", 0.05), name=f"{name}.bcq_threshold", low=0.0, high=1.0),
        }

    if request.rewards:
        env_updates["REAL_RL_REWARD_OVERRIDES"] = json.dumps(request.rewards, separators=(",", ":"))

    env_updates["REAL_RL_EXPERIMENTS"] = json.dumps(model_configs, separators=(",", ":"))
    env_updates["REAL_RL_ALGORITHM_PARAMS_JSON"] = json.dumps(algorithm_params, separators=(",", ":"))
    env_updates["REAL_RL_CONFIG_SNAPSHOT"] = json.dumps({"training": request.training, "model_configs": model_configs, "rewards": request.rewards}, default=str, separators=(",", ":"))

    previous: dict[str, str | None] = {key: os.environ.get(key) for key in env_updates}
    return env_updates, previous


def _start_with_config(request: TrainingStartRequest):
    env_updates, previous = _prepare_training_environment(request)
    try:
        # Preserve every completed run before the next run replaces the active files.
        archive_current_run()
        os.environ.update(env_updates)
        return start(request.model_names)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@router.get("/models")
def get_training_models():
    return models()


@router.get("/runs")
def get_training_runs():
    return {"runs": list_runs()}


@router.get("/runs/{run_id}")
def get_training_run(run_id: str):
    value = load_run(run_id)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Training run not found: {run_id}")
    return value


@router.post("")
def start_full_training(request: TrainingStartRequest | None = None):
    return _start_with_config(request or TrainingStartRequest())


@router.get("")
def get_full_training_status():
    return status()


@router.post("/stop")
def stop_full_training():
    return force_stop()
