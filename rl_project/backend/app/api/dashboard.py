from fastapi import APIRouter
from app.schemas import DashboardSummary
from app.services.dashboard_service import get_enhanced_dashboard_summary

# إزالة prefix="/dashboard"
router = APIRouter(tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary():
    """Récupère le résumé complet des métriques pour le Dashboard."""
    return get_enhanced_dashboard_summary()