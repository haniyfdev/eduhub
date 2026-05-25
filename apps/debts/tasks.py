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
    from apps.discounts.models import Discount
    from apps.attendance.models import Attendance
    from .models import Debt

    company = Company.objects.get(id=company_id)
    billing_date = timezone.now().date()
    billing_start = billing_date - timedelta(days=30)

    try:
        billing_type = company.settings.billing_type
    except Exception:
        billing_type = 'monthly'

    active_enrollments = GroupStudent.objects.filter(
        group__company=company,
        group__status='active',
        left_at__isnull=True,
    ).select_related('student', 'group__course')

    for enrollment in active_enrollments:
        if enrollment.student.status == 'frozen':
            continue
        course_price = enrollment.group.course.price

        if billing_type == 'monthly':
            charge = course_price
        elif billing_type == 'per_lesson':
            lessons_attended = Attendance.objects.filter(
                lesson__group=enrollment.group,
                student=enrollment.student,
                status='present',
                lesson__date__gte=billing_start,
                lesson__date__lte=billing_date,
            ).count()
            lesson_price = course_price / Decimal('20')
            charge = lesson_price * lessons_attended
        elif billing_type == 'upfront':
            # Only charge students who enrolled in this billing period
            if enrollment.joined_at.date() >= billing_start:
                charge = course_price * enrollment.group.course.duration_months
            else:
                continue
        else:
            charge = course_price

        # Check for active per-student discount
        current_month = billing_date.replace(day=1)
        active_discount = Discount.objects.filter(
            student=enrollment.student,
            course=enrollment.group.course,
            start_month__lte=current_month,
            end_month__gte=current_month,
        ).first()

        if active_discount:
            discount_amt = charge * active_discount.percent / 100
            final_price = charge - discount_amt
        else:
            discount_amt = Decimal('0')
            final_price = charge

        final_price = Decimal(str(final_price)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        if final_price <= 0:
            continue

        Debt.objects.get_or_create(
            student=enrollment.student,
            company=company,
            defaults={
                'amount': final_price,
                'discount': active_discount,
                'discount_amount': discount_amt,
                'status': 'unpaid',
                'due_date': billing_date + timedelta(days=15),
            },
        )
