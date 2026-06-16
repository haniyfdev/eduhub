import pytest
from datetime import date
from decimal import Decimal

from apps.expenses.models import Expense

EXPENSES_URL = "/api/v1/expenses/"
PL_URL = "/api/v1/profit-loss/"
PL_HISTORY_URL = "/api/v1/profit-loss/history/"
PL_TEACHERS_URL = "/api/v1/profit-loss/teachers/"

ALL_EXPENSE_CATEGORIES = ['rent', 'utility', 'tax', 'fine', 'discount', 'maoshlar', 'other']


@pytest.mark.django_db
class TestExpensePermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(EXPENSES_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(EXPENSES_URL)
        assert resp.status_code == 200

    def test_admin_can_list(self, admin_client):
        # ExpenseViewSet: create=IsBossOrManager, list=IsAuthenticated
        resp = admin_client.get(EXPENSES_URL)
        assert resp.status_code == 200

    def test_admin_blocked_from_create(self, admin_client):
        resp = admin_client.post(EXPENSES_URL, {
            "category": "rent", "amount": "100000.00",
            "description": "Test", "expense_date": str(date.today()),
        })
        assert resp.status_code == 403

    def test_teacher_can_list(self, teacher_client):
        resp = teacher_client.get(EXPENSES_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(EXPENSES_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestExpenseCRUD:
    def test_create_manual_expense(self, boss_client, company):
        resp = boss_client.post(EXPENSES_URL, {
            "category": "rent",
            "amount": "500000.00",
            "description": "Office rent",
            "expense_date": str(date.today()),
        })
        assert resp.status_code == 201
        # Verify source is set to 'manual' by checking the DB record
        from apps.expenses.models import Expense
        expense = Expense.objects.get(id=resp.data["id"])
        assert expense.source == "manual"

    def test_list_expenses(self, boss_client, company):
        Expense.objects.create(
            company=company, category="rent", source="manual",
            amount=Decimal("100000"), description="Test", expense_date=date.today()
        )
        resp = boss_client.get(EXPENSES_URL)
        assert resp.status_code == 200
        assert len(resp.data.get("results", resp.data)) >= 1

    def test_cross_company_blocked(self, boss_client, company2, db):
        other_expense = Expense.objects.create(
            company=company2, category="rent", source="manual",
            amount=Decimal("100000"), description="Other", expense_date=date.today()
        )
        resp = boss_client.get(f"{EXPENSES_URL}{other_expense.id}/")
        assert resp.status_code in (403, 404)


@pytest.mark.django_db
class TestProfitLoss:
    def test_pl_requires_month_or_year_param(self, boss_client):
        resp = boss_client.get(PL_URL)
        assert resp.status_code == 400

    def test_pl_by_month_returns_all_8_categories(self, boss_client):
        today = date.today()
        month_str = f"{today.year}-{today.month:02d}"
        resp = boss_client.get(f"{PL_URL}?month={month_str}")
        assert resp.status_code == 200
        expenses = resp.data["expenses"]
        # Category totals are flat on expenses (teacher+staff salary combined as maoshlar)
        for cat in ALL_EXPENSE_CATEGORIES:
            assert cat in expenses, f"Category '{cat}' missing from P&L expenses"
        # breakdown is now a list of individual expense records (not a dict)
        assert isinstance(expenses["breakdown"], list)

    def test_pl_by_year_works(self, boss_client):
        today = date.today()
        resp = boss_client.get(f"{PL_URL}?year={today.year}")
        assert resp.status_code == 200

    def test_pl_response_structure(self, boss_client):
        today = date.today()
        month_str = f"{today.year}-{today.month:02d}"
        resp = boss_client.get(f"{PL_URL}?month={month_str}")
        assert resp.status_code == 200
        assert "income" in resp.data
        assert "expenses" in resp.data
        assert "profit" in resp.data
        assert "margin" in resp.data

    def test_pl_history_returns_list(self, boss_client):
        resp = boss_client.get(PL_HISTORY_URL)
        assert resp.status_code == 200
        assert isinstance(resp.data, list)

    def test_pl_teachers_returns_list(self, boss_client):
        resp = boss_client.get(PL_TEACHERS_URL)
        assert resp.status_code == 200
        assert isinstance(resp.data, list)

    def test_pl_profit_calculation(self, boss_client, company):
        today = date.today()
        Expense.objects.create(
            company=company, category="rent", source="manual",
            amount=Decimal("100000"), description="Rent", expense_date=today
        )
        month_str = f"{today.year}-{today.month:02d}"
        resp = boss_client.get(f"{PL_URL}?month={month_str}")
        assert resp.status_code == 200
        # profit = income.total - expenses.total
        income_total = resp.data["income"]["total"]
        expenses_total = resp.data["expenses"]["total"]
        assert resp.data["profit"] == income_total - expenses_total
