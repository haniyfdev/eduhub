from celery import shared_task
from django.utils import timezone


@shared_task
def check_overdue_debts():
    from .models import Debt
    today = timezone.now().date()
    updated = Debt.objects.filter(
        due_date__lt=today,
        status__in=['unpaid', 'partial'],
    ).update(status='overdue')
    return f"Marked {updated} debts as overdue"


@shared_task
def assign_monthly_debts(company_id):
    from datetime import timedelta
    from decimal import Decimal, ROUND_HALF_UP
    from apps.companies.models import Company
    from apps.groups.models import GroupStudent
    from .models import Debt

    company = Company.objects.get(id=company_id)
    billing_date = timezone.now().date()

    active_enrollments = GroupStudent.objects.filter(
        group__company=company,
        group__status='active',
        left_at__isnull=True,
    ).select_related('student', 'group__course')

    for gs in active_enrollments:
        if gs.student.status == 'frozen':
            continue

        if not gs.group.course or not gs.group.course.price:
            continue

        course_price = gs.group.course.price
        from apps.discounts.models import Discount
        current_month = billing_date.replace(day=1)
        active_discount = Discount.objects.filter(
            student=gs.student,
            course=gs.group.course,
            start_month__lte=current_month,
            end_month__gte=current_month,
        ).first()

        if active_discount:
            discount_amt = Decimal(str(course_price)) * active_discount.percent / 100
            final_price = Decimal(str(course_price)) - discount_amt
        else:
            final_price = Decimal(str(course_price))

        final_price = final_price.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        if final_price <= 0:
            continue

        Debt.objects.get_or_create(
            group_student=gs,
            company=company,
            defaults={
                'amount': final_price,
                'status': 'unpaid',
                'due_date': billing_date + timedelta(days=15),
            },
        )
