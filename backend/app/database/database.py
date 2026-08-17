from pymongo import MongoClient
from app.config.settings import settings

# Create a MongoDB client using configured settings. Keep a short server
# selection timeout so health checks fail fast during development when the
# database is not available.
client = MongoClient(
    settings.mongo_uri, serverSelectionTimeoutMS=settings.mongo_timeout_ms
)
db = client[settings.database_name]

# Collections used across the application. Add any collections referenced
# elsewhere (training, metrics, checkpoints) so imports succeed.
alerts_collection = db["alerts"]
decisions_collection = db["decisions"]
rewards_collection = db["rewards"]
evaluations_collection = db["evaluations"]
pipeline_collection = db["pipeline_logs"]
training_collection = db["training"]
metrics_collection = db["metrics"]
checkpoints_collection = db["checkpoints"]
api_statuses_collection = db["api_statuses"]
training_metrics_collection = db["training_metrics"]

# Export client and db for health checks and administrative endpoints
# (some parts of the code import client and db directly).

__all__ = [
    "client",
    "db",
    "alerts_collection",
    "decisions_collection",
    "rewards_collection",
    "evaluations_collection",
    "pipeline_collection",
    "training_collection",
    "metrics_collection",
    "checkpoints_collection",
    "api_statuses_collection",
    "training_metrics_collection",
]
