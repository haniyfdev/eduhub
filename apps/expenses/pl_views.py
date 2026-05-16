from decimal import Decimal
from django.db.models import Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.permissions import IsSuperAdminOrBossOrManager
from apps.payments.models import Payment
from apps.teachers.models import Teacher
from apps.salaries.models import TeacherSalary
from .models import Expense
import traceback

ALL_EXPENSE_CATEGORIES = [
    'rent', 'utility', 'tax', 'fine',
    'discount', 'teacher_salary', 'staff_salary', 'other',
]

EXPENSE_CATEGORY_LABELS = {
    'rent': 'Ijara', 'utility': 'Kommunal', 'tax': 'Soliq',
    'fine': 'Jarima', 'discount': 'Chegirma',
    'teacher_salary': "O'q. maoshi", 'staff_salary': 'Xodim maoshi', 'other': 'Boshqa',
}


def _parse_month(month_str):
    """Parse '2026-05' → (2026, 5). Returns None if invalid."""
    try:
        year, mon = month_str.split('-')
        return int(year), int(mon)
    except (ValueError, AttributeError):
        return None

class ProfitLossView(APIView):
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        try:
            month_str = request.query_params.get('month')
            year_str = request.query_params.get('year')
            date_from_str = request.query_params.get('date_from')
            date_to_str = request.query_params.get('date_to')

            company = request.user.company if request.user.role != 'superadmin' else None
            company_filter = {} if company is None else {'company': company}

            # 1. Filtrlash qismi
            if date_from_str and date_to_str:
                from datetime import date
                payments_qs = Payment.objects.filter(**company_filter, paid_at__date__range=[date_from_str, date_to_str])
                expenses_qs = Expense.objects.filter(**company_filter, expense_date__range=[date_from_str, date_to_str])
                period = f"{date_from_str} - {date_to_str}"
            elif month_str:
                parsed = _parse_month(month_str)
                if not parsed: return Response({'detail': 'Format: YYYY-MM'}, status=400)
                year, mon = parsed
                payments_qs = Payment.objects.filter(**company_filter, paid_at__year=year, paid_at__month=mon)
                expenses_qs = Expense.objects.filter(**company_filter, expense_date__year=year, expense_date__month=mon)
                period = month_str
            elif year_str:
                payments_qs = Payment.objects.filter(**company_filter, paid_at__year=year_str)
                expenses_qs = Expense.objects.filter(**company_filter, expense_date__year=year_str)
                period = year_str
            else:
                return Response({'detail': 'Parametrlar yetishmayapti'}, status=400)

            # 2. Hisoblash qismi
            total_income = payments_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
            total_expense = expenses_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')

            expense_breakdown = {
                cat: expenses_qs.filter(category=cat).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                for cat in ALL_EXPENSE_CATEGORIES
            }

            return Response({
                'period': period,
                'income': total_income,
                'expenses': total_expense,
                'net_profit': total_income - total_expense,
                'expense_breakdown': expense_breakdown,
                # backward compat
                'total_income': total_income,
                'total_expense': total_expense,
                'profit': total_income - total_expense,
            })

        except Exception as e:
            return Response({'error': str(e)}, status=500)


class ProfitLossHistoryView(APIView):
    """GET /api/v1/profit-loss/history/ — monthly P&L for last 12 months."""
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        from datetime import date
        from dateutil.relativedelta import relativedelta

        company = request.user.company if request.user.role != 'superadmin' else None
        company_filter = {} if company is None else {'company': company}
        today = date.today()
        results = []

        months_count = min(int(request.query_params.get('months', 12)), 24)
        for i in range(months_count - 1, -1, -1):
            d = today - relativedelta(months=i)
            income = Payment.objects.filter(
                **company_filter, paid_at__year=d.year, paid_at__month=d.month
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            expenses = Expense.objects.filter(
                **company_filter, expense_date__year=d.year, expense_date__month=d.month
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            results.append({
                'period': f"{d.year}-{d.month:02d}",
                'income': income,
                'expenses': expenses,
                'profit': income - expenses,
            })
        return Response(results)

        
class ProfitLossTeachersView(APIView):
    """GET /api/v1/profit-loss/teachers/ — per-teacher revenue vs salary."""
    permission_classes = [IsSuperAdminOrBossOrManager]
    def get(self, request):
        try: # endi hullas...

            month_str = request.query_params.get('month')
            parsed = _parse_month(month_str) if month_str else None
            company = request.user.company if request.user.role != 'superadmin' else None
            company_filter = {} if company is None else {'company': company}

            teachers = Teacher.objects.filter(**company_filter, status='active').select_related('user')
            result = []
            for teacher in teachers:
                if parsed:
                    year, mon = parsed
                    revenue = Payment.objects.filter(
                        **company_filter, group__teacher=teacher,
                        paid_at__year=year, paid_at__month=mon,
                    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                    salary_qs = TeacherSalary.objects.filter(
                        teacher=teacher, month__year=year, month__month=mon
                    ).first()
                else:
                    revenue = Decimal('0')
                    salary_qs = None

                result.append({
                    'teacher_id': str(teacher.id),
                    'teacher_name': teacher.user.get_full_name(),
                    'revenue': revenue,
                    'salary': salary_qs.total_amount if salary_qs else Decimal('0'),
                })
            return Response(result)
        
        except Exception as e:
            return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)


class IncomeByCourseView(APIView):
    """GET /api/v1/profit-loss/income-by-course/?month=YYYY-MM"""
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        month_str = request.query_params.get('month')
        company = request.user.company if request.user.role != 'superadmin' else None
        company_filter = {} if company is None else {'company': company}

        qs = Payment.objects.filter(**company_filter)
        if month_str:
            parsed = _parse_month(month_str)
            if parsed:
                year, mon = parsed
                qs = qs.filter(paid_at__year=year, paid_at__month=mon)

        result = (
            qs.values('course__name')
            .annotate(total=Sum('amount'))
            .order_by('-total')
        )
        return Response([
            {'course': r['course__name'] or 'Nomsiz', 'amount': r['total']}
            for r in result
        ])


class DebtForecastView(APIView):
    """GET /api/v1/profit-loss/debt-forecast/"""
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        from apps.debts.models import Debt
        company = request.user.company if request.user.role != 'superadmin' else None
        company_filter = {} if company is None else {'company': company}

        qs = Debt.objects.filter(**company_filter).exclude(status='paid')
        total = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        return Response({
            'total': total,
            'breakdown': {
                'unpaid': qs.filter(status='unpaid').aggregate(t=Sum('amount'))['t'] or Decimal('0'),
                'overdue': qs.filter(status='overdue').aggregate(t=Sum('amount'))['t'] or Decimal('0'),
                'partial': qs.filter(status='partial').aggregate(t=Sum('amount'))['t'] or Decimal('0'),
            },
            'count': {
                'unpaid': qs.filter(status='unpaid').count(),
                'overdue': qs.filter(status='overdue').count(),
                'partial': qs.filter(status='partial').count(),
            },
        })