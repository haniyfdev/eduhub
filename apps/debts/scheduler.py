import logging

logger = logging.getLogger(__name__)


def generate_monthly_debts():
    from datetime import date
    from decimal import Decimal
    from dateutil.relativedelta import relativedelta
    from apps.groups.models import GroupStudent
    from apps.debts.models import Debt

    today = date.today()
    updated = 0
    skipped = 0

    active_enrollments = GroupStudent.objects.filter(
        group__status='active',
        left_at__isnull=True,
    ).select_related('student', 'group__course')

    for gs in active_enrollments:
        if gs.student.status == 'frozen':
            skipped += 1
            continue

        if not gs.group.course or not gs.group.course.price:
            skipped += 1
            continue

        try:
            debt = Debt.objects.get(group_student=gs)
        except Debt.DoesNotExist:
            skipped += 1
            continue

        if debt.due_date > today:
            skipped += 1
            continue

        course_price = gs.group.course.price
        current_month = today.replace(day=1)
        active_discount = None
        try:
            from apps.discounts.models import Discount
            active_discount = Discount.objects.filter(
                student=gs.student,
                course=gs.group.course,
                start_month__lte=current_month,
                end_month__gte=current_month,
            ).first()
        except Exception:
            pass

        if active_discount:
            discount_amount = Decimal(str(course_price)) * active_discount.percent / 100
            final_amount = Decimal(str(course_price)) - discount_amount
        else:
            discount_amount = Decimal('0')
            final_amount = Decimal(str(course_price))

        new_due_date = debt.due_date + relativedelta(months=1)

        debt.amount = final_amount
        debt.discount = active_discount
        debt.discount_amount = discount_amount
        debt.due_date = new_due_date
        debt.status = 'unpaid'
        debt.save(update_fields=['amount', 'discount', 'discount_amount', 'due_date', 'status'])

        updated += 1
        logger.info(
            'Debt rolled forward: %s %s  amount=%s  due=%s',
            gs.student.first_name, gs.student.last_name, final_amount, new_due_date,
        )

    logger.info('generate_monthly_debts: updated=%d skipped=%d', updated, skipped)
    return updated
