"""Authoritative real-data incident-level offline-RL pipeline utilities."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ["Category", "MitreTechniques", "ActionGrouped", "ActionGranular", "EntityType", "EvidenceRole", "ThreatFamily", "OSFamily", "SuspicionLevel", "hour", "day", "month", "is_weekend"]
INCIDENT_ID = "IncidentId"
TARGET = "IncidentGrade"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED = PROJECT_ROOT / "data" / "processed"
RL_DATA = PROJECT_ROOT / "data" / "rl_incident"
MODELS = PROJECT_ROOT / "models"
EXPERIMENTS_DIR = MODELS / "experiments"
TRAIN_PATH = PROCESSED / "train_processed.csv"
TEST_PATH = PROCESSED / "test_processed.csv"
MODEL_PATH = MODELS / "real_dqn_agent.pt"
TRAIN_METRICS_PATH = MODELS / "training_metrics.json"
TEST_METRICS_PATH = MODELS / "real_test_metrics.json"
COMPARISON_PATH = MODELS / "model_comparison.json"
RL_DATA.mkdir(parents=True, exist_ok=True)
MODELS.mkdir(parents=True, exist_ok=True)
EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)


def locate_source_dataset() -> Path:
    candidates = [PROCESSED / n for n in ("Microsoft_SOC_Dataset.csv", "microsoft_soc_dataset.csv", "soc_dataset.csv", "full_processed.csv", "processed.csv", "all_processed.csv")]
    for path in candidates:
        if path.exists():
            return path
    valid = []
    for path in PROCESSED.glob("*.csv"):
        try:
            cols = pd.read_csv(path, nrows=0).columns
            if INCIDENT_ID in cols and TARGET in cols:
                valid.append(path)
        except Exception:
            pass
    if not valid:
        raise FileNotFoundError("Could not find a processed CSV containing IncidentId and IncidentGrade.")
    return max(valid, key=lambda p: p.stat().st_size)


def _assert_disjoint(*frames: pd.DataFrame) -> None:
    sets = [set(frame[INCIDENT_ID].astype(str)) for frame in frames]
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            overlap = sets[i] & sets[j]
            if overlap:
                raise RuntimeError(f"FATAL: incident overlap between split {i} and {j}: {len(overlap)}")


def _stream_unique_incident_ids(path: Path, chunksize: int = 200_000) -> set[str]:
    ids: set[str] = set()
    for chunk in pd.read_csv(path, usecols=[INCIDENT_ID], dtype={INCIDENT_ID: "string"}, chunksize=chunksize, low_memory=False):
        values = chunk[INCIDENT_ID].dropna().astype(str)
        ids.update(values.tolist())
        print(f"[RAM-SAFE SPLIT] scanned={len(ids):,} unique incidents", flush=True)
        del chunk
    return ids


def _stream_partition(source: Path, train_out: Path, validation_out: Path, validation_ids: set[str], chunksize: int = 100_000) -> tuple[int, int]:
    first_train = True
    first_validation = True
    train_rows = 0
    validation_rows = 0
    for chunk_no, chunk in enumerate(pd.read_csv(source, chunksize=chunksize, low_memory=False), start=1):
        ids = chunk[INCIDENT_ID].astype(str)
        mask_validation = ids.isin(validation_ids)
        validation_chunk = chunk.loc[mask_validation]
        train_chunk = chunk.loc[~mask_validation]
        if len(train_chunk):
            train_chunk.to_csv(train_out, mode="w" if first_train else "a", header=first_train, index=False)
            first_train = False
            train_rows += len(train_chunk)
        if len(validation_chunk):
            validation_chunk.to_csv(validation_out, mode="w" if first_validation else "a", header=first_validation, index=False)
            first_validation = False
            validation_rows += len(validation_chunk)
        print(f"[RAM-SAFE SPLIT] chunk={chunk_no} train_rows={train_rows:,} validation_rows={validation_rows:,}", flush=True)
        del chunk, ids, mask_validation, validation_chunk, train_chunk
    return train_rows, validation_rows


def build_incident_split() -> tuple[str, str, str]:
    train_source = RL_DATA / "train_incident.csv"
    test_source = RL_DATA / "test_incident.csv"
    if not train_source.exists(): train_source = TRAIN_PATH
    if not test_source.exists(): test_source = TEST_PATH
    if not train_source.exists(): raise FileNotFoundError(f"Training dataset not found: {train_source}")
    if not test_source.exists(): raise FileNotFoundError(f"Test dataset not found: {test_source}")
    print("=" * 78, flush=True)
    print("RAM-SAFE INCIDENT SPLIT", flush=True)
    print(f"TRAIN SOURCE: {train_source}", flush=True)
    print(f"TEST SOURCE : {test_source}", flush=True)
    print("=" * 78, flush=True)
    train_ids = _stream_unique_incident_ids(train_source)
    if not train_ids: raise RuntimeError("No training IncidentId values found.")
    ratio = float(os.getenv("REAL_RL_TRAIN_RATIO_WITHIN_TRAIN_VAL", "0.75"))
    seed = int(os.getenv("REAL_RL_VALIDATION_SEED", "4242"))
    rng = np.random.default_rng(seed)
    ordered_ids = np.array(sorted(train_ids), dtype=object)
    rng.shuffle(ordered_ids)
    n_train = int(len(ordered_ids) * ratio)
    final_train_ids = set(str(x) for x in ordered_ids[:n_train])
    validation_ids = set(str(x) for x in ordered_ids[n_train:])
    if final_train_ids & validation_ids: raise RuntimeError("FATAL: train/validation IncidentId overlap.")
    paths = (RL_DATA / "train_incident.csv", RL_DATA / "validation_incident.csv", RL_DATA / "test_incident.csv")
    train_out, validation_out, test_out = paths
    temporary_train = RL_DATA / "_train_model.tmp.csv"
    target_train = temporary_train if train_source.resolve() == train_out.resolve() else train_out
    for old in [target_train, validation_out]:
        if old.exists(): old.unlink()
    train_rows, validation_rows = _stream_partition(train_source, target_train, validation_out, validation_ids)
    if target_train != train_out: target_train.replace(train_out)
    if test_source.resolve() != test_out: shutil.copy2(test_source, test_out)
    test_ids = _stream_unique_incident_ids(test_out)
    if final_train_ids & test_ids: raise RuntimeError(f"FATAL: train/test incident overlap: {len(final_train_ids & test_ids):,}")
    if validation_ids & test_ids: raise RuntimeError(f"FATAL: validation/test incident overlap: {len(validation_ids & test_ids):,}")
    live_path = PROJECT_ROOT / "data_alert" / "live_source.csv"
    live_ids: set[str] = set()
    if live_path.exists():
        live_df = pd.read_csv(live_path, usecols=[INCIDENT_ID], dtype={INCIDENT_ID: "string"})
        live_ids = set(live_df[INCIDENT_ID].dropna().astype(str).tolist())
    if live_ids & final_train_ids: raise RuntimeError(f"FATAL: live/train overlap: {len(live_ids & final_train_ids)}")
    if live_ids & validation_ids: raise RuntimeError(f"FATAL: live/validation overlap: {len(live_ids & validation_ids)}")
    if live_ids & test_ids: raise RuntimeError(f"FATAL: live/test overlap: {len(live_ids & test_ids)}")
    (RL_DATA / "train_incidents.txt").write_text("\n".join(sorted(final_train_ids)) + "\n", encoding="utf-8")
    (RL_DATA / "validation_incidents.txt").write_text("\n".join(sorted(validation_ids)) + "\n", encoding="utf-8")
    (RL_DATA / "test_incidents.txt").write_text("\n".join(sorted(test_ids)) + "\n", encoding="utf-8")
    report = {"source_rows": train_rows + validation_rows, "train_rows": train_rows, "validation_rows": validation_rows, "test_rows": sum(1 for _ in test_out.open("r", encoding="utf-8", errors="ignore")) - 1, "train_incidents": len(final_train_ids), "validation_incidents": len(validation_ids), "test_incidents": len(test_ids), "live_incidents": len(live_ids), "incident_overlap": 0, "train_validation_overlap": 0, "train_test_overlap": 0, "validation_test_overlap": 0, "train_live_overlap": 0, "validation_live_overlap": 0, "test_live_overlap": 0, "features": FEATURES, "incident_id": INCIDENT_ID, "target": TARGET, "ram_safe": True, "authoritative_train_preserved": True, "authoritative_test_preserved": True}
    (RL_DATA / "split_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("=" * 78, flush=True)
    print("RAM-SAFE SPLIT COMPLETE", flush=True)
    print(f"TRAIN      : {train_rows:,}", flush=True)
    print(f"VALIDATION : {validation_rows:,}", flush=True)
    print(f"TEST       : {report['test_rows']:,}", flush=True)
    print(f"TRAIN IDs  : {len(final_train_ids):,}", flush=True)
    print(f"VAL IDs    : {len(validation_ids):,}", flush=True)
    print(f"TEST IDs   : {len(test_ids):,}", flush=True)
    print(f"LIVE IDs   : {len(live_ids):,}", flush=True)
    print("ALL INCIDENT OVERLAPS: 0", flush=True)
    print("=" * 78, flush=True)
    return tuple(str(p) for p in paths)


def _experiment_configs() -> list[dict]:
    raw = os.getenv("REAL_RL_EXPERIMENTS")
    if raw:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed:
            return parsed
    batch_size = int(os.getenv("REAL_RL_BATCH_SIZE", "2048"))
    learning_rate = float(os.getenv("REAL_RL_LR", "1e-3"))
    gamma = float(os.getenv("REAL_RL_GAMMA", "0.95"))
    max_updates = int(os.getenv("REAL_RL_MAX_TOTAL_UPDATES", "5000000"))
    return [
        {"name": "double_dqn", "algorithm": "double_dqn", "learning_rate": learning_rate, "gamma": gamma, "batch_size": batch_size, "max_total_updates": max_updates},
        {"name": "cql", "algorithm": "cql", "learning_rate": learning_rate, "gamma": gamma, "batch_size": batch_size, "max_total_updates": max_updates},
        {"name": "iql", "algorithm": "iql", "learning_rate": learning_rate, "gamma": gamma, "batch_size": batch_size, "max_total_updates": max_updates},
        {"name": "bcq", "algorithm": "bcq", "learning_rate": learning_rate, "gamma": gamma, "batch_size": batch_size, "max_total_updates": max_updates},
    ]


def _write_comparison(records: list[dict], best: dict | None, status: str = "running") -> None:
    COMPARISON_PATH.write_text(json.dumps({"status": status, "selection_rule": "0.70 * validation_policy_optimality + 0.30 * validation_reward_efficiency", "test_used_for_selection": False, "candidates": records, "best": best}, indent=2, default=str), encoding="utf-8")


def _score(candidate: dict) -> float:
    validation = candidate.get("best_validation") or {}
    return float(0.70 * float(validation.get("policy_optimality", 0.0)) + 0.30 * float(validation.get("reward_efficiency", 0.0)))


def load_dataset(path):
    path = Path(path)
    if not path.exists(): raise FileNotFoundError(path)
    df = pd.read_csv(path, low_memory=False)
    missing = [c for c in list(FEATURES) + [TARGET] if c not in df.columns]
    if missing: raise RuntimeError(f"{path} missing required columns: {missing}")
    states = df[list(FEATURES)].astype(np.float32).to_numpy()
    labels = pd.to_numeric(df[TARGET], errors="raise").astype(np.int64).to_numpy()
    return df, states, labels


def reward_matrix(labels):
    from .triage_env import REWARD_TABLE
    rewards = np.zeros((len(labels), 3), dtype=np.float32)
    for i, label in enumerate(labels):
        row = REWARD_TABLE.get(int(label), REWARD_TABLE[max(REWARD_TABLE)])
        for action in range(3): rewards[i, action] = float(row[action])
    return rewards


def reward_vector(labels): return reward_matrix(labels)


def fit_normalization(states):
    x = np.asarray(states, dtype=np.float32)
    if x.ndim != 2: raise ValueError(f"Expected 2D state matrix, got shape={x.shape}")
    mean = x.mean(axis=0); std = x.std(axis=0); std = np.where(std < 1e-8, 1.0, std)
    return {"mean": mean.astype(float).tolist(), "std": std.astype(float).tolist()}


def apply_normalization(states, normalization=None):
    x = np.asarray(states, dtype=np.float32)
    if normalization is None: return x
    mean = np.asarray(normalization["mean"], dtype=np.float32); std = np.asarray(normalization["std"], dtype=np.float32); std = np.where(std < 1e-8, 1.0, std)
    return ((x - mean) / std).astype(np.float32)
