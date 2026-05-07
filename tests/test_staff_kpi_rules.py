"""Tests for StaffKpiRule CRUD endpoints."""
import pytest
from decimal import Decimal

from apps.salaries.models import StaffKpiRule


class TestStaffKpiRuleCRUD:
    def test_boss_can_create_rule(self, db, boss_client, company):
        res = boss_client.post('/api/v1/staff-kpi-rules/', {
            'name': 'Payment KPI',
            'role': 'admin',
            'metric': 'payment_collected',
            'threshold': '5000000',
            'bonus_amount': '500000',
        })
        assert res.status_code == 201
        assert res.data['name'] == 'Payment KPI'
        assert Decimal(res.data['bonus_amount']) == Decimal('500000')

    def test_manager_can_create_rule(self, db, manager_client):
        res = manager_client.post('/api/v1/staff-kpi-rules/', {
            'name': 'Attendance KPI',
            'role': 'any',
            'metric': 'attendance_rate',
            'threshold': '90',
            'bonus_amount': '300000',
        })
        assert res.status_code == 201

    def test_admin_cannot_create_rule(self, db, admin_client):
        res = admin_client.post('/api/v1/staff-kpi-rules/', {
            'name': 'Test',
            'role': 'admin',
            'metric': 'payment_collected',
            'threshold': '1000',
            'bonus_amount': '100',
        })
        assert res.status_code == 403

    def test_list_rules_filters_by_company(self, db, boss_client, company):
        StaffKpiRule.objects.create(
            company=company,
            name='Rule A',
            role='admin',
            metric='payment_collected',
            threshold=Decimal('100'),
            bonus_amount=Decimal('50'),
        )
        res = boss_client.get('/api/v1/staff-kpi-rules/')
        assert res.status_code == 200
        assert len(res.data['results']) == 1
        assert res.data['results'][0]['name'] == 'Rule A'

    def test_cross_company_rule_blocked(self, db, boss_client, company2):
        rule = StaffKpiRule.objects.create(
            company=company2,
            name='Other Rule',
            role='admin',
            metric='student_enrolled',
            threshold=Decimal('10'),
            bonus_amount=Decimal('200000'),
        )
        res = boss_client.get(f'/api/v1/staff-kpi-rules/{rule.id}/')
        assert res.status_code == 404

    def test_patch_rule(self, db, boss_client, company):
        rule = StaffKpiRule.objects.create(
            company=company,
            name='Rule B',
            role='manager',
            metric='student_enrolled',
            threshold=Decimal('20'),
            bonus_amount=Decimal('400000'),
        )
        res = boss_client.patch(f'/api/v1/staff-kpi-rules/{rule.id}/', {
            'bonus_amount': '600000',
        })
        assert res.status_code == 200
        assert Decimal(res.data['bonus_amount']) == Decimal('600000')

    def test_archive_rule(self, db, boss_client, company):
        rule = StaffKpiRule.objects.create(
            company=company,
            name='Old Rule',
            role='any',
            metric='attendance_rate',
            threshold=Decimal('80'),
            bonus_amount=Decimal('100000'),
        )
        res = boss_client.post(f'/api/v1/staff-kpi-rules/{rule.id}/archive/')
        assert res.status_code == 200
        rule.refresh_from_db()
        assert rule.status == 'archived'
        assert rule.archived_at is not None

    def test_archived_rule_hidden_from_list(self, db, boss_client, company):
        StaffKpiRule.objects.create(
            company=company,
            name='Archived Rule',
            role='admin',
            metric='payment_collected',
            threshold=Decimal('1000'),
            bonus_amount=Decimal('50000'),
            status='archived',
        )
        res = boss_client.get('/api/v1/staff-kpi-rules/')
        assert res.status_code == 200
        names = [r['name'] for r in res.data['results']]
        assert 'Archived Rule' not in names

    def test_delete_not_allowed(self, db, boss_client, company):
        rule = StaffKpiRule.objects.create(
            company=company,
            name='No Delete',
            role='admin',
            metric='payment_collected',
            threshold=Decimal('1000'),
            bonus_amount=Decimal('50000'),
        )
        res = boss_client.delete(f'/api/v1/staff-kpi-rules/{rule.id}/')
        assert res.status_code == 405
