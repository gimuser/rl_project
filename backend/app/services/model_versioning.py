from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
MODEL_PATH = MODELS_DIR / "real_dqn_agent.pt"
VERSION_PATH = MODELS_DIR / "current_model.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model_version(
    *,
    model_path: Path = MODEL_PATH,
    model_name: str = "DoubleDQN",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not model_path.exists():
        return None

    model_hash = _sha256(model_path)
    existing = None
    try:
        if VERSION_PATH.exists():
            existing = json.loads(VERSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        existing = None

    if isinstance(existing, dict) and existing.get("model_sha256") == model_hash:
        return existing

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version = f"{model_name}-{stamp}-{model_hash[:10]}"

    metadata: dict[str, Any] = {
        "model_version": version,
        "model_name": model_name,
        "model_path": str(model_path),
        "model_sha256": model_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "authoritative_training",
    }
    if extra:
        metadata.update(extra)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    VERSION_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def get_current_model_version() -> dict[str, Any] | None:
    if VERSION_PATH.exists():
        try:
            value = json.loads(VERSION_PATH.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    return ensure_model_version()
