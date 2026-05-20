import datetime
from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin
from utils.permissions import IsBossOrManager
from .models import Staff, StaffSalary
from .serializers import StaffSerializer, StaffCreateSerializer, StaffSalarySerializer


class StaffViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = Staff.objects.all().order_by('first_name', 'last_name')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def get_permissions(self):
        if self.action in ('create', 'partial_update', 'archive'):
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return StaffCreateSerializer
        return StaffSerializer

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    @action(detail=True, methods=['patch'], url_path='archive')
    def archive(self, request, pk=None):
        staff = self.get_object()
        staff.status = 'archived'
        staff.save(update_fields=['status'])
        return Response(StaffSerializer(staff).data)


class StaffSalaryViewSet(CompanyFilterMixin, mixins.ListModelMixin,
                         mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = StaffSalary.objects.select_related('staff').order_by('-month', 'staff__first_name')
    serializer_class = StaffSalarySerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        month_str = self.request.query_params.get('month')
        if month_str:
            try:
                year, mon = month_str.split('-')
                qs = qs.filter(month__year=int(year), month__month=int(mon))
            except ValueError:
                pass
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def get_permissions(self):
        return [IsAuthenticated()]

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """POST /api/v1/staff-salaries/generate/?month=YYYY-MM"""
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

        prev_month = (month - relativedelta(months=1)).replace(day=1)
        active_staff = Staff.objects.filter(company=company, status='active')
        created_list, skipped_list = [], []

        for staff in active_staff:
            calculated_amount = staff.salary_amount
            due_date = (month + relativedelta(months=1)).replace(day=1)

            prev_salary = StaffSalary.objects.filter(staff=staff, month=prev_month).first()
            carry_over = Decimal('0')
            if prev_salary and prev_salary.status != 'paid':
                carry_over = max(
                    Decimal('0'),
                    prev_salary.calculated_amount + prev_salary.carry_over - prev_salary.paid_amount,
                )

            salary, was_created = StaffSalary.objects.get_or_create(
                staff=staff, company=company, month=month,
                defaults={
                    'calculated_amount': calculated_amount,
                    'carry_over': carry_over,
                    'due_date': due_date,
                },
            )

            if not was_created:
                if salary.status != 'paid':
                    salary.calculated_amount = calculated_amount
                    salary.carry_over = carry_over
                    salary.due_date = due_date
                    salary.save(update_fields=['calculated_amount', 'carry_over', 'due_date'])
                    created_list.append(staff.full_name)
                else:
                    skipped_list.append(staff.full_name)
            else:
                created_list.append(staff.full_name)

        return Response({
            'month': month.strftime('%Y-%m'),
            'created': created_list,
            'skipped': skipped_list,
        })

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        """POST /api/v1/staff-salaries/{id}/pay/  body: {amount, payment_type}"""
        from apps.expenses.models import Expense

        salary = self.get_object()
        try:
            amount = Decimal(str(request.data.get('amount', 0)))
        except (InvalidOperation, TypeError):
            return Response({'error': "Noto'g'ri summa"}, status=400)

        total_owed = salary.calculated_amount + salary.carry_over - salary.paid_amount

        if amount <= 0:
            return Response({"error": "Summa musbat bo'lishi kerak"}, status=400)
        if amount < 10000:
            return Response({"error": "Minimal to'lov 10,000 so'm"}, status=400)
        if amount > total_owed:
            return Response({"error": "Summa qarzdan oshib ketdi"}, status=400)

        salary.paid_amount += amount
        new_owed = salary.calculated_amount + salary.carry_over - salary.paid_amount

        if new_owed <= 0:
            salary.status  = 'paid'
            salary.is_paid = True
            salary.paid_at = timezone.now()
        else:
            salary.status = 'partial'

        salary.save()

        Expense.objects.create(
            company=salary.company,
            category='staff_salary',
            source='auto',
            amount=amount,
            description=f"{salary.staff.full_name} — {salary.month.strftime('%B %Y')} maoshi",
            expense_date=timezone.now().date(),
        )

        return Response(StaffSalarySerializer(salary).data)
