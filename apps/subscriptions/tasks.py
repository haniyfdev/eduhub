from celery import shared_task
from django.utils import timezone


@shared_task
def check_subscription_billing():
    from apps.debts.tasks import assign_monthly_debts
    from .models import Subscription

    today = timezone.now().date()

    for subscription in Subscription.objects.filter(status='active'):
        delta = {'monthly': 30, 'quarterly': 90, 'yearly': 365}[subscription.interval]
        days_since_start = (today - subscription.started_at).days

        if days_since_start > 0 and days_since_start % delta == 0:
            assign_monthly_debts.delay(str(subscription.company_id))
            calculate_subscription_fee.delay(str(subscription.id))


@shared_task
def calculate_subscription_fee(subscription_id):
    from apps.students.models import Student
    from .models import Subscription

    subscription = Subscription.objects.get(id=subscription_id)

    if subscription.billing_type == 'per_student':
        count = Student.objects.filter(company=subscription.company, status='active').count()
        subscription.students_count = count
        subscription.amount_billed = count * subscription.price_per_unit
    elif subscription.billing_type == 'flat':
        subscription.amount_billed = subscription.price_per_unit

    subscription.save()


@shared_task
def check_subscription_expiry():
    from .models import Subscription

    today = timezone.now().date()
    Subscription.objects.filter(expires_at__lt=today, status='active').update(status='expired')
