from app.database.repository import (
    get_alerts_from_db, create_alert_in_db, get_alert_by_id_from_db, 
    update_alert_in_db, delete_alert_from_db
)
from app.schemas.alert_schema import Alert, AlertCreate
from typing import Optional

def get_all_alerts(skip: int = 0, limit: int = 10):
    return get_alerts_from_db(skip=skip, limit=limit)

def create_alert(alert: AlertCreate) -> Alert:
    return create_alert_in_db(alert)

def get_alert_by_id(alert_id: int) -> Optional[Alert]:
    return get_alert_by_id_from_db(alert_id)

def update_alert(alert_id: int, alert: AlertCreate):
    return update_alert_in_db(alert_id, alert)

def delete_alert(alert_id: int):
    return delete_alert_from_db(alert_id)