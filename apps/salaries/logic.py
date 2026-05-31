from decimal import Decimal
from dateutil.relativedelta import relativedelta


def calculate_group_salary(teacher, group):
    """Return salary data dict for one teacher+group, or None if no active students ever."""
    from apps.groups.models import GroupStudent

    first_active = GroupStudent.objects.filter(
        group=group,
        student__status__in=['active', 'archived'],
    ).order_by('joined_at').first()

    if not first_active:
        return None

    first_active_date = first_active.joined_at
    first_date = first_active_date.date() if hasattr(first_active_date, 'date') else first_active_date
    due_date = first_date + relativedelta(months=1)

    student_count = GroupStudent.objects.filter(
        group=group,
        left_at__isnull=True,
        student__status='active',
    ).count()

    course_price = group.course.price if group.course else Decimal('0')

    if teacher.salary_type == 'fixed':
        amount = teacher.fixed_amount or Decimal('0')
    elif teacher.salary_type == 'percent':
        group_revenue = course_price * Decimal(student_count)
        amount = group_revenue * (teacher.salary_percent or Decimal('0')) / 100
    elif teacher.salary_type == 'per_student':
        amount = Decimal(student_count) * (teacher.per_student_amt or Decimal('0'))
    else:
        amount = Decimal('0')

    return {
        'calculated_amount': amount,
        'due_date': due_date,
        'student_count': student_count,
        'course_price': course_price,
        'first_active_date': first_active_date,
    }


def _reconcile_status(salary):
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
        salary.status = correct_status
        salary.is_paid = correct_status == 'paid'
        if correct_status != 'paid':
            salary.paid_at = None
        salary.save(update_fields=['status', 'is_paid', 'paid_at'])


def calculate_teacher_salary(teacher, month):
    """Calculate salary per group for a teacher. Returns list of TeacherSalary instances."""
    if teacher.status in ('frozen', 'archived'):
        return []
    from apps.groups.models import Group
    from .models import TeacherSalary

    groups = Group.objects.filter(
        teacher=teacher,
        status='active',
        company=teacher.company,
    ).select_related('course')

    created_salaries = []
    first_group = True

    for group in groups:
        if not group:
            continue
        data = calculate_group_salary(teacher, group)
        if data is None:
            continue

        # KPI only on the first group to avoid duplication
        kpi_amount = (teacher.kpi_bonus or Decimal('0')) if first_group else Decimal('0')
        first_group = False

        base = data['calculated_amount']
        calculated_amount = base + kpi_amount

        salary, _ = TeacherSalary.objects.update_or_create(
            teacher=teacher,
            group=group,
            company=teacher.company,
            month=month.replace(day=1),
            defaults={
                'base_amount':       base,
                'kpi_amount':        kpi_amount,
                'total_amount':      calculated_amount,
                'calculated_amount': calculated_amount,
                'due_date':          data['due_date'],
            },
        )
        _reconcile_status(salary)
        created_salaries.append(salary)

    return created_salaries
