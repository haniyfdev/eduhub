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

        date_from_str = request.query_params.get('date_from')
        date_to_str   = request.query_params.get('date_to')

        if date_from_str and date_to_str:
            from datetime import date
            try:
                date_from = date.fromisoformat(date_from_str)
                date_to   = date.fromisoformat(date_to_str)
            except ValueError:
                return Response({'detail': 'Use YYYY-MM-DD format.'}, status=400)
            payments_qs = Payment.objects.filter(
                **company_filter, paid_at__date__gte=date_from, paid_at__date__lte=date_to
            )
            expenses_qs = Expense.objects.filter(
                **company_filter, expense_date__gte=date_from, expense_date__lte=date_to
            )
            period = f"{date_from_str} — {date_to_str}"
        elif month_str:
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
            return Response({'detail': 'Provide ?month=YYYY-MM or ?year=YYYY or ?date_from&date_to.'}, status=400)


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

import traceback

def get(self, request):
    try:
                
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

    
    except Exception as e:
        return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)