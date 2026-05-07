from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin, ArchiveMixin
from utils.permissions import IsBossOrManager
from .models import TeacherSalary, StaffSalary, StaffKpiRule
from .serializers import (
    TeacherSalarySerializer,
    StaffSalarySerializer,
    StaffSalaryCreateSerializer,
    StaffKpiRuleSerializer,
    StaffKpiRuleCreateSerializer,
)


class TeacherSalaryViewSet(CompanyFilterMixin, mixins.ListModelMixin,
                           mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET  /api/v1/teacher-salaries/
    GET  /api/v1/teacher-salaries/{id}/
    POST /api/v1/teacher-salaries/{id}/mark-paid/
    """
    queryset = TeacherSalary.objects.select_related('teacher__user').order_by('-month')
    serializer_class = TeacherSalarySerializer
    filterset_fields = ['teacher']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        month = self.request.query_params.get('month')
        if month:
            try:
                year, mon = month.split('-')
                qs = qs.filter(month__year=int(year), month__month=int(mon))
            except ValueError:
                pass
        return qs

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        salary = self.get_object()
        salary.paid_at = timezone.now()
        salary.save(update_fields=['paid_at'])
        return Response(TeacherSalarySerializer(salary).data)


class StaffSalaryViewSet(CompanyFilterMixin, mixins.CreateModelMixin,
                         mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    """
    GET  /api/v1/staff-salaries/
    POST /api/v1/staff-salaries/   — triggers Expense mirror via signal (Rule 10)
    GET  /api/v1/staff-salaries/{id}/
    """
    queryset = StaffSalary.objects.select_related('user').order_by('-month')
    http_method_names = ['get', 'post', 'head', 'options']
    filterset_fields = ['user']

    def get_queryset(self):
        qs = super().get_queryset()
        month = self.request.query_params.get('month')
        if month:
            try:
                year, mon = month.split('-')
                qs = qs.filter(month__year=int(year), month__month=int(mon))
            except ValueError:
                pass
        return qs

    def get_permissions(self):
        if self.action == 'create':
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return StaffSalaryCreateSerializer
        return StaffSalarySerializer

    def perform_create(self, serializer):
        # Signal in apps/salaries/signals.py auto-creates the Expense mirror
        serializer.save(company=self.request.user.company)


class StaffKpiRuleViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    """
    GET    /api/v1/staff-kpi-rules/
    POST   /api/v1/staff-kpi-rules/
    GET    /api/v1/staff-kpi-rules/{id}/
    PATCH  /api/v1/staff-kpi-rules/{id}/
    POST   /api/v1/staff-kpi-rules/{id}/archive/
    """
    queryset = StaffKpiRule.objects.filter(status='active').order_by('created_at')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        return [IsBossOrManager()]

    def get_serializer_class(self):
        if self.action == 'create':
            return StaffKpiRuleCreateSerializer
        return StaffKpiRuleSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)
