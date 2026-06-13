from utils.mixins import get_active_company
from decimal import Decimal
from datetime import date
from django.db.models import Sum, Count, Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class DashboardSummaryView(APIView):
    """GET /api/v1/dashboard/summary/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.students.models import Student
        from apps.groups.models import Group
        from apps.payments.models import Payment
        from apps.debts.models import Debt
        from apps.teachers.models import Teacher

        company = get_active_company(request)
        today = date.today()

        students = Student.objects.filter(company=company)
        active_students = students.filter(status='active')
        groups = Group.objects.filter(company=company)
        monthly_revenue = Payment.objects.filter(
            company=company, paid_at__year=today.year, paid_at__month=today.month
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        debt_stats = Debt.objects.filter(company=company).aggregate(
            total_debtors=Count('id', filter=~Q(status='paid')),
            total_debt_amount=Sum('amount', filter=~Q(status='paid')),
        )

        return Response({
            'total_students': students.count(),
            'active_students': active_students.count(),
            'pending_students': students.filter(status='pending').count(),
            'trial_students': students.filter(status='trial').count(),
            'total_groups': groups.count(),
            'active_groups': groups.filter(status='active').count(),
            'monthly_revenue': monthly_revenue,
            'total_debtors': debt_stats['total_debtors'] or 0,
            'total_debt_amount': debt_stats['total_debt_amount'] or Decimal('0'),
            'teachers_count': Teacher.objects.filter(company=company, status='active').count(),
        })


class DashboardRevenueView(APIView):
    """GET /api/v1/dashboard/revenue/?period=6"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.payments.models import Payment
        from dateutil.relativedelta import relativedelta

        company = get_active_company(request)
        try:
            period = int(request.query_params.get('period', 6))
        except ValueError:
            period = 6

        period = min(max(period, 1), 24)
        today = date.today()
        labels, data = [], []

        for i in range(period - 1, -1, -1):
            d = today - relativedelta(months=i)
            total = Payment.objects.filter(
                company=company, paid_at__year=d.year, paid_at__month=d.month
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
            labels.append(d.strftime('%b'))
            data.append(total)

        return Response({'labels': labels, 'data': data})


class DashboardDebtsSummaryView(APIView):
    """GET /api/v1/dashboard/debts-summary/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.debts.models import Debt
        from django.db.models import Count, Sum

        company = get_active_company(request)
        rows = Debt.objects.filter(company=company).values('status').annotate(
            count=Count('id'), total=Sum('amount')
        )
        summary = {row['status']: {'count': row['count'], 'total': row['total']} for row in rows}

        for s in ('unpaid', 'partial', 'paid', 'overdue'):
            summary.setdefault(s, {'count': 0, 'total': Decimal('0')})

        return Response(summary)


class DashboardTeacherStatsView(APIView):
    """GET /api/v1/dashboard/teacher-stats/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.teachers.models import Teacher
        from apps.groups.models import GroupStudent
        from apps.payments.models import Payment

        company = get_active_company(request)
        today = date.today()
        teachers = Teacher.objects.filter(company=company, status='active').select_related('user')
        result = []

        for teacher in teachers:
            active_students = GroupStudent.objects.filter(
                group__teacher=teacher, group__status='active', left_at__isnull=True
            ).count()
            monthly_revenue = Payment.objects.filter(
                company=company, group_student__group__teacher=teacher,
                paid_at__year=today.year, paid_at__month=today.month,
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
            result.append({
                'teacher_id': str(teacher.id),
                'teacher_name': teacher.user.get_full_name(),
                'active_students': active_students,
                'active_groups': teacher.groups.filter(status='active').count(),
                'monthly_revenue': monthly_revenue,
            })

        return Response(result)
