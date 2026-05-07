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

ALL_EXPENSE_CATEGORIES = [
    'rent', 'utility', 'tax', 'fine',
    'discount', 'teacher_salary', 'staff_salary', 'other',
]


def _parse_month(month_str):
    """Parse '2026-05' → (2026, 5). Returns None if invalid."""
    try:
        year, mon = month_str.split('-')
        return int(year), int(mon)
    except (ValueError, AttributeError):
        return None


class ProfitLossView(APIView):
    """GET /api/v1/profit-loss/?month=2026-05"""
    permission_classes = [IsSuperAdminOrBossOrManager]

    def get(self, request):
        month_str = request.query_params.get('month')
        year_str = request.query_params.get('year')

        company = request.user.company if request.user.role != 'superadmin' else None

        company_filter = {} if company is None else {'company': company}

        if month_str:
            parsed = _parse_month(month_str)
            if not parsed:
                return Response({'detail': 'Invalid month format. Use YYYY-MM.'}, status=400)
            year, mon = parsed
            payments_qs = Payment.objects.filter(
                **company_filter, paid_at__year=year, paid_at__month=mon
            )
            expenses_qs = Expense.objects.filter(
                **company_filter, expense_date__year=year, expense_date__month=mon
            )
            period = month_str
        elif year_str:
            try:
                year = int(year_str)
            except ValueError:
                return Response({'detail': 'Invalid year.'}, status=400)
            payments_qs = Payment.objects.filter(**company_filter, paid_at__year=year)
            expenses_qs = Expense.objects.filter(**company_filter, expense_date__year=year)
            period = year_str
        else:
            return Response({'detail': 'Provide ?month=YYYY-MM or ?year=YYYY.'}, status=400)

        income = payments_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        expense_data = expenses_qs.values('category').annotate(total=Sum('amount'))
        expense_map = {row['category']: row['total'] for row in expense_data}

        # Rule: all 8 categories always present, even at 0
        breakdown = {cat: expense_map.get(cat, Decimal('0')) for cat in ALL_EXPENSE_CATEGORIES}
        total_expenses = sum(breakdown.values())
        profit = income - total_expenses
        margin = (profit / income * 100) if income > 0 else Decimal('0')

        # Income breakdown by course
        income_by_course = (
            payments_qs.values('course__name')
            .annotate(amount=Sum('amount'))
            .order_by('-amount')
        )

        return Response({
            'period': period,
            'income': {
                'total': income,
                'breakdown': [
                    {'course': row['course__name'], 'amount': row['amount']}
                    for row in income_by_course
                ],
            },
            'expenses': {
                'total': total_expenses,
                'breakdown': breakdown,
            },
            'profit': profit,
            'margin': f"{margin:.1f}%",
        })


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

        for i in range(11, -1, -1):
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
