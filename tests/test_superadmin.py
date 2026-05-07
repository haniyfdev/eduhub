import pytest
from decimal import Decimal

SUPERADMIN_COMPANIES_URL = "/api/superadmin/companies/"
SUPERADMIN_REVENUE_URL = "/api/superadmin/revenue/"
SUPERADMIN_SUBSCRIPTIONS_URL = "/api/superadmin/subscriptions/"
SUPERADMIN_LOGS_URL = "/api/superadmin/logs/"


@pytest.mark.django_db
class TestSuperadminPermissions:
    def test_superadmin_can_access_companies(self, superadmin_client):
        resp = superadmin_client.get(SUPERADMIN_COMPANIES_URL)
        assert resp.status_code == 200

    def test_boss_blocked_from_superadmin(self, boss_client):
        resp = boss_client.get(SUPERADMIN_COMPANIES_URL)
        assert resp.status_code == 403

    def test_manager_blocked(self, manager_client):
        resp = manager_client.get(SUPERADMIN_COMPANIES_URL)
        assert resp.status_code == 403

    def test_admin_blocked(self, admin_client):
        resp = admin_client.get(SUPERADMIN_COMPANIES_URL)
        assert resp.status_code == 403

    def test_teacher_blocked(self, teacher_client):
        resp = teacher_client.get(SUPERADMIN_COMPANIES_URL)
        assert resp.status_code == 403

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(SUPERADMIN_COMPANIES_URL)
        assert resp.status_code == 401

    def test_all_superadmin_endpoints_blocked_for_boss(self, boss_client):
        for url in [SUPERADMIN_COMPANIES_URL, SUPERADMIN_REVENUE_URL,
                    SUPERADMIN_SUBSCRIPTIONS_URL, SUPERADMIN_LOGS_URL]:
            resp = boss_client.get(url)
            assert resp.status_code == 403, f"{url} should be 403 for boss"


@pytest.mark.django_db
class TestSuperadminCompanies:
    def test_lists_all_companies(self, superadmin_client, company, company2):
        resp = superadmin_client.get(SUPERADMIN_COMPANIES_URL)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data]
        assert str(company.id) in ids
        assert str(company2.id) in ids

    def test_company_has_subscription_and_user_count(self, superadmin_client, company):
        resp = superadmin_client.get(SUPERADMIN_COMPANIES_URL)
        assert resp.status_code == 200
        entry = next((c for c in resp.data if c["id"] == str(company.id)), None)
        assert entry is not None
        assert "active_subscription" in entry
        assert "user_count" in entry


@pytest.mark.django_db
class TestSuperadminRevenue:
    def test_revenue_returns_12_months(self, superadmin_client):
        resp = superadmin_client.get(SUPERADMIN_REVENUE_URL)
        assert resp.status_code == 200
        assert len(resp.data) == 12

    def test_revenue_period_format(self, superadmin_client):
        resp = superadmin_client.get(SUPERADMIN_REVENUE_URL)
        for item in resp.data:
            assert "period" in item
            assert "revenue" in item
            # period format: "YYYY-MM"
            assert len(item["period"]) == 7
            assert item["period"][4] == "-"


@pytest.mark.django_db
class TestSuperadminLogs:
    def test_list_logs(self, superadmin_client):
        resp = superadmin_client.get(SUPERADMIN_LOGS_URL)
        assert resp.status_code == 200

    def test_create_log(self, superadmin_client, superadmin):
        resp = superadmin_client.post(SUPERADMIN_LOGS_URL, {
            "action": "archive_company",
            "description": "Archived test company",
        })
        assert resp.status_code == 201
        assert resp.data["action"] == "archive_company"

    def test_created_log_has_user(self, superadmin_client, superadmin):
        resp = superadmin_client.post(SUPERADMIN_LOGS_URL, {
            "action": "update_subscription",
            "description": "Extended plan",
        })
        assert resp.status_code == 201
        from apps.superadmin_panel.models import SuperadminLog
        log = SuperadminLog.objects.get(id=resp.data["id"])
        assert log.user == superadmin

    def test_patch_not_supported_logs_detail(self, superadmin_client, superadmin):
        # SuperadminLogViewSet is ListModelMixin + CreateModelMixin only
        # Detail endpoints (/{id}/) are not registered → 404
        create_resp = superadmin_client.post(SUPERADMIN_LOGS_URL, {
            "action": "test", "description": "test"
        })
        log_id = create_resp.data["id"]
        resp = superadmin_client.patch(f"{SUPERADMIN_LOGS_URL}{log_id}/", {"action": "hacked"})
        assert resp.status_code in (404, 405)
