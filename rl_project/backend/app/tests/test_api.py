import pytest
from fastapi.testclient import TestClient
from app.database.database import alerts_collection, decisions_collection, rewards_collection
from main import app

# إنشاء زبون الاختبار (TestClient)
client = TestClient(app)

# ==========================================
# 1. System & Health Tests
# ==========================================
def test_health_check():
    """اختبار نقطة فحص سلامة النظام"""
    response = client.get("/api/system/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ==========================================
# 2. Alerts Endpoints Tests
# ==========================================
def test_create_and_get_alert():
    """اختبار إنشاء تنبيه جديد ثم استرجاعه"""
    # 1. إنشاء تنبيه
    new_alert = {
        "title": "Unauthorized SSH Access Attempt",
        "severity": "High",
        "source": "Firewall-Logs"
    }
    create_res = client.post("/api/alerts", json=new_alert)
    assert create_res.status_code == 200
    created_alert_id = create_res.json()["id"]
    data = create_res.json()
    assert data["title"] == new_alert["title"]
    assert "id" in data
    
    alert_id = data["id"]

    # 2. جلب التنبيه بالـ ID
    get_res = client.get(f"/api/alerts/{alert_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == alert_id

    # Prevent the API test from polluting operational MongoDB.
    alerts_collection.delete_one(
        {"id": created_alert_id}
    )

def test_get_all_alerts_pagination():
    """اختبار قائمة التنبيهات مع دعم الـ Pagination"""
    response = client.get("/api/alerts?skip=0&limit=5")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_alert_not_found():
    """اختبار طلب تنبيه غير موجود"""
    response = client.get("/api/alerts/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Alert not found"


# ==========================================
# 3. Pipeline Endpoints Tests (Zineb)
# ==========================================
def test_pipeline_import_train():
    """اختبار استيراد dataset التدريب"""
    response = client.post("/api/pipeline/import-train")
    assert response.status_code == 200
    assert "imported_count" in response.json()


def test_pipeline_statistics():
    """اختبار إحصائيات الـ Pipeline"""
    response = client.get("/api/pipeline/statistics")
    assert response.status_code == 200
    data = response.json()
    assert "total_rows" in data
    assert "total_columns" in data


# ==========================================
# 4. Decisions Endpoints Tests (Ikram)
# ==========================================
def test_create_and_get_decisions():
    """اختبار إضافة قرار واسترجاع قائمة القرارات"""
    decision_payload = {
        "incident_id": 101,
        "action": "BLOCK_IP"
    }
    # إنشاء قرار
    post_res = client.post("/api/decisions", json=decision_payload)
    assert post_res.status_code == 200
    assert post_res.json()["action"] == "BLOCK_IP"

    created_decision_id = post_res.json()["id"]

    # جلب القرارات
    get_res = client.get("/api/decisions")
    assert get_res.status_code == 200
    assert isinstance(get_res.json(), list)

    # IMPORTANT:
    # Tests must not pollute the real operational MongoDB.
    decisions_collection.delete_one(
        {"id": created_decision_id}
    )


# ==========================================
# 5. Training Endpoints Tests (Ikram)
# ==========================================
def test_training_lifecycle():
    """Verify the authoritative training status endpoint without starting training."""
    status_res = client.get("/api/training-control")

    assert status_res.status_code == 200

    payload = status_res.json()

    assert isinstance(payload, dict)
    assert "status" in payload


# ==========================================
# 6. Rewards Endpoints Tests (Hiba)
# ==========================================
def test_create_and_get_rewards():
    """اختبار إضافة مكافأة واسترجاع الإحصائيات"""
    reward_payload = {
        "decision_id": 1,
        "reward_value": 8.5,
        "metrics": {"latency_reduction": 0.4}
    }
    # إضافة المكافأة
    post_res = client.post("/api/rewards", json=reward_payload)
    assert post_res.status_code == 200
    assert post_res.json()["reward_value"] == 8.5

    created_reward_id = post_res.json()["id"]

    # إحصائيات المكافآت
    stats_res = client.get("/api/rewards/statistics")
    assert stats_res.status_code == 200
    assert "mean_reward" in stats_res.json()

    # IMPORTANT:
    # Tests must not pollute the real operational MongoDB.
    rewards_collection.delete_one(
        {"id": created_reward_id}
    )


# ==========================================
# 7. Database Monitoring Tests (Walid)
# ==========================================
def test_database_monitoring():
    """اختبار مراقبة وصحة قاعدة البيانات"""
    health_res = client.get("/api/database/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "healthy"

    collections_res = client.get("/api/database/collections")
    assert collections_res.status_code == 200
    assert "collections" in collections_res.json()


# ==========================================
# 8. Dashboard Summary Test (Mohammed)
# ==========================================
def test_dashboard_summary():
    """اختبار نقطة الملخص الشامل للـ Dashboard"""
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    
    # التأكد من التزام الاستجابة بالشروط الـ 10 المطلوبة فـ الفقرة 12
    required_keys = [
        "total_alerts", "processed_alerts", "total_decisions",
        "total_rewards", "average_reward", "average_latency",
        "accuracy", "database_status", "training_status", "current_episode"
    ]
    for key in required_keys:
        assert key in data