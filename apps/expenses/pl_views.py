from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from dateutil.relativedelta import relativedelta
from rest_framework.response import Response
from rest_framework.views import APIView
import traceback

from utils.permissions import IsSuperAdminOrBossOrManager
from utils.mixins import resolve_company_id
from apps.payments.models import Payment
from apps.teachers.models import Teacher
from apps.salaries.models import TeacherSalary
from apps.staff.models import StaffSalary as StaffMemberSalary
from .models import Expense


def _parse_date_range(request):
    today = date.today()

    month_param = request.query_params.get('month')
    if month_param:
        try:
            year, mon = month_param.split('-')
            from_date = date(int(year), int(mon), 1)
            to_date = (from_date + relativedelta(months=1)) - timedelta(days=1)
            return from_date, to_date
        except (ValueError, AttributeError):
            pass

    year_param = request.query_params.get('year')
    if year_param:
        try:
            y = int(year_param)
            return date(y, 1, 1), date(y, 12, 31)
        except ValueError:
            pass

    default_from = today.replace(day=1)
    from_str = request.query_params.get('from_date', str(default_from))
    to_str   = request.query_params.get('to_date',   str(today))
    try:
        from_date = date.fromisoformat(from_str)
    except (ValueError, AttributeError):
        from_date = default_from
    try:
        to_date = date.fromisoformat(to_str)
    except (ValueError, AttributeError):
        to_date = today
    return from_date, to_date


def _salary_totals(cf):
    """Return (teacher_paid, staff_paid) — all paid_amount > 0 regardless of paid_at date."""
    teacher_paid = TeacherSalary.objects.filter(
        **cf,
        paid_amount__gt=0,
    ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')

    staff_paid = StaffMemberSalary.objects.filter(
        **cf,
        paid_amount__gt=0,
    ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')

    return teacher_paid, staff_paid


def _manual_totals(manual_qs):
    def _s(cat):
        return manual_qs.filter(category=cat).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    return {
        'rent':     _s('rent'),
        'utility':  _s('utility'),
        'tax':      _s('tax'),
        'fine':     _s('fine'),
        'discount': _s('discount'),
        'other':    _s('other'),
    }


class ProfitLossView(APIView):
    """GET /api/v1/profit-loss/?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD"""
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        if not request.query_params.get('month') and not request.query_params.get('year'):
            return Response({'error': "'month' or 'year' parameter required"}, status=400)

        try:
            from_date, to_date = _parse_date_range(request)
            company_id = None if request.user.role == 'superadmin' else resolve_company_id(request)
            cf = {} if company_id is None else {'company_id': company_id}

            total_income = Payment.objects.filter(
                **cf, paid_at__date__gte=from_date, paid_at__date__lte=to_date
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

            teacher_paid, staff_paid = _salary_totals(cf)

            # Manual expenses only (exclude auto-mirrored salary rows)
            manual_qs = Expense.objects.filter(
                **cf,
                expense_date__gte=from_date,
                expense_date__lte=to_date,
            ).exclude(category__in=['teacher_salary', 'staff_salary'])

            cats = _manual_totals(manual_qs)
            breakdown = {
                'rent':           cats['rent'],
                'utility':        cats['utility'],
                'tax':            cats['tax'],
                'fine':           cats['fine'],
                'discount':       cats['discount'],
                'teacher_salary': teacher_paid,
                'staff_salary':   staff_paid,
                'other':          cats['other'],
            }
            total_expense = sum(breakdown.values())
            profit        = total_income - total_expense

            # Stats (not date-filtered — current state)
            from apps.leads.models   import Lead
            from apps.students.models import Student
            from apps.groups.models  import Group
            from apps.debts.models   import Debt

            debts_qs = Debt.objects.filter(**cf, status__in=['unpaid', 'partial', 'overdue'])
            stats = {
                'total_leads':       Lead.objects.filter(**cf).count(),
                'active_students':   Student.objects.filter(**cf, status='active').count(),
                'active_teachers':   Teacher.objects.filter(**cf, status='active').count(),
                'active_groups':     Group.objects.filter(**cf, status='active').count(),
                'total_debtors':     debts_qs.count(),
                'total_debt_amount': debts_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0'),
            }

            return Response({
                'from_date': str(from_date),
                'to_date':   str(to_date),
                'income':   {'total': total_income},
                'expenses': {
                    'total':     total_expense,
                    'breakdown': breakdown,
                },
                'profit':         profit,
                'margin':         float(profit / total_income * 100) if total_income else 0,
                'expense_percent': float(total_expense / total_income * 100) if total_income else 0,
                'stats': stats,
            })

        except Exception as e:
            return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)


class ProfitLossHistoryView(APIView):
    """GET /api/v1/profit-loss/history/?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&group_by=day|month"""
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        from_date, to_date = _parse_date_range(request)
        company_id = None if request.user.role == 'superadmin' else resolve_company_id(request)
        cf = {} if company_id is None else {'company_id': company_id}
        group_by = request.query_params.get('group_by', 'month')

        results = []

        if group_by == 'day':
            current = from_date
            while current <= to_date:
                income = Payment.objects.filter(
                    **cf, paid_at__date=current,
                ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

                teacher_m = TeacherSalary.objects.filter(
                    **cf, paid_at__date=current, paid_amount__gt=0,
                ).aggregate(t=Sum('paid_amount'))['t'] or Decimal('0')

                staff_m = StaffMemberSalary.objects.filter(
                    **cf, paid_at__date=current, paid_amount__gt=0,
                ).aggregate(t=Sum('paid_amount'))['t'] or Decimal('0')

                manual_m = Expense.objects.filter(
                    **cf, expense_date=current,
                ).exclude(category__in=['teacher_salary', 'staff_salary']).aggregate(
                    t=Sum('amount')
                )['t'] or Decimal('0')

                expenses = teacher_m + staff_m + manual_m
                results.append({
                    'date':     current.strftime('%Y-%m-%d'),
                    'label':    current.strftime('%d/%m'),
                    'income':   income,
                    'expenses': expenses,
                    'profit':   income - expenses,
                })
                current += timedelta(days=1)
        else:
            current = from_date.replace(day=1)
            while current <= to_date:
                next_month = current + relativedelta(months=1)
                month_from = max(from_date, current)
                month_to   = min(to_date, next_month - timedelta(days=1))

                income = Payment.objects.filter(
                    **cf, paid_at__date__gte=month_from, paid_at__date__lte=month_to,
                ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

                teacher_m = TeacherSalary.objects.filter(
                    **cf,
                    paid_at__date__gte=month_from,
                    paid_at__date__lte=month_to,
                    paid_amount__gt=0,
                ).aggregate(t=Sum('paid_amount'))['t'] or Decimal('0')

                staff_m = StaffMemberSalary.objects.filter(
                    **cf,
                    paid_at__date__gte=month_from,
                    paid_at__date__lte=month_to,
                    paid_amount__gt=0,
                ).aggregate(t=Sum('paid_amount'))['t'] or Decimal('0')

                manual_m = Expense.objects.filter(
                    **cf,
                    expense_date__gte=month_from,
                    expense_date__lte=month_to,
                ).exclude(category__in=['teacher_salary', 'staff_salary']).aggregate(
                    t=Sum('amount')
                )['t'] or Decimal('0')

                expenses = teacher_m + staff_m + manual_m
                results.append({
                    'month':    current.strftime('%Y-%m'),
                    'income':   income,
                    'expenses': expenses,
                    'profit':   income - expenses,
                })
                current = next_month

        return Response(results)


class ProfitLossTeachersView(APIView):
    """GET /api/v1/profit-loss/teachers/?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD"""
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        try:
            from_date, to_date = _parse_date_range(request)
            company_id = None if request.user.role == 'superadmin' else resolve_company_id(request)
            cf = {} if company_id is None else {'company_id': company_id}

            teachers = Teacher.objects.filter(**cf, status='active').select_related('user')
            result = []
            for teacher in teachers:
                revenue = Payment.objects.filter(
                    **cf, group_student__group__teacher=teacher,
                    paid_at__date__gte=from_date, paid_at__date__lte=to_date,
                ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

                salary = TeacherSalary.objects.filter(
                    teacher=teacher,
                    month__gte=from_date.replace(day=1),
                    month__lte=to_date,
                ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')

                result.append({
                    'teacher_id':   str(teacher.id),
                    'teacher_name': teacher.user.get_full_name(),
                    'revenue':      revenue,
                    'salary':       salary,
                })
            return Response(result)

        except Exception as e:
            return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)


class IncomeByCourseView(APIView):
    """GET /api/v1/profit-loss/income-by-course/?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD"""
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        from_date, to_date = _parse_date_range(request)
        company_id = None if request.user.role == 'superadmin' else resolve_company_id(request)
        cf = {} if company_id is None else {'company_id': company_id}

        result = (
            Payment.objects
            .filter(**cf, paid_at__date__gte=from_date, paid_at__date__lte=to_date)
            .values('group_student__group__course__name')
            .annotate(total=Sum('amount'))
            .order_by('-total')
        )
        return Response([
            {'course': r['group_student__group__course__name'] or 'Nomsiz', 'amount': r['total']}
            for r in result
        ])


class DebtForecastView(APIView):
    """GET /api/v1/profit-loss/debt-forecast/"""
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        from apps.debts.models import Debt
        company_id = None if request.user.role == 'superadmin' else resolve_company_id(request)
        cf = {} if company_id is None else {'company_id': company_id}

        qs = Debt.objects.filter(**cf).exclude(status='paid')
        total = qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')

        return Response({
            'total': total,
            'breakdown': {
                'unpaid':  qs.filter(status='unpaid').aggregate(t=Sum('amount'))['t']  or Decimal('0'),
                'overdue': qs.filter(status='overdue').aggregate(t=Sum('amount'))['t'] or Decimal('0'),
                'partial': qs.filter(status='partial').aggregate(t=Sum('amount'))['t'] or Decimal('0'),
            },
            'count': {
                'unpaid':  qs.filter(status='unpaid').count(),
                'overdue': qs.filter(status='overdue').count(),
                'partial': qs.filter(status='partial').count(),
            },
        })
