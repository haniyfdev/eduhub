from decimal import Decimal
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
        qs = qs.filter(
            Q(teacher__status='active') | Q(teacher__status='archived', archive_billing_type__isnull=False)
        ).distinct()
        return qs.filter(
            Q(calculated_amount__gt=0) | Q(paid_amount__gt=0)
        )

    def get_permissions(self):
        if self.action in ('generate', 'calculate', 'pay', 'mark_paid', 'bulk_pay', 'set_amount'):
            return [IsBossOrManagerOrAdmin()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['post'], url_path='set-amount')
    def set_amount(self, request, pk=None):
        """Manually set calculated_amount for a manual-billed archived salary."""
        salary = self.get_object()
        if salary.archive_billing_type != 'manual':
            return Response({'error': 'Only manual billing type can be set this way'}, status=400)
        try:
            amount = Decimal(str(request.data.get('amount', '')))
            if amount < 0:
                raise ValueError
        except Exception:
            return Response({'error': 'Invalid amount'}, status=400)
        salary.calculated_amount = amount
        salary.save(update_fields=['calculated_amount'])
        return Response({'calculated_amount': float(salary.calculated_amount), 'manual_amount_set': salary.manual_amount_set})

    @action(detail=True, methods=['get'], url_path='last-month-breakdown')
    def last_month_breakdown(self, request, pk=None):
        """Read-only breakdown of an archived teacher's prorated salary."""
        from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
        import datetime as dt
        from apps.lessons.models import Lesson

        salary = self.get_object()
        teacher = salary.teacher

        if teacher.status != 'archived' or not teacher.archived_at:
            return Response({'error': 'Teacher is not archived'}, status=400)

        billing_type = salary.archive_billing_type or 'manual'
        archived_at  = teacher.archived_at.date()
        month_start  = salary.month

        # full_monthly is the salary BEFORE archive proration — total_amount is never overwritten
        full_monthly = Decimal(str(salary.total_amount))

        # Teacher salary settings for display
        salary_type     = teacher.salary_type          # 'fixed' | 'percent' | 'per_student'
        salary_percent  = float(teacher.salary_percent or 0)
        per_student_amt = float(teacher.per_student_amt or 0)

        # Students and revenue for display chain (uses current enrollment as approximation)
        students_count = 0
        group_revenue  = 0.0
        course_price   = 0.0
        if salary.group_id:
            from apps.groups.models import GroupStudent
            students_count = GroupStudent.objects.filter(
                group_id=salary.group_id,
                left_at__isnull=True,
                student__status__in=['active', 'trial', 'frozen'],
            ).count()
            if salary.group.course and salary.group.course.price:
                course_price  = float(salary.group.course.price)
                group_revenue = students_count * course_price

        if teacher.salary_type == 'fixed' and billing_type != 'full':
            billing_type = 'manual'

        raw_amount        = None
        calculated_amount = None
        per_unit          = None
        units_count       = None
        total_units       = None
        unit_label        = None

        if billing_type == 'manual':
            calculated_amount = salary.calculated_amount

        elif billing_type == 'per_day':
            days_in_month = 30
            days_worked   = (archived_at - month_start).days + 1
            per_unit          = (full_monthly / days_in_month).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            units_count       = days_worked
            total_units       = days_in_month
            raw_amount        = per_unit * days_worked
            calculated_amount = (raw_amount / 1000).to_integral_value(rounding=ROUND_FLOOR) * 1000
            unit_label        = 'day'

        elif billing_type == 'per_lesson' and not salary.group_id:
            # Fixed salary type: no group attached, per-lesson proration is not possible.
            # Archive action also skipped proration for the same reason; calculated_amount
            # was left as the full fixed amount. Treat as 'full' so the modal renders it.
            billing_type = 'full'

        elif billing_type == 'per_lesson' and salary.group_id:
            from dateutil.relativedelta import relativedelta

            taught = Lesson.objects.filter(
                group_id=salary.group_id,
                teacher=teacher,
                date__gte=month_start,
                date__lte=archived_at,
                status='finished',
            ).count()

            DAY_MAP = {
                'du': 0, 'se': 1, 'ch': 2, 'cho': 2,
                'pa': 3, 'ju': 4, 'sh': 5, 'sha': 5, 'ya': 6,
            }
            schedule_str = salary.group.schedule or ''
            days_part = schedule_str.split(' ')[0]
            lesson_weekdays: set = set()
            for abbr in days_part.split(','):
                key = abbr.strip().lower()
                if key in DAY_MAP:
                    lesson_weekdays.add(DAY_MAP[key])

            total_in_cycle = 0
            if lesson_weekdays:
                d = month_start
                cycle_end = month_start + relativedelta(months=1)
                while d < cycle_end:
                    if d.weekday() in lesson_weekdays:
                        total_in_cycle += 1
                    d += dt.timedelta(days=1)
            if total_in_cycle == 0:
                total_in_cycle = 12

            # Divide full_monthly (not already-prorated amount) to get correct per-lesson rate
            per_unit          = (full_monthly / total_in_cycle).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            units_count       = taught
            total_units       = total_in_cycle
            raw_amount        = per_unit * taught
            calculated_amount = (raw_amount / 1000).to_integral_value(rounding=ROUND_FLOOR) * 1000
            unit_label        = 'lesson'

        return Response({
            'teacher_name':        f"{teacher.user.first_name} {teacher.user.last_name}",
            'group_name':          salary.group.display_name if salary.group else None,
            'course_name':         salary.group.course.name if salary.group and salary.group.course else None,
            'month':               month_start.strftime('%Y-%m'),
            'archived_at':         archived_at.strftime('%d/%m/%Y'),
            'billing_type':          billing_type,
            'billing_type_original': salary.archive_billing_type,
            'salary_type':         salary_type,
            'salary_percent':      salary_percent,
            'per_student_amt':     per_student_amt,
            'students_count':      students_count,
            'group_revenue':       group_revenue,
            'course_price':        course_price,
            'full_monthly_salary': float(full_monthly),
            'base_amount':         float(full_monthly),  # kept for compat — equals full_monthly
            'raw_amount':          float(raw_amount) if raw_amount is not None else None,
            'calculated_amount':   float(calculated_amount) if calculated_amount is not None else None,
            'per_unit':            float(per_unit) if per_unit is not None else None,
            'units_count':         units_count,
            'total_units':         total_units,
            'unit_label':          unit_label,
            'manual_amount_set':   salary.manual_amount_set,
        })

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
                    'teacher_status': salary.teacher.status,
                    'teacher_archived_at': salary.teacher.archived_at.isoformat() if salary.teacher.archived_at else None,
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
            kpi = float(salary.kpi_amount or 0)

            # Self-heal: fixed-salary teachers archived with per_lesson policy were not prorated
            # at archive time. Recompute per_day, fix the DB record, and use the correct value.
            display_calculated = float(salary.calculated_amount)
            if (
                salary.teacher.status == 'archived'
                and sdata.get('salary_type') == 'fixed'
                and salary.archive_billing_type == 'per_lesson'
                and salary.teacher.archived_at
                and salary.total_amount
            ):
                from decimal import Decimal, ROUND_FLOOR as _FLOOR
                _archived = salary.teacher.archived_at.date()
                _start = salary.month
                _days = max((_archived - _start).days + 1, 1)
                _base = Decimal(str(salary.total_amount))
                _raw = (_base / 30) * _days
                _correct = int((_raw / 1000).to_integral_value(rounding=_FLOOR) * 1000)
                if salary.calculated_amount != _correct:
                    salary.calculated_amount = _correct
                    salary.save(update_fields=['calculated_amount'])
                display_calculated = float(_correct)

            total_owed = display_calculated + carry_over

            entry['kpi_amount'] = max(float(entry['kpi_amount']), kpi)
            entry['total_calculated'] += display_calculated
            entry['total_paid'] += float(salary.paid_amount)
            entry['total_owed'] += total_owed

            entry['groups'].append({
                'salary_id':          str(salary.id),
                'group_id':           sdata['group_id'],
                'group_name':         sdata['group_name'],
                'course_name':        sdata['course_name'],
                'calculated_amount':  display_calculated,
                'paid_amount':        float(salary.paid_amount),
                'carry_over':         carry_over,
                'total_owed':         total_owed,
                'status':             salary.status,
                'due_date':           sdata['due_date'],
                'first_active_date':  sdata['first_active_date'],
                'student_count':      sdata['student_count'],
                'course_price':       float(sdata['course_price'] or 0),
                'kpi_amount':         kpi,
                'archive_billing_type': salary.archive_billing_type,
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

            if entry['salary_type'] == 'fixed' and entry.get('teacher_status') != 'archived':
                # Active fixed-salary teacher: replace null-group entry with actual groups for display.
                # Skip for archived teachers — their groups may have been reassigned and the
                # null-group entry is needed to carry the salary_id for the breakdown modal.
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
                        'calculated_amount': 0,
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
                if display_groups:
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
