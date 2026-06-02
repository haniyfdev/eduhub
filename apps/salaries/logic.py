from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta


def _reconcile(salary):
    from decimal import Decimal
    total = salary.calculated_amount + salary.carry_over
    if total <= Decimal('0'):
        status = 'unpaid'
    elif salary.paid_amount >= total:
        status = 'paid'
    elif salary.paid_amount > Decimal('0'):
        status = 'partial'
    else:
        status = 'unpaid'

    if salary.status != status:
        salary.status  = status
        salary.is_paid = status == 'paid'
        if status != 'paid':
            salary.paid_at = None
        salary.save(update_fields=['status', 'is_paid', 'paid_at'])


# Keep old name as alias so existing call sites don't break
_reconcile_status = _reconcile


def calculate_teacher_salary(teacher, month):
    """Calculate salary for a teacher. Fixed type = one record; percent/per_student = per group."""
    from .models import TeacherSalary
    from apps.groups.models import Group, GroupStudent

    if teacher.status in ('frozen', 'archived'):
        return []

    month = month.replace(day=1)
    prev_month = (month - relativedelta(months=1)).replace(day=1)
    kpi_amount = teacher.kpi_bonus or Decimal('0')

    # ── FIXED: ONE salary record, no group, no carry_over ───────────────────
    # Each month is independent — same as staff fixed salary
    if teacher.salary_type == 'fixed':
        base_amount = teacher.fixed_amount or Decimal('0')
        calculated_amount = base_amount + kpi_amount

        salary, _ = TeacherSalary.objects.update_or_create(
            teacher=teacher,
            company=teacher.company,
            month=month,
            group=None,
            defaults={
                'base_amount':       base_amount,
                'kpi_amount':        kpi_amount,
                'total_amount':      calculated_amount,
                'calculated_amount': calculated_amount,
                'carry_over':        Decimal('0'),
                'due_date':          (month + relativedelta(months=1)),
            },
        )
        _reconcile(salary)
        return [salary]

    # ── PERCENT / PER_STUDENT: one record per active group ───────────────────
    active_groups = Group.objects.filter(
        teacher=teacher,
        status='active',
        company=teacher.company,
    ).select_related('course')

    salaries = []
    first_group = True

    for group in active_groups:
        if teacher.salary_type == 'percent':
            enrollments = GroupStudent.objects.filter(
                group=group,
                left_at__isnull=True,
                student__status__in=['active', 'trial', 'frozen'],
            ).select_related('group__course')
            total_revenue = sum(
                gs.group.course.price
                for gs in enrollments
                if gs.group.course and gs.group.course.price
            )
            base_amount = Decimal(str(total_revenue)) * (
                (teacher.salary_percent or Decimal('0')) / 100
            )
        elif teacher.salary_type == 'per_student':
            student_count = GroupStudent.objects.filter(
                group=group,
                left_at__isnull=True,
                student__status='active',
            ).count()
            base_amount = Decimal(str(student_count)) * (
                teacher.per_student_amt or Decimal('0')
            )
        else:
            base_amount = Decimal('0')

        base_amount = Decimal(str(base_amount)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        group_kpi = kpi_amount if first_group else Decimal('0')
        first_group = False
        calculated_amount = base_amount + group_kpi

        prev = TeacherSalary.objects.filter(
            teacher=teacher,
            company=teacher.company,
            month=prev_month,
            group=group,
        ).first()
        carry_over = Decimal('0')
        if prev and prev.status in ('unpaid', 'partial'):
            carry_over = max(
                prev.calculated_amount + prev.carry_over - prev.paid_amount,
                Decimal('0'),
            )

        salary, _ = TeacherSalary.objects.update_or_create(
            teacher=teacher,
            company=teacher.company,
            month=month,
            group=group,
            defaults={
                'base_amount':       base_amount,
                'kpi_amount':        group_kpi,
                'total_amount':      calculated_amount,
                'calculated_amount': calculated_amount,
                'carry_over':        carry_over,
            },
        )
        _reconcile(salary)
        salaries.append(salary)

    return salaries
