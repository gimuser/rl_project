# app/api/router.py
from fastapi import APIRouter
from app.api.alerts import router as alerts_router
from app.api.health import router as health_router
from app.api.pipeline import router as pipeline_router
from app.api.decisions import router as decisions_router
from app.api.rewards import router as rewards_router
from app.api.database_monitoring import router as db_router
from app.api.dashboard import router as dashboard_router
from app.api.agent import router as agent_router
from app.api.evaluation import router as evaluation_router
from app.api.metrics import router as metrics_router
from app.api.api_status import router as api_status_router
from app.api.live_alerts import router as live_alerts_router
from app.api.live_cycle import router as live_cycle_router
from app.api.authoritative_training import router as authoritative_training_router
from app.api.authoritative_metrics import router as authoritative_metrics_router
from app.api.training_history import router as training_history_router

router = APIRouter()

router.include_router(alerts_router, prefix="/api/alerts", tags=["Alerts"])
router.include_router(health_router, prefix="/api/system", tags=["System Health"])
router.include_router(api_status_router)
router.include_router(decisions_router, prefix="/api/decisions", tags=["Decisions"])
router.include_router(rewards_router, prefix="/api/rewards", tags=["Rewards"])
router.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])
router.include_router(live_alerts_router)
router.include_router(live_cycle_router)
router.include_router(authoritative_training_router)
router.include_router(authoritative_metrics_router)
router.include_router(training_history_router)
router.include_router(pipeline_router)
router.include_router(db_router)
router.include_router(agent_router)
router.include_router(evaluation_router)
router.include_router(metrics_router)
