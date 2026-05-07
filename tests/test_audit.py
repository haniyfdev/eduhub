import pytest
import uuid

from apps.audit.models import AuditLog

AUDIT_LOGS_URL = "/api/v1/audit-logs/"


@pytest.mark.django_db
class TestAuditPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 200

    def test_superadmin_can_list(self, superadmin_client):
        resp = superadmin_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 200

    def test_admin_blocked(self, admin_client):
        resp = admin_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 403

    def test_teacher_blocked(self, teacher_client):
        resp = teacher_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 403

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestAuditReadOnly:
    def test_cannot_create_audit_log(self, boss_client):
        resp = boss_client.post(AUDIT_LOGS_URL, {
            "action": "created",
            "model_name": "Student",
            "object_id": str(uuid.uuid4()),
            "description": "Manual entry attempt",
        })
        assert resp.status_code == 405

    def test_cannot_delete_audit_log(self, boss_client, company, boss):
        log = AuditLog.objects.create(
            company=company, user=boss,
            action="created", model_name="Student",
            object_id=uuid.uuid4(), description="Test log"
        )
        resp = boss_client.delete(f"{AUDIT_LOGS_URL}{log.id}/")
        assert resp.status_code in (404, 405)


@pytest.mark.django_db
class TestAuditFiltering:
    def test_filter_by_model_name(self, boss_client, company, boss):
        AuditLog.objects.create(
            company=company, user=boss,
            action="created", model_name="Student",
            object_id=uuid.uuid4(), description="Created student"
        )
        resp = boss_client.get(f"{AUDIT_LOGS_URL}?model_name=Student")
        assert resp.status_code == 200

    def test_filter_by_date_range(self, boss_client, company, boss):
        from datetime import date
        AuditLog.objects.create(
            company=company, user=boss,
            action="updated", model_name="Group",
            object_id=uuid.uuid4(), description="Updated group"
        )
        today = str(date.today())
        resp = boss_client.get(f"{AUDIT_LOGS_URL}?date_from={today}&date_to={today}")
        assert resp.status_code == 200
