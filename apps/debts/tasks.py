from celery import shared_task
from django.utils import timezone


@shared_task
def check_overdue_subscription_debts():
    from apps.superadmin_panel.models import CompanySubscriptionDebt
    today = timezone.now().date()
    updated = CompanySubscriptionDebt.objects.filter(
        period_end__lt=today,
        status__in=['pending', 'partial'],
    ).update(status='overdue')
    return f"Marked {updated} subscription debts as overdue"


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
    from apps.companies.models import Company, CompanySettings
    from apps.groups.models import GroupStudent
    from .models import Debt

    company = Company.objects.get(id=company_id)
    billing_date = timezone.now().date()
    current_month = billing_date.replace(day=1)

    settings, _ = CompanySettings.objects.get_or_create(company=company)
    billing_type = settings.billing_type

    active_enrollments = GroupStudent.objects.filter(
        group__company=company,
        group__status='active',
        left_at__isnull=True,
    ).select_related('student', 'group__course')

    for gs in active_enrollments:
        if gs.status == 'trial':
            continue
        if gs.status == 'frozen':
            continue
        if gs.student.status == 'frozen':
            continue

        if not gs.group.course or not gs.group.course.price:
            continue

        course_price = Decimal(str(gs.group.course.price))

        if billing_type == 'upfront':
            if gs.joined_at.date() < current_month:
                continue
            base_price = course_price * (gs.group.course.duration_months or 1)
        elif billing_type == 'per_lesson':
            from apps.attendance.models import Attendance
            attended = Attendance.objects.filter(
                lesson__group=gs.group,
                student=gs.student,
                status='present',
                lesson__date__year=billing_date.year,
                lesson__date__month=billing_date.month,
            ).count()
            base_price = (course_price / Decimal('20')) * attended
        else:
            base_price = course_price

        from apps.discounts.models import Discount
        active_discount = Discount.objects.filter(
            student=gs.student,
            course=gs.group.course,
            start_month__lte=current_month,
            end_month__gte=current_month,
        ).first()

        if active_discount:
            discount_amt = base_price * active_discount.percent / 100
            final_price = base_price - discount_amt
        else:
            final_price = base_price

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
