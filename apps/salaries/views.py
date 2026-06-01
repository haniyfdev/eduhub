from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.mixins import CompanyFilterMixin, ArchiveMixin, get_active_company
from utils.permissions import IsBossOrManager, IsBossOrManagerOrAdmin, IsBossOrManagerOrAdmin
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
    queryset = TeacherSalary.objects.select_related(
        'teacher__user', 'group__course'
    ).order_by('teacher__user__first_name', 'group__course__name')
    serializer_class = TeacherSalarySerializer
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

        from django.db.models import Q
        qs = qs.filter(teacher__status='active').distinct()
        return qs.filter(
            Q(calculated_amount__gt=0) | Q(paid_amount__gt=0)
        )

    def get_permissions(self):
        if self.action in ('generate', 'calculate', 'pay', 'mark_paid', 'bulk_pay'):
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        """Return salaries grouped by teacher."""
        salaries = list(self.get_queryset())
        serializer = TeacherSalarySerializer(salaries, many=True)
        salary_data_list = serializer.data

        teacher_map = {}
        for salary, sdata in zip(salaries, salary_data_list):
            tid = str(salary.teacher_id)
            if tid not in teacher_map:
                teacher_map[tid] = {
                    'teacher_id': tid,
                    'teacher_name': sdata['teacher_name'],
                    'teacher_subject': sdata['teacher_subject'],
                    'salary_type': sdata['salary_type'],
                    'salary_percent': sdata['salary_percent'],
                    'fixed_amount': sdata['fixed_amount'],
                    'per_student_amt': sdata['per_student_amt'],
                    'kpi_amount': 0,
                    'total_calculated': 0,
                    'total_paid': 0,
                    'total_owed': 0,
                    'groups': [],
                }

            entry = teacher_map[tid]
            carry_over = float(sdata['carry_over'] or 0)
            total_owed = float(sdata['total_owed'] or salary.calculated_amount)
            kpi = float(salary.kpi_amount or 0)

            entry['kpi_amount'] = max(float(entry['kpi_amount']), kpi)
            entry['total_calculated'] += float(salary.calculated_amount)
            entry['total_paid'] += float(salary.paid_amount)
            entry['total_owed'] += total_owed

            entry['groups'].append({
                'salary_id':        str(salary.id),
                'group_id':         sdata['group_id'],
                'group_name':       sdata['group_name'],
                'course_name':      sdata['course_name'],
                'calculated_amount': float(salary.calculated_amount),
                'paid_amount':      float(salary.paid_amount),
                'carry_over':       carry_over,
                'total_owed':       total_owed,
                'status':           salary.status,
                'due_date':         sdata['due_date'],
                'first_active_date': sdata['first_active_date'],
                'student_count':    sdata['student_count'],
                'course_price':     float(sdata['course_price'] or 0),
                'kpi_amount':       kpi,
            })

        # For fixed salary: replace null-group entry with teacher's actual active groups (display only)
        from apps.groups.models import Group, GroupStudent
        results = []
        for entry in teacher_map.values():
            remaining = entry['total_owed'] - entry['total_paid']
            if remaining <= 0:
                entry['overall_status'] = 'paid'
            elif entry['total_paid'] > 0:
                entry['overall_status'] = 'partial'
            else:
                entry['overall_status'] = 'unpaid'

            if entry['salary_type'] == 'fixed':
                # Replace null-group salary entry with actual active groups for display
                actual_groups = Group.objects.filter(
                    teacher_id=entry['teacher_id'],
                    status='active',
                ).select_related('course')
                display_groups = []
                for g in actual_groups:
                    student_count = GroupStudent.objects.filter(
                        group=g, left_at__isnull=True, student__status='active'
                    ).count()
                    display_groups.append({
                        'salary_id':         entry['groups'][0]['salary_id'] if entry['groups'] else '',
                        'group_id':          str(g.id),
                        'group_name':        g.display_name,
                        'course_name':       g.course.name if g.course else None,
                        'calculated_amount': 0,  # fixed amount shown at teacher level
                        'paid_amount':       0,
                        'carry_over':        0,
                        'total_owed':        0,
                        'status':            entry['groups'][0]['status'] if entry['groups'] else 'unpaid',
                        'due_date':          entry['groups'][0]['due_date'] if entry['groups'] else None,
                        'first_active_date': None,
                        'student_count':     student_count,
                        'course_price':      float(g.course.price) if g.course else 0,
                        'kpi_amount':        0,
                    })
                entry['groups'] = display_groups

            results.append(entry)

        return Response(results)

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """POST /api/v1/teacher-salaries/generate/?month=YYYY-MM"""
        return self._run_generate(request)

    @action(detail=False, methods=['post'], url_path='calculate')
    def calculate(self, request):
        """POST /api/v1/teacher-salaries/calculate/?month=YYYY-MM  (alias for generate)"""
        return self._run_generate(request)

    def _run_generate(self, request):
        import datetime
        from apps.salaries.logic import calculate_teacher_salary
        from apps.teachers.models import Teacher as TeacherModel

        month_str = request.query_params.get('month') or request.data.get('month')
        company = get_active_company(request)

        if month_str:
            try:
                year, mon = month_str.split('-')
                month = datetime.date(int(year), int(mon), 1)
            except (ValueError, AttributeError):
                return Response({'detail': 'Format: YYYY-MM'}, status=400)
        else:
            month = datetime.date.today().replace(day=1)

        teachers = TeacherModel.objects.filter(company=company, status='active')
        created_count = 0
        for teacher in teachers:
            salaries = calculate_teacher_salary(teacher, month)
            created_count += len(salaries)

        return Response({'month': month.strftime('%Y-%m'), 'created': created_count})

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """GET /api/v1/teacher-salaries/summary/?month=YYYY-MM"""
        from django.db.models import Sum
        from apps.staff.models import StaffSalary as StaffMemberSalary

        company = get_active_company(request)
        month   = request.query_params.get('month')

        ts_qs = TeacherSalary.objects.filter(company=company)
        ss_qs = StaffMemberSalary.objects.filter(company=company)

        if month:
            try:
                year, mon = month.split('-')
                ts_qs = ts_qs.filter(month__year=int(year), month__month=int(mon))
                ss_qs = ss_qs.filter(month__year=int(year), month__month=int(mon))
            except ValueError:
                pass

        t_agg = ts_qs.aggregate(
            calculated=Sum('calculated_amount'),
            paid=Sum('paid_amount'),
            carry=Sum('carry_over'),
        )
        t_calculated = float(t_agg['calculated'] or 0)
        t_paid       = float(t_agg['paid']       or 0)
        t_carry      = float(t_agg['carry']      or 0)
        t_remaining  = max(t_calculated + t_carry - t_paid, 0)

        s_agg = ss_qs.aggregate(
            calculated=Sum('calculated_amount'),
            paid=Sum('paid_amount'),
            carry=Sum('carry_over'),
        )
        s_calculated = float(s_agg['calculated'] or 0)
        s_paid       = float(s_agg['paid']       or 0)
        s_carry      = float(s_agg['carry']      or 0)
        s_remaining  = max(s_calculated + s_carry - s_paid, 0)

        return Response({
            'total_calculated': t_calculated + s_calculated,
            'total_paid':       t_paid + s_paid,
            'total_remaining':  t_remaining + s_remaining,
            'teacher': {'calculated': t_calculated, 'paid': t_paid, 'remaining': t_remaining},
            'staff':   {'calculated': s_calculated, 'paid': s_paid, 'remaining': s_remaining},
        })

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        """POST /api/v1/teacher-salaries/{id}/pay/  body: {amount}"""
        from decimal import Decimal, InvalidOperation
        from django.db.models import Sum
        from apps.expenses.models import Expense

        salary = self.get_object()
        try:
            amount = Decimal(str(request.data.get('amount', 0)))
        except (InvalidOperation, TypeError):
            return Response({'error': "Noto'g'ri summa"}, status=400)

        # Compute carry_over from previous unpaid records for same teacher+group
        result = TeacherSalary.objects.filter(
            teacher=salary.teacher,
            group=salary.group,
            month__lt=salary.month,
            company=salary.company,
        ).exclude(status='paid').aggregate(
            total_calc=Sum('calculated_amount'),
            total_paid=Sum('paid_amount'),
        )
        carry_over = max(
            (result['total_calc'] or Decimal('0')) - (result['total_paid'] or Decimal('0')),
            Decimal('0'),
        )

        total_owed = salary.calculated_amount + carry_over
        remaining  = total_owed - salary.paid_amount

        if amount <= 0:
            return Response({"error": "Summa musbat bo'lishi kerak"}, status=400)
        if amount < 10000:
            return Response({"error": "Minimal to'lov 10,000 so'm"}, status=400)
        if amount > remaining:
            return Response({"error": "Summa qarzdan oshib ketdi"}, status=400)

        salary.paid_amount += amount
        new_remaining = total_owed - salary.paid_amount

        if new_remaining <= 0 and total_owed > 0:
            salary.status  = 'paid'
            salary.is_paid = True
            salary.paid_at = timezone.now()
        else:
            salary.status = 'partial'

        salary.save()

        teacher_name = salary.teacher.user.get_full_name()
        group_label  = f' ({salary.group.number}{(salary.group.gender_type or "").upper()})' if salary.group else ''
        Expense.objects.create(
            company=salary.company,
            category='teacher_salary',
            source='auto',
            amount=amount,
            description=f"{teacher_name}{group_label} — {salary.month.strftime('%B %Y')} maoshi",
            expense_date=timezone.now().date(),
        )

        return Response(TeacherSalarySerializer(salary).data)

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        """Legacy alias — pays full remaining amount."""
        from decimal import Decimal
        from django.db.models import Sum
        salary = self.get_object()
        result = TeacherSalary.objects.filter(
            teacher=salary.teacher,
            group=salary.group,
            month__lt=salary.month,
            company=salary.company,
        ).exclude(status='paid').aggregate(
            total_calc=Sum('calculated_amount'),
            total_paid=Sum('paid_amount'),
        )
        carry_over = max(
            (result['total_calc'] or Decimal('0')) - (result['total_paid'] or Decimal('0')),
            Decimal('0'),
        )
        total_owed = salary.calculated_amount + carry_over
        remaining  = total_owed - salary.paid_amount
        request.data['amount'] = str(remaining) if remaining > 0 else str(total_owed)
        return self.pay(request, pk=pk)

    @action(detail=False, methods=['post'], url_path='bulk-pay')
    def bulk_pay(self, request):
        """POST /api/v1/teacher-salaries/bulk-pay/
        body: { payments: [{ salary_id, amount }, ...] }
        """
        from decimal import Decimal, InvalidOperation
        from django.db.models import Sum
        from apps.expenses.models import Expense

        payments = request.data.get('payments', [])
        if not payments:
            return Response({'error': 'payments list is required'}, status=400)

        results = []
        errors  = []

        for payment in payments:
            salary_id = payment.get('salary_id')
            try:
                amount = Decimal(str(payment.get('amount', 0)))
            except (InvalidOperation, TypeError):
                errors.append({'salary_id': salary_id, 'error': "Noto'g'ri summa"})
                continue

            try:
                salary = TeacherSalary.objects.get(id=salary_id, company=get_active_company(request))
            except TeacherSalary.DoesNotExist:
                errors.append({'salary_id': salary_id, 'error': 'Not found'})
                continue

            result = TeacherSalary.objects.filter(
                teacher=salary.teacher,
                group=salary.group,
                month__lt=salary.month,
                company=salary.company,
            ).exclude(status='paid').aggregate(
                total_calc=Sum('calculated_amount'),
                total_paid=Sum('paid_amount'),
            )
            carry_over = max(
                (result['total_calc'] or Decimal('0')) - (result['total_paid'] or Decimal('0')),
                Decimal('0'),
            )

            total_owed = salary.calculated_amount + carry_over
            remaining  = total_owed - salary.paid_amount

            if amount <= 0:
                errors.append({'salary_id': salary_id, 'error': "Summa musbat bo'lishi kerak"})
                continue
            if amount < 10000:
                errors.append({'salary_id': salary_id, 'error': "Minimal to'lov 10,000 so'm"})
                continue
            if amount > remaining:
                amount = remaining  # cap at remaining

            salary.paid_amount += amount
            new_remaining = total_owed - salary.paid_amount

            if new_remaining <= 0 and total_owed > 0:
                salary.status  = 'paid'
                salary.is_paid = True
                salary.paid_at = timezone.now()
            else:
                salary.status = 'partial'

            salary.save()

            teacher_name = salary.teacher.user.get_full_name()
            group_label  = f' ({salary.group.number}{(salary.group.gender_type or "").upper()})' if salary.group else ''
            Expense.objects.create(
                company=salary.company,
                category='teacher_salary',
                source='auto',
                amount=amount,
                description=f"{teacher_name}{group_label} — {salary.month.strftime('%B %Y')} maoshi",
                expense_date=timezone.now().date(),
            )

            results.append(TeacherSalarySerializer(salary).data)

        return Response({'results': results, 'errors': errors})


class StaffSalaryViewSet(CompanyFilterMixin, mixins.CreateModelMixin,
                         mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
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
        if self.action in ('generate', 'pay', 'create'):
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return StaffSalaryCreateSerializer
        return StaffSalarySerializer

    def perform_create(self, serializer):
        serializer.save(company=self._get_active_company())


class StaffKpiRuleViewSet(ArchiveMixin, CompanyFilterMixin, viewsets.ModelViewSet):
    queryset = StaffKpiRule.objects.filter(status='active').order_by('created_at')
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        return [IsBossOrManager()]

    def get_serializer_class(self):
        if self.action == 'create':
            return StaffKpiRuleCreateSerializer
        return StaffKpiRuleSerializer

    def perform_create(self, serializer):
        serializer.save(company=self._get_active_company())
