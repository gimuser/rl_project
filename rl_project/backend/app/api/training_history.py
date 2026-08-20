from fastapi import APIRouter, HTTPException

from app.services.training_history import archive_current_run, list_runs, load_run

router = APIRouter(prefix="/api/training-control", tags=["Training History"])


@router.get("/runs")
def get_training_runs():
    return {"runs": list_runs()}


@router.post("/runs/archive-current")
def archive_current_training_run():
    from app.services.authoritative_training_control import status

    current = status()
    if current.get("status") == "running":
        raise HTTPException(status_code=409, detail="A training run is currently active; it will not be archived or modified.")
    run_id = archive_current_run(reason="archived_before_new_run")
    return {"status": "archived" if run_id else "nothing_to_archive", "run_id": run_id}


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
