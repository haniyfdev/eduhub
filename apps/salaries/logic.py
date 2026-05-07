from decimal import Decimal

from apps.groups.models import GroupStudent


def calculate_teacher_salary(teacher, month):
    from .models import TeacherSalary

    if teacher.salary_type == 'fixed':
        base_amount = teacher.fixed_amount

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
        base_amount = student_count * teacher.per_student_amt

    else:
        base_amount = Decimal('0')

    kpi_amount = teacher.kpi_bonus or Decimal('0')

    # Apply teacher_contract_break_policy if teacher was archived this month
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
            kpi_amount = Decimal('0')
        elif policy == 'prorate':
            days_worked = (teacher.archived_at.date() - month).days
            days_in_month = Decimal('30')
            fraction = max(Decimal('0'), min(Decimal('1'), Decimal(days_worked) / days_in_month))
            base_amount = base_amount * fraction
            kpi_amount = kpi_amount * fraction

    total_amount = base_amount + kpi_amount

    salary = TeacherSalary.objects.create(
        teacher=teacher,
        company=teacher.company,
        month=month,
        base_amount=base_amount,
        kpi_amount=kpi_amount,
        total_amount=total_amount,
    )
    return salary
