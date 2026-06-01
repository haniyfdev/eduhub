import datetime
from decimal import Decimal, InvalidOperation

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin, get_active_company
from utils.permissions import IsBossOrManager
from .models import Staff, StaffSalary
from .serializers import StaffSerializer, StaffSalarySerializer


class StaffViewSet(CompanyFilterMixin, viewsets.ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = Staff.objects.select_related('user').order_by(
            'user__first_name', 'user__last_name'
        )
        user = self.request.user
        if user.role != 'superadmin':
            qs = qs.filter(company_id=self._resolve_company_id())
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def get_permissions(self):
        if self.action in ('create', 'partial_update', 'archive'):
            return [IsBossOrManager()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        return StaffSerializer

    def create(self, request, *args, **kwargs):
        from apps.users.models import User

        first_name    = request.data.get('first_name', '').strip()
        last_name     = request.data.get('last_name', '').strip()
        phone         = request.data.get('phone', '').strip()
        role          = request.data.get('role', '').strip()
        salary_amount = request.data.get('salary_amount', 0)
        notes         = request.data.get('notes')
        password      = request.data.get('password', 'parol123')

        company = get_active_company(request)

        if not all([first_name, last_name, phone, role]):
            return Response({'error': 'Barcha maydonlar kerak'}, status=400)

        if User.objects.filter(phone=phone).exists():
            return Response({'error': 'Bu telefon raqam allaqachon ro\'yxatdan o\'tgan'}, status=400)

        with transaction.atomic():
            user = User.objects.create(
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role=role,
                company=company,
            )
            user.set_password(password)
            user.save()

            staff = Staff.objects.create(
                company=company,
                user=user,
                salary_amount=salary_amount,
                notes=notes,
            )

        return Response(StaffSerializer(staff).data, status=201)

    @action(detail=True, methods=['patch'], url_path='archive')
    def archive(self, request, pk=None):
        staff = self.get_object()
        staff.status = 'archived'
        staff.save(update_fields=['status'])
        staff.user.is_active = False
        staff.user.status = 'archived'
        staff.user.save(update_fields=['is_active', 'status'])
        return Response(StaffSerializer(staff).data)

    @action(detail=True, methods=['post'])
    def freeze(self, request, pk=None):
        staff = self.get_object()
        if staff.status == 'frozen':
            return Response({'error': 'Xodim allaqachon muzlatilgan'}, status=400)
        if staff.status == 'archived':
            return Response({'error': "Arxivlangan xodimni muzlatib bo'lmaydi"}, status=400)
        staff.status = 'frozen'
        staff.save(update_fields=['status'])
        return Response({'status': 'frozen'})

    @action(detail=True, methods=['post'])
    def unfreeze(self, request, pk=None):
        staff = self.get_object()
        if staff.status != 'frozen':
            return Response({'error': 'Xodim muzlatilmagan'}, status=400)
        staff.status = 'active'
        staff.save(update_fields=['status'])
        return Response({'status': 'active'})


class StaffSalaryViewSet(CompanyFilterMixin, mixins.ListModelMixin,
                         mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = StaffSalary.objects.select_related('staff__user', 'staff').order_by(
        '-month', 'staff__user__first_name'
    )
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
        company = get_active_company(request)

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
        active_staff = Staff.objects.filter(company=company, status='active').select_related('user')
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

            name = staff.user.get_full_name()
            if not was_created:
                if salary.status != 'paid':
                    salary.calculated_amount = calculated_amount
                    salary.carry_over = carry_over
                    salary.due_date = due_date
                    salary.save(update_fields=['calculated_amount', 'carry_over', 'due_date'])
                    created_list.append(name)
                else:
                    skipped_list.append(name)
            else:
                created_list.append(name)

        return Response({
            'month': month.strftime('%Y-%m'),
            'created': created_list,
            'skipped': skipped_list,
        })

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        """POST /api/v1/staff-salaries/{id}/pay/  body: {amount}"""
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
            description=f"{salary.staff.user.get_full_name()} — {salary.month.strftime('%B %Y')} maoshi",
            expense_date=timezone.now().date(),
        )

        return Response(StaffSalarySerializer(salary).data)
