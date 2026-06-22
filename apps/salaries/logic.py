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
    """Calculate salary for a teacher. Fixed type = one record; percent/per_student = per group.

    percent:     salary = group_debt_sum × (percent / 100)
    per_student: salary = group_debt_sum × (per_student_amt / course_price)
    fixed:       salary = fixed_amount  (unchanged, ignores debt records)

    group_debt_sum = sum of Debt.amount for all GroupStudents in the group
    where Debt.due_date falls within the billing month being calculated.
    """
    from .models import TeacherSalary
    from apps.groups.models import Group
    from apps.debts.models import Debt
    from apps.payments.models import Payment
    from django.db.models import Sum

    if teacher.status == 'frozen':
        return []

    month = month.replace(day=1)
    prev_month = (month - relativedelta(months=1)).replace(day=1)
    kpi_amount = teacher.kpi_bonus or Decimal('0')

    # ── ARCHIVED: apply teacher_contract_break_policy (full/prorate/none) ───
    if teacher.status == 'archived':
        if teacher.salary_type != 'fixed':
            return []

        from apps.companies.models import CompanySettings
        cs = CompanySettings.objects.filter(company=teacher.company).first()
        policy = cs.teacher_contract_break_policy if cs else 'full'

        base_amount = teacher.fixed_amount or Decimal('0')
        if policy == 'none':
            base_amount = Decimal('0')
        elif policy != 'full' and teacher.archived_at:
            days_worked = (teacher.archived_at.date() - month).days
            base_amount = base_amount * (Decimal(days_worked) / Decimal('30'))

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
        # Previous month's salary — used for carry_over only
        prev = TeacherSalary.objects.filter(
            teacher=teacher,
            company=teacher.company,
            month=prev_month,
            group=group,
        ).first()

        # Sum of debts for the billing month.  billing_month is set by the
        # scheduler when a debt cycle closes (before due_date rolls forward),
        # so it stays correct even after the debt has been rolled to the next
        # month.  Fall back to due_date filtering for old debts without it.
        from django.db.models import Q
        agg = Debt.objects.filter(
            group_student__group=group,
            company=teacher.company,
        ).filter(
            Q(billing_month__year=month.year, billing_month__month=month.month) |
            Q(billing_month__isnull=True, due_date__year=month.year, due_date__month=month.month)
        ).aggregate(total=Sum('amount'))
        remaining_debt_sum = Decimal(str(agg['total'] or 0))

        # Debt.amount is drawn down to 0 as a student pays (see payments/serializers.py),
        # but salary must not depend on payment status (Rule 9: "the teacher did the
        # work regardless of whether the student paid"). Add back this month's payments
        # so paid-off debts still count at their original invoiced amount.
        paid_agg = Payment.objects.filter(
            group_student__group=group,
            company=teacher.company,
            paid_at__year=month.year,
            paid_at__month=month.month,
        ).aggregate(total=Sum('amount'))
        payments_this_month = Decimal(str(paid_agg['total'] or 0))

        group_debt_sum = remaining_debt_sum + payments_this_month

        if teacher.salary_type == 'percent':
            coefficient = (teacher.salary_percent or Decimal('0')) / 100
            base_amount = group_debt_sum * coefficient

        elif teacher.salary_type == 'per_student':
            course_price = (
                Decimal(str(group.course.price))
                if group.course and group.course.price
                else None
            )
            if course_price and course_price > 0:
                coefficient = (teacher.per_student_amt or Decimal('0')) / course_price
                base_amount = group_debt_sum * coefficient
            else:
                base_amount = Decimal('0')

        else:
            base_amount = Decimal('0')

        base_amount = Decimal(str(base_amount)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        group_kpi = kpi_amount if first_group else Decimal('0')
        first_group = False
        calculated_amount = base_amount + group_kpi

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
