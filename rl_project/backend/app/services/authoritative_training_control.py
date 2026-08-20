from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
TRAIN_METRICS = MODELS_DIR / "training_metrics.json"
TEST_METRICS = MODELS_DIR / "real_test_metrics.json"
COMPARISON = MODELS_DIR / "model_comparison.json"
INFERENCE = MODELS_DIR / "live_inference.json"
RUN_STATE = MODELS_DIR / "training_run.json"
PROGRESS = MODELS_DIR / "training_progress.json"
SPLIT_REPORT = PROJECT_ROOT / "data" / "rl_incident" / "split_report.json"
MODEL_PATH = MODELS_DIR / "real_dqn_agent.pt"
LOG_PATH = MODELS_DIR / "full_real_training.log"

_lock = Lock()
_process: subprocess.Popen[str] | None = None
_log_handle = None
_started_at: str | None = None
_last_return_code: int | None = None
_last_message = ""
_post_training: dict[str, Any] | None = None
_selected_models: list[str] = []
_run_id: str | None = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, float): return value if math.isfinite(value) else None
    if isinstance(value, dict): return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_json_safe(v) for v in value]
    return value


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists(): return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return _json_safe(value) if isinstance(value, dict) else None
    except Exception:
        return None


def _write_run_state(**updates: Any) -> dict[str, Any]:
    # A new run must NEVER inherit stopped_at/finished_at/return_code
    # from a previous experiment.
    if updates.get("status") == "starting":
        current: dict[str, Any] = {}
    else:
        current = _load_json(RUN_STATE) or {}

    current.update(_json_safe(updates))

    RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
    RUN_STATE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def _history() -> list[dict[str, Any]]:
    data = _load_json(TRAIN_METRICS) or {}
    raw = data.get("metrics")
    if not isinstance(raw, list): return []
    output = []
    for item in raw:
        if not isinstance(item, dict): continue
        if not isinstance(item.get("epoch"), (int, float)) or not isinstance(item.get("loss"), (int, float)): continue
        output.append({
            "epoch": item["epoch"], "loss": item["loss"], "avg_reward": item.get("average_reward"),
            "policy_reward": item.get("policy_reward", item.get("average_reward")),
            "oracle_average_reward": item.get("oracle_average_reward"), "reward_efficiency": item.get("reward_efficiency"),
            "updates": item.get("updates"), "total_updates": item.get("total_updates"), "updates_per_epoch": item.get("updates_per_epoch"),
            "rows": item.get("rows"), "incidents": item.get("incidents"), "action_distribution": item.get("action_distribution") or item.get("action_counts"),
            "time_seconds": item.get("time_seconds"), "validation": item.get("validation"), "validation_score": item.get("validation_score"),
            "best_epoch": item.get("best_epoch"), "patience_used": item.get("patience_used"), "improved": item.get("improved"),
            "stopping_reason": item.get("stopping_reason"), "run_id": item.get("run_id"), "algorithm": item.get("algorithm"),
        })
    return output


def _available_models() -> list[dict[str, Any]]:
    from app.rl_agent.real_pipeline import _experiment_configs
    from app.rl_agent.offline_algorithms import algorithm_metadata
    return [{**cfg, **algorithm_metadata(str(cfg.get("algorithm", cfg.get("name", "double_dqn"))))} for cfg in _experiment_configs()]


def models() -> dict[str, Any]:
    items = _available_models()
    return {"models": items, "count": len(items)}


def _orphan_pids() -> list[int]:
    try:
        out = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if "app.rl_agent.sequential_experiment" not in line or "grep" in line: continue
        try: pids.append(int(line.split(None, 1)[0]))
        except Exception: pass
    return pids


def _sync_process_state() -> None:
    global _process, _log_handle, _last_return_code, _last_message, _post_training
    if _process is None: return
    code = _process.poll()
    if code is None: return
    _last_return_code = code
    if code == 0:
        _last_message = "Selected model training and live evaluation completed."
        try:
            from app.services.post_training_service import promote_and_infer
            _post_training = promote_and_infer()
            if _post_training.get("status") == "completed": _last_message = "Selected models evaluated; champion versioned and final live cycle routed."
        except Exception as exc:
            _post_training = {"status": "post_training_failed", "error": str(exc)}
            _last_message = "Training completed, but final post-training inference failed."
    elif code < 0:
        _last_message = f"Training process terminated by signal {-code}."
    else:
        _last_message = f"Training process exited with return code {code}."
    _write_run_state(status="completed" if code == 0 else "stopped" if code < 0 else "failed", return_code=code, finished_at=datetime.now(timezone.utc).isoformat())
    if _log_handle:
        try: _log_handle.close()
        except Exception: pass
        _log_handle = None
    _process = None


def start(model_names: list[str] | None = None) -> dict[str, Any]:
    global _process, _log_handle, _started_at, _last_return_code, _last_message, _post_training, _selected_models, _run_id
    with _lock:
        _sync_process_state()
        orphans = _orphan_pids()
        if _process is not None and _process.poll() is None:
            raise HTTPException(status_code=409, detail={"message": "A training experiment is already running.", "pid": _process.pid, "selected_models": _selected_models})
        if orphans:
            raise HTTPException(status_code=409, detail={"message": "An orphaned sequential training process is still running. Stop it before starting another experiment.", "orphan_pids": orphans})
        available = _available_models()
        by_name = {str(item.get("name")): item for item in available}
        selected = [str(n) for n in (model_names or []) if str(n) in by_name]
        invalid = [str(n) for n in (model_names or []) if str(n) not in by_name]
        if invalid:
            raise HTTPException(status_code=400, detail={"message": "Unknown model candidate(s).", "invalid_models": invalid, "available_models": sorted(by_name)})
        if not selected:
            raise HTTPException(status_code=400, detail={"message": "Select at least one model candidate before starting training.", "available_models": sorted(by_name)})

        _selected_models = selected
        _run_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc).isoformat()
        _started_at = started_at
        _last_return_code = None
        _last_message = "Selected models started with isolated telemetry and adaptive stopping."
        _post_training = None

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        TRAIN_METRICS.write_text(json.dumps({"config": {"run_id": _run_id, "selected_models": selected, "status": "starting"}, "metrics": []}, indent=2), encoding="utf-8")
        COMPARISON.write_text(json.dumps({"status": "starting", "run_id": _run_id, "selected_models": selected, "candidates": [], "best": None}, indent=2), encoding="utf-8")
        TEST_METRICS.write_text(json.dumps({}, indent=2), encoding="utf-8")
        INFERENCE.write_text(json.dumps({"status": "idle", "run_id": _run_id, "alerts_considered": 0, "alerts_processed": 0, "human_review_routed": 0, "action_distribution": {}}, indent=2), encoding="utf-8")
        PROGRESS.write_text(json.dumps({"status": "starting", "stage": "starting", "algorithm": None, "display_name": None, "epoch": 0, "epochs": 0, "completed_epochs": 0, "source_rows_processed": 0, "source_rows_total": 0, "progress_percent": 0.0, "chunks_processed": 0, "chunks_total": 0, "filtered_train_rows_processed": 0, "updates": 0, "total_updates": 0, "run_id": _run_id, "updated_at": time.time()}, indent=2), encoding="utf-8")
        _write_run_state(run_id=_run_id, status="starting", selected_models=selected, started_at=started_at, pid=None)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "backend") + os.pathsep + env.get("PYTHONPATH", "")
        env["REAL_RL_EXPERIMENTS"] = json.dumps([by_name[n] for n in selected])
        env["REAL_RL_RUN_ID"] = _run_id
        env["REAL_RL_PROGRESS_PATH"] = str(PROGRESS)
        env.setdefault("RL_TORCH_THREADS", "2")
        env.setdefault("OMP_NUM_THREADS", "2")
        env.setdefault("MKL_NUM_THREADS", "2")
        env.setdefault("OPENBLAS_NUM_THREADS", "2")

        _log_handle = LOG_PATH.open("w", encoding="utf-8")
        _process = subprocess.Popen([sys.executable, "-m", "app.rl_agent.sequential_experiment"], cwd=str(PROJECT_ROOT / "backend"), env=env, stdout=_log_handle, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        _write_run_state(pid=_process.pid, status="running")
        _last_message = f"Training run {_run_id} started for: {', '.join(selected)}"
        return {"status": "started", "message": _last_message, "pid": _process.pid, "started_at": _started_at, "run_id": _run_id, "selected_models": _selected_models}


def stop() -> dict[str, Any]:
    global _process, _log_handle, _last_message, _last_return_code
    with _lock:
        _sync_process_state()
        killed: list[int] = []
        if _process is not None and _process.poll() is None:
            pid = _process.pid
            try: os.killpg(os.getpgid(pid), signal.SIGTERM); killed.append(pid)
            except Exception:
                try: _process.terminate(); killed.append(pid)
                except Exception: pass
            try: _process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                try: os.killpg(os.getpgid(pid), signal.SIGKILL)
                except Exception:
                    try: _process.kill()
                    except Exception: pass
                try: _process.wait(timeout=3)
                except Exception: pass
            _last_return_code = _process.returncode
            _process = None
        for pid in _orphan_pids():
            try: os.kill(pid, signal.SIGTERM); killed.append(pid)
            except ProcessLookupError: pass
            except Exception: pass
        if _log_handle:
            try: _log_handle.close()
            except Exception: pass
            _log_handle = None
        _last_message = "Training stop requested; all managed/orphan sequential training processes were terminated."
        PROGRESS.write_text(json.dumps({"status": "stopped", "stage": "stopped", "run_id": _run_id, "updated_at": time.time()}, indent=2), encoding="utf-8")
        _write_run_state(status="stopped", stopped_at=datetime.now(timezone.utc).isoformat(), return_code=_last_return_code)
        return {"status": "stopped", "message": _last_message, "terminated_pids": sorted(set(killed))}


def status() -> dict[str, Any]:
    with _lock:
        try:
            _sync_process_state()
            run_state = _load_json(RUN_STATE) or {}
            running = _process is not None and _process.poll() is None
            training = _load_json(TRAIN_METRICS) or {}
            progress = _load_json(PROGRESS) or {}
            testing = _load_json(TEST_METRICS) or {}
            comparison = _load_json(COMPARISON) or {}
            split = _load_json(SPLIT_REPORT) or {}
            inference = _load_json(INFERENCE) or {}
            config = training.get("config") if isinstance(training.get("config"), dict) else {}
            same_run = bool(run_state.get("run_id")) and run_state.get("run_id") == config.get("run_id")
            history = _history() if same_run else []
            last = history[-1] if history else {}

            if running:
                state, message = "running", f"Selected models are training: {', '.join(_selected_models)}"
            elif _last_return_code == 0:
                state, message = "completed", _last_message
            elif _last_return_code is not None:
                state, message = ("stopped" if "stop" in _last_message.lower() else "failed"), _last_message
            elif history:
                state, message = "completed", "Persisted training results available."
            else:
                state, message = "idle", "No managed training experiment is running."

            if running and not same_run:
                config = {"run_id": run_state.get("run_id"), "selected_models": _selected_models, "status": "starting"}
                training = {"metrics": []}

            results = {
                "dataset": {"name": "train_processed.csv", "train_rows": split.get("train_rows"), "validation_rows": split.get("validation_rows"), "test_rows": split.get("test_rows"), "train_incidents": split.get("train_incidents"), "validation_incidents": split.get("validation_incidents"), "test_incidents": split.get("test_incidents"), "incident_overlap": split.get("incident_overlap"), "features": split.get("features"), "feature_count": len(split.get("features", [])) if isinstance(split.get("features"), list) else None, "synthetic_data": False, "unseen_incidents": True},
                "training": {"run_id": run_state.get("run_id"), "model_name": config.get("model_name"), "algorithm": config.get("algorithm"), "display_name": config.get("display_name"), "candidate_index": config.get("candidate_index"), "candidate_count": config.get("candidate_count", len(_selected_models)), "selected_models": run_state.get("selected_models", _selected_models), "learning_rate": config.get("learning_rate"), "epochs": config.get("max_epochs", config.get("epochs")), "actual_epochs": training.get("actual_epochs", last.get("epoch")), "min_epochs": config.get("min_epochs"), "patience": config.get("patience"), "min_delta": config.get("min_delta"), "stability_window": config.get("stability_window"), "stability_tolerance": config.get("stability_tolerance"), "batch_size": config.get("batch_size"), "updates_per_epoch": training.get("updates_per_epoch") or last.get("updates_per_epoch"), "max_total_updates": training.get("max_total_updates") or config.get("max_total_updates"), "total_updates_used": training.get("total_updates_used", last.get("total_updates")), "policy_reward": last.get("policy_reward"), "oracle_average_reward": last.get("oracle_average_reward"), "reward_efficiency": last.get("reward_efficiency"), "validation": last.get("validation"), "validation_score": last.get("validation_score"), "best_epoch": training.get("best_epoch", last.get("best_epoch")), "stopping_reason": training.get("stopping_reason") or last.get("stopping_reason"), "progress": progress, "history": history},
                "comparison": comparison if comparison.get("run_id") in (None, run_state.get("run_id")) else {},
                "evaluation": {"samples": testing.get("test_rows"), "throughput_rows_per_second": testing.get("throughput_rows_per_second"), "average_reward": testing.get("average_reward"), "oracle_average_reward": testing.get("oracle_average_reward"), "policy_optimality": testing.get("policy_optimality"), "reward_efficiency": testing.get("reward_efficiency"), "reward_regret": testing.get("reward_regret"), "action_distribution": testing.get("action_distribution"), "per_class": testing.get("per_class")},
                "model": {"path": str(MODEL_PATH), "exists": MODEL_PATH.exists(), "size_bytes": MODEL_PATH.stat().st_size if MODEL_PATH.exists() else None, "modified_at": datetime.fromtimestamp(MODEL_PATH.stat().st_mtime, tz=timezone.utc).isoformat() if MODEL_PATH.exists() else None},
                "live_inference": inference,
                "post_training": _post_training,
            }
            return _json_safe({"status": state, "message": message, "started_at": _started_at, "pid": _process.pid if running and _process else None, "run_id": run_state.get("run_id"), "results": results})
        except Exception as exc:
            return {"status": "error", "message": f"Training telemetry error: {exc}", "results": {"training": {"history": []}, "dataset": {}, "evaluation": {}, "comparison": {}, "model": {}}}