import pytest
from decimal import Decimal

DEBTS_URL = "/api/v1/debts/"


@pytest.mark.django_db
class TestDebtConfirmation:
    def test_patch_amount_sets_confirmed_at(self, boss_client, debt):
        assert debt.confirmed_at is None

        resp = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "450000"})
        assert resp.status_code == 200

        debt.refresh_from_db()
        assert debt.amount == Decimal("450000")
        assert debt.confirmed_at is not None

    def test_patch_status_only_does_not_set_confirmed_at(self, boss_client, debt):
        assert debt.confirmed_at is None

        resp = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"status": "paid"})
        assert resp.status_code == 200

        debt.refresh_from_db()
        assert debt.status == "paid"
        assert debt.confirmed_at is None

    def test_confirmed_at_is_read_only(self, boss_client, debt):
        resp = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {
            "status": "paid",
            "confirmed_at": "2020-01-01T00:00:00Z",
        })
        assert resp.status_code == 200

        debt.refresh_from_db()
        # confirmed_at is read-only and 'amount' is absent — must remain None
        assert debt.confirmed_at is None

    def test_re_confirm_updates_confirmed_at_again(self, boss_client, debt):
        resp1 = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "400000"})
        assert resp1.status_code == 200
        debt.refresh_from_db()
        first_confirmed_at = debt.confirmed_at
        assert first_confirmed_at is not None

        resp2 = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "300000"})
        assert resp2.status_code == 200
        debt.refresh_from_db()
        assert debt.amount == Decimal("300000")
        assert debt.confirmed_at >= first_confirmed_at

    def test_admin_can_confirm_debt(self, admin_client, debt):
        resp = admin_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "100000"})
        assert resp.status_code == 200
        debt.refresh_from_db()
        assert debt.confirmed_at is not None

    def test_manager_can_confirm_debt(self, manager_client, debt):
        resp = manager_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "100000"})
        assert resp.status_code == 200

    def test_teacher_cannot_update_debt(self, teacher_client, debt):
        resp = teacher_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "100000"})
        assert resp.status_code == 403
        debt.refresh_from_db()
        assert debt.confirmed_at is None

    def test_response_includes_confirmed_at_field(self, boss_client, debt):
        resp = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "250000"})
        assert resp.status_code == 200
        assert "confirmed_at" in resp.data
        assert resp.data["confirmed_at"] is not None
