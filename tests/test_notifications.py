import pytest

from apps.notifications.models import Notification, SmsTemplate

NOTIFICATIONS_URL = "/api/v1/notifications/"
SMS_TEMPLATES_URL = "/api/v1/sms-templates/"


@pytest.mark.django_db
class TestNotificationPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(NOTIFICATIONS_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(NOTIFICATIONS_URL)
        assert resp.status_code == 200

    def test_teacher_can_read(self, teacher_client):
        resp = teacher_client.get(NOTIFICATIONS_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(NOTIFICATIONS_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestNotificationReadOnly:
    def test_cannot_post_notification(self, boss_client):
        resp = boss_client.post(NOTIFICATIONS_URL, {
            "recipient_phone": "+998991234567",
            "message": "Test", "type": "sms",
        })
        assert resp.status_code == 405

    def test_cannot_patch_notification(self, boss_client, company):
        notif = Notification.objects.create(
            company=company, recipient_phone="+998991234567",
            message="Hello", type="sms", status="pending"
        )
        resp = boss_client.patch(f"{NOTIFICATIONS_URL}{notif.id}/", {"status": "sent"})
        assert resp.status_code in (404, 405)

    def test_list_returns_company_notifications(self, boss_client, company):
        Notification.objects.create(
            company=company, recipient_phone="+998991234567",
            message="Test msg", type="sms", status="pending"
        )
        resp = boss_client.get(NOTIFICATIONS_URL)
        assert resp.status_code == 200
        assert len(resp.data.get("results", resp.data)) >= 1


@pytest.mark.django_db
class TestSmsTemplateCRUD:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(SMS_TEMPLATES_URL)
        assert resp.status_code == 200

    def test_boss_can_create(self, boss_client):
        resp = boss_client.post(SMS_TEMPLATES_URL, {
            "name": "Debt Reminder",
            "body": "Dear {student_name}, please pay your debt.",
            "type": "debt",
        })
        assert resp.status_code == 201

    def test_manager_can_create(self, manager_client):
        resp = manager_client.post(SMS_TEMPLATES_URL, {
            "name": "Welcome SMS",
            "body": "Welcome {student_name}!",
            "type": "welcome",
        })
        assert resp.status_code == 201

    def test_admin_blocked_from_create(self, admin_client):
        resp = admin_client.post(SMS_TEMPLATES_URL, {
            "name": "X", "body": "Y", "type": "custom"
        })
        assert resp.status_code == 403

    def test_teacher_blocked_from_create(self, teacher_client):
        resp = teacher_client.post(SMS_TEMPLATES_URL, {
            "name": "X", "body": "Y", "type": "custom"
        })
        assert resp.status_code == 403

    def test_boss_can_update(self, boss_client, company):
        template = SmsTemplate.objects.create(
            company=company, name="Test", body="Hello", type="custom"
        )
        resp = boss_client.patch(f"{SMS_TEMPLATES_URL}{template.id}/", {"name": "Updated"})
        assert resp.status_code == 200
        template.refresh_from_db()
        assert template.name == "Updated"

    def test_boss_can_delete_sms_template(self, boss_client, company):
        template = SmsTemplate.objects.create(
            company=company, name="DeleteMe", body="bye", type="custom"
        )
        resp = boss_client.delete(f"{SMS_TEMPLATES_URL}{template.id}/")
        assert resp.status_code == 204
        assert not SmsTemplate.objects.filter(id=template.id).exists()

    def test_cross_company_template_blocked(self, boss_client, company2):
        template = SmsTemplate.objects.create(
            company=company2, name="OtherTemplate", body="msg", type="custom"
        )
        resp = boss_client.get(f"{SMS_TEMPLATES_URL}{template.id}/")
        assert resp.status_code in (403, 404)
