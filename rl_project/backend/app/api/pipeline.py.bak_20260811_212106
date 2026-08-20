from fastapi import APIRouter
from app.schemas.pipeline_schema import PipelineStats, PipelineImportResponse
from app.services.dataset_service import (
    import_train_dataset,
    import_test_dataset,
    get_pipeline_status,
    get_pipeline_statistics,
)

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])

@router.post("/import-train", response_model=PipelineImportResponse)
def import_train_dataset_api():
    return import_train_dataset()

@router.post("/import-test", response_model=PipelineImportResponse)
def import_test_dataset_api():
    return import_test_dataset()

@router.get("/status")
def get_pipeline_status_api():
    return get_pipeline_status()

@router.get("/statistics", response_model=PipelineStats)
def get_pipeline_statistics_api():
    return get_pipeline_statistics()
