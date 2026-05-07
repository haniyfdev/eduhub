import pytest
from decimal import Decimal
from datetime import date

SUMMARY_URL = "/api/v1/dashboard/summary/"
REVENUE_URL = "/api/v1/dashboard/revenue/"
DEBTS_SUMMARY_URL = "/api/v1/dashboard/debts-summary/"
TEACHER_STATS_URL = "/api/v1/dashboard/teacher-stats/"


@pytest.mark.django_db
class TestDashboardPermissions:
    def test_boss_can_access_summary(self, boss_client):
        resp = boss_client.get(SUMMARY_URL)
        assert resp.status_code == 200

    def test_manager_can_access_summary(self, manager_client):
        resp = manager_client.get(SUMMARY_URL)
        assert resp.status_code == 200

    def test_admin_can_access_summary(self, admin_client):
        resp = admin_client.get(SUMMARY_URL)
        assert resp.status_code == 200

    def test_teacher_can_access_summary(self, teacher_client):
        resp = teacher_client.get(SUMMARY_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(SUMMARY_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestDashboardSummary:
    def test_summary_fields(self, boss_client):
        resp = boss_client.get(SUMMARY_URL)
        assert resp.status_code == 200
        for field in [
            "total_students", "active_students", "pending_students", "trial_students",
            "total_groups", "active_groups", "monthly_revenue",
            "total_debtors", "total_debt_amount", "teachers_count"
        ]:
            assert field in resp.data, f"Missing field: {field}"

    def test_summary_reflects_data(self, boss_client, student, pending_student):
        resp = boss_client.get(SUMMARY_URL)
        assert resp.status_code == 200
        assert resp.data["total_students"] >= 2
        assert resp.data["active_students"] >= 1
        assert resp.data["pending_students"] >= 1


@pytest.mark.django_db
class TestDashboardRevenue:
    def test_revenue_default_6_months(self, boss_client):
        resp = boss_client.get(REVENUE_URL)
        assert resp.status_code == 200
        assert len(resp.data["labels"]) == 6
        assert len(resp.data["data"]) == 6

    def test_revenue_custom_period(self, boss_client):
        resp = boss_client.get(f"{REVENUE_URL}?period=12")
        assert resp.status_code == 200
        assert len(resp.data["labels"]) == 12

    def test_revenue_period_clamped_to_24(self, boss_client):
        resp = boss_client.get(f"{REVENUE_URL}?period=100")
        assert resp.status_code == 200
        assert len(resp.data["labels"]) <= 24

    def test_revenue_period_clamped_min_1(self, boss_client):
        resp = boss_client.get(f"{REVENUE_URL}?period=0")
        assert resp.status_code == 200
        assert len(resp.data["labels"]) >= 1


@pytest.mark.django_db
class TestDashboardDebtsSummary:
    ALL_DEBT_STATUSES = ["unpaid", "partial", "paid", "overdue"]

    def test_all_debt_statuses_present(self, boss_client):
        resp = boss_client.get(DEBTS_SUMMARY_URL)
        assert resp.status_code == 200
        for status in self.ALL_DEBT_STATUSES:
            assert status in resp.data, f"Status '{status}' missing"

    def test_each_status_has_count_and_total(self, boss_client):
        resp = boss_client.get(DEBTS_SUMMARY_URL)
        for status in self.ALL_DEBT_STATUSES:
            entry = resp.data[status]
            assert "count" in entry
            assert "total" in entry


@pytest.mark.django_db
class TestDashboardTeacherStats:
    def test_returns_list(self, boss_client, teacher):
        resp = boss_client.get(TEACHER_STATS_URL)
        assert resp.status_code == 200
        assert isinstance(resp.data, list)

    def test_teacher_entry_fields(self, boss_client, teacher):
        resp = boss_client.get(TEACHER_STATS_URL)
        assert resp.status_code == 200
        if resp.data:
            entry = resp.data[0]
            for field in ["teacher_id", "teacher_name", "active_students", "active_groups", "monthly_revenue"]:
                assert field in entry, f"Missing: {field}"
