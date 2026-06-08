from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='companies.Company')
def create_initial_subscription_debt(sender, instance, created, **kwargs):
    if not created:
        return

    from dateutil.relativedelta import relativedelta
    from .models import SubscriptionPlan, CompanySubscriptionDebt

    plan = SubscriptionPlan.objects.first()
    if not plan:
        return

    period_start = instance.created_at.date()
    period_end = period_start + relativedelta(months=1)

    CompanySubscriptionDebt.objects.create(
        company=instance,
        amount=plan.price,
        period_start=period_start,
        period_end=period_end,
        status='pending',
    )
