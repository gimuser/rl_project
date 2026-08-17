from fastapi import HTTPException


def alert_not_found():
    raise HTTPException(
        status_code=404,
        detail="Alert not found"
    )