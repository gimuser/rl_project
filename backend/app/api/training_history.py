from fastapi import APIRouter, HTTPException

from app.services.training_history import list_runs, load_run

router = APIRouter(prefix="/api/training-control", tags=["Training History"])


@router.get("/runs")
def get_training_runs():
    return {"runs": list_runs()}


@router.get("/runs/{run_id}")
def get_training_run(run_id: str):
    result = load_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Training run not found.")
    return {
        "status": result.get("run_state", {}).get("status", "completed"),
        "run_id": result["run_id"],
        "results": {
            "training": result.get("training", {}),
            "evaluation": result.get("evaluation", {}),
            "comparison": result.get("comparison", {}),
            "live_inference": result.get("live_inference", {}),
            "manifest": result.get("manifest", {}),
        },
    }
