from decimal import Decimal

from dateutil.relativedelta import relativedelta
from apps.groups.models import GroupStudent


def calculate_teacher_salary(teacher, month):
    from .models import TeacherSalary

    if teacher.salary_type == 'fixed':
        base_amount = teacher.fixed_amount or Decimal('0')

    elif teacher.salary_type == 'percent':
        enrollments = GroupStudent.objects.filter(
            group__teacher=teacher,
            group__status='active',
            left_at__isnull=True,
        ).select_related('group__course')
        total_course_revenue_due = sum(gs.group.course.price for gs in enrollments)
        base_amount = total_course_revenue_due * (teacher.salary_percent / 100)

    elif teacher.salary_type == 'per_student':
        student_count = GroupStudent.objects.filter(
            group__teacher=teacher,
            group__status='active',
            left_at__isnull=True,
        ).count()
        base_amount = Decimal(student_count) * (teacher.per_student_amt or Decimal('0'))

    else:
        base_amount = Decimal('0')

    kpi_amount = teacher.kpi_bonus or Decimal('0')

    # Apply contract-break policy if teacher was archived this month
    try:
        policy = teacher.company.settings.teacher_contract_break_policy
    except Exception:
        policy = 'full'

    if (
        teacher.status == 'archived'
        and teacher.archived_at
        and teacher.archived_at.date().replace(day=1) == month.replace(day=1)
        and policy != 'full'
    ):
        if policy == 'none':
            base_amount = Decimal('0')
            kpi_amount  = Decimal('0')
        elif policy == 'prorate':
            days_worked = (teacher.archived_at.date() - month).days
            fraction    = max(Decimal('0'), min(Decimal('1'), Decimal(days_worked) / Decimal('30')))
            base_amount = base_amount * fraction
            kpi_amount  = kpi_amount  * fraction

    calculated_amount = base_amount + kpi_amount

    # Carry-over: unpaid balance from the previous month
    prev_month = (month - relativedelta(months=1)).replace(day=1)
    prev_salary = TeacherSalary.objects.filter(
        teacher=teacher,
        company=teacher.company,
        month=prev_month,
    ).first()

    carry_over = Decimal('0')
    if prev_salary and prev_salary.status in ('unpaid', 'partial'):
        carry_over = prev_salary.calculated_amount + prev_salary.carry_over - prev_salary.paid_amount

    salary, _ = TeacherSalary.objects.update_or_create(
        teacher=teacher,
        company=teacher.company,
        month=month.replace(day=1),
        defaults={
            'base_amount':       base_amount,
            'kpi_amount':        kpi_amount,
            'total_amount':      calculated_amount,
            'calculated_amount': calculated_amount,
            'carry_over':        carry_over,
        },
    )

    # Reconcile status with actual payment state — guards against
    # recalculation bumping calculated_amount above paid_amount on a
    # previously-paid record, or a ghost 'paid' from a zero-amount cycle.
    total = salary.calculated_amount + salary.carry_over
    if total <= 0:
        correct_status = 'unpaid'
    elif salary.paid_amount >= total:
        correct_status = 'paid'
    elif salary.paid_amount > 0:
        correct_status = 'partial'
    else:
        correct_status = 'unpaid'

    if salary.status != correct_status:
        salary.status  = correct_status
        salary.is_paid = correct_status == 'paid'
        if correct_status != 'paid':
            salary.paid_at = None
        salary.save(update_fields=['status', 'is_paid', 'paid_at'])

    return salary
