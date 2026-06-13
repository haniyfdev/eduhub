import pytest

from apps.companies.models import Company

COMPANIES_URL = "/api/v1/companies/"


@pytest.mark.django_db
class TestCompanyPermissions:
    def test_superadmin_can_list(self, superadmin_client):
        resp = superadmin_client.get(COMPANIES_URL)
        assert resp.status_code == 200

    def test_boss_can_access_own_company(self, boss_client, boss):
        resp = boss_client.get(COMPANIES_URL)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data["results"]]
        assert str(boss.company_id) in ids

    def test_manager_can_access_own_company(self, manager_client, manager):
        resp = manager_client.get(COMPANIES_URL)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data["results"]]
        assert str(manager.company_id) in ids

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(COMPANIES_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestCompanyCRUD:
    def test_superadmin_create_company(self, superadmin_client):
        resp = superadmin_client.post(COMPANIES_URL, {
            "name": "New Academy", "phone": "+998991112233"
        })
        assert resp.status_code == 201
        assert Company.objects.filter(name="New Academy").exists()

    def test_superadmin_list_returns_all(self, superadmin_client, company, company2):
        resp = superadmin_client.get(COMPANIES_URL)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data["results"]]
        assert str(company.id) in ids
        assert str(company2.id) in ids

    def test_superadmin_update_company(self, superadmin_client, company):
        resp = superadmin_client.patch(f"{COMPANIES_URL}{company.id}/", {"name": "Updated"})
        assert resp.status_code == 200
        company.refresh_from_db()
        assert company.name == "Updated"

    def test_superadmin_archive_company(self, superadmin_client, company):
        resp = superadmin_client.post(f"{COMPANIES_URL}{company.id}/archive/")
        assert resp.status_code == 200
        company.refresh_from_db()
        assert company.status == "archived"

    def test_archive_does_not_delete(self, superadmin_client, company):
        superadmin_client.post(f"{COMPANIES_URL}{company.id}/archive/")
        assert Company.objects.filter(id=company.id).exists()
