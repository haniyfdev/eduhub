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
        from datetime import date as date_type
        qs = super().get_queryset()

        from_str = self.request.query_params.get('from_date')
        to_str   = self.request.query_params.get('to_date')
        month    = self.request.query_params.get('month')

        if from_str or to_str:
            try:
                if from_str:
                    fd = date_type.fromisoformat(from_str)
                    qs = qs.filter(month__gte=fd.replace(day=1))
                if to_str:
                    td = date_type.fromisoformat(to_str)
                    qs = qs.filter(month__lte=td.replace(day=1))
            except (ValueError, AttributeError):
                pass
        elif month:
            try:
                year, mon = month.split('-')
                qs = qs.filter(month__year=int(year), month__month=int(mon))
            except ValueError:
                pass

        # Only show salaries for active teachers who have at least one active group
        qs = qs.filter(teacher__status='active', teacher__groups__status='active').distinct()

        return qs.order_by('-total_amount')

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        """Legacy alias — delegates to pay() with full amount."""
        salary = self.get_object()
        total_owed = salary.calculated_amount + salary.carry_over
        remaining  = total_owed - salary.paid_amount
        request.data['amount'] = str(remaining) if remaining > 0 else str(total_owed)
        return self.pay(request, pk=pk)

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        """POST /api/v1/teacher-salaries/{id}/pay/  body: {amount}"""
        from decimal import Decimal, InvalidOperation
        from apps.expenses.models import Expense

        salary = self.get_object()
        try:
            amount = Decimal(str(request.data.get('amount', 0)))
        except (InvalidOperation, TypeError):
            return Response({'error': "Noto'g'ri summa"}, status=400)

        total_owed = salary.calculated_amount + salary.carry_over
        remaining  = total_owed - salary.paid_amount

        if amount <= 0:
            return Response({"error": "Summa musbat bo'lishi kerak"}, status=400)
        if amount > remaining:
            return Response({"error": "Summa qarzdan oshib ketdi"}, status=400)

        salary.paid_amount += amount

        if salary.paid_amount >= total_owed:
            salary.status    = 'paid'
            salary.is_paid   = True
            salary.paid_at   = timezone.now()
            salary.carry_over = Decimal('0')
        else:
            salary.status = 'partial'

        salary.save()

        # Record the payment as an expense
        teacher_name = salary.teacher.user.get_full_name()
        Expense.objects.create(
            company=salary.teacher.company,
            category='teacher_salary',
            source='auto',
            amount=amount,
            description=f"{teacher_name} — {salary.month.strftime('%B %Y')} maoshi",
            expense_date=timezone.now().date(),
        )

        return Response(TeacherSalarySerializer(salary).data)

    @action(detail=False, methods=['post'], url_path='calculate')
    def calculate(self, request):
        """POST /api/v1/teacher-salaries/calculate/?month=YYYY-MM
        Calculate (create if missing) salaries for all active teachers this month."""
        import datetime
        from apps.salaries.logic import calculate_teacher_salary
        from apps.teachers.models import Teacher as TeacherModel

        month_str = request.query_params.get('month') or request.data.get('month')
        company = request.user.company

        if month_str:
            try:
                year, mon = month_str.split('-')
                month = datetime.date(int(year), int(mon), 1)
            except (ValueError, AttributeError):
                return Response({'detail': 'Format: YYYY-MM'}, status=400)
        else:
            today = datetime.date.today()
            month = today.replace(day=1)

        teachers = TeacherModel.objects.filter(
            company=company, status='active', groups__status='active',
        ).distinct()
        created, skipped = [], []

        for teacher in teachers:
            name = teacher.user.get_full_name()
            existing = TeacherSalary.objects.filter(teacher=teacher, month=month).first()
            if existing and existing.status == 'paid':
                skipped.append(name)
            else:
                calculate_teacher_salary(teacher, month)
                created.append(name)

        return Response({
            'month':   month.strftime('%Y-%m'),
            'created': created,
            'skipped': skipped,
        })


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
