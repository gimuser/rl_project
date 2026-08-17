"""Runtime settings for the backend.

This simple settings object avoids importing pydantic.BaseSettings which may
not be available in all test environments. Use environment variables or a
proper settings management package in production.
"""

import os
from pathlib import Path


class Settings:
    def __init__(self):
        self.app_name: str = "SOAR-RL-Agent"
        self.debug: bool = os.getenv("DEBUG", "true").lower() in ("1", "true", "yes")
        self.api_host: str = os.getenv("API_HOST", "0.0.0.0")
        self.api_port: int = int(os.getenv("API_PORT", "8000"))
        self.mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.database_name: str = os.getenv("DATABASE_NAME", "soar_rl_agent")
        self.mongo_timeout_ms: int = int(os.getenv("MONGO_TIMEOUT_MS", "1000"))
        self.project_root: Path = Path(__file__).resolve().parents[3]
        self.processed_data_dir: Path = Path(
            os.getenv("PROCESSED_DATA_DIR", str(self.project_root / "data" / "processed"))
        )
        self.model_dir: Path = Path(os.getenv("MODEL_DIR", str(self.project_root / "models")))
        self.model_path: Path = Path(os.getenv("MODEL_PATH", str(self.model_dir / "triage_dqn.pt")))
        self.model_metadata_path: Path = Path(
            os.getenv("MODEL_METADATA_PATH", str(self.model_dir / "triage_dqn.metadata.json"))
        )
        self.training_seed: int = int(os.getenv("TRAINING_SEED", "42"))
        self.training_max_steps: int = int(os.getenv("TRAINING_MAX_STEPS", "500000"))
        self.training_passes: int = int(os.getenv("TRAINING_PASSES", "3"))
        self.training_episodes: int = int(os.getenv("TRAINING_EPISODES", "0"))
        self.training_progress_interval: int = int(os.getenv("TRAINING_PROGRESS_INTERVAL", "1000"))
        self.evaluation_max_steps: int = int(os.getenv("EVALUATION_MAX_STEPS", "500000"))
        self.training_ram_limit_mb: int = int(os.getenv("TRAINING_RAM_LIMIT_MB", "2048"))
        self.api_allowed_origins: list[str] = [
            "http://localhost:8081",
            "http://127.0.0.1:8081",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
        self.enable_api_activity_tracking: bool = True
        self.api_status_poll_interval: int = 5
        self.api_status_timeout_seconds: int = 15
        self.persist_api_statuses: bool = True
        self.api_components: list[dict] = [

            {"name": "database", "prefix": "/api/database"},
            {"name": "alerts", "prefix": "/api/alerts"},
            {"name": "decisions", "prefix": "/api/decisions"},
            {"name": "rewards", "prefix": "/api/rewards"},
            {"name": "dashboard", "prefix": "/api/dashboard"},
            {"name": "agent", "prefix": "/api/agent"},
            {"name": "evaluation", "prefix": "/api/evaluation"},
        ]
        self.siem_base_url: str | None = os.getenv("SIEM_BASE_URL") or None
        self.siem_api_key: str | None = os.getenv("SIEM_API_KEY") or None
        self.soar_base_url: str | None = os.getenv("SOAR_BASE_URL") or None
        self.soar_api_key: str | None = os.getenv("SOAR_API_KEY") or None
        self.thehive_url: str | None = os.getenv("THEHIVE_URL") or None
        self.thehive_api_key: str | None = os.getenv("THEHIVE_API_KEY") or None
        self.cortex_url: str | None = os.getenv("CORTEX_URL") or None
        self.cortex_api_key: str | None = os.getenv("CORTEX_API_KEY") or None
        self.integration_timeout_seconds: float = float(os.getenv("INTEGRATION_TIMEOUT_SECONDS", "5"))


settings = Settings()
