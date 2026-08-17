from fastapi import APIRouter, HTTPException

from app.schemas import (
    Alert,
    AlertCreate,
)

from app.services.alert_service import (
    get_all_alerts,
    get_alert_by_id,
    create_alert,
    update_alert,
    delete_alert,
)


router = APIRouter(
    tags=["Alerts"]
)


@router.get("/health")
def alerts_health():
    return {
        "status": "ok",
        "service": "alerts",
    }


@router.get(
    "",
    response_model=list[Alert],
)
def get_alerts(
    skip: int = 0,
    limit: int = 10,
):
    return get_all_alerts(
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=Alert,
)
def add_alert(
    alert: AlertCreate,
):
    return create_alert(
        alert
    )


@router.get(
    "/{alert_id}",
    response_model=Alert,
)
def get_alert(
    alert_id: int,
):
    alert = get_alert_by_id(
        alert_id
    )

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail="Alert not found",
        )

    return alert


@router.put(
    "/{alert_id}",
    response_model=Alert,
)
def edit_alert(
    alert_id: int,
    alert: AlertCreate,
):
    updated = update_alert(
        alert_id,
        alert,
    )

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail="Alert not found",
        )

    return updated


@router.delete(
    "/{alert_id}"
)
def remove_alert(
    alert_id: int,
):
    deleted = delete_alert(
        alert_id
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Alert not found",
        )

    return {
        "message":
            "Alert deleted successfully"
    }
