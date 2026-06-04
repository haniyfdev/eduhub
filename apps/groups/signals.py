from datetime import date, timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.debts.models import Debt
from .models import GroupStudent


@receiver(post_save, sender=GroupStudent)
def create_debt_on_enrollment(sender, instance, created, **kwargs):
    """Create a Debt record when a student is added to a group (if none exists yet)."""
    if not created:
        return
    # Ignore records created with left_at already set (edge-case defensive check)
    if instance.left_at is not None:
        return

    # Do NOT create debt for trial students.
    # Debt is created by auto_promote_trial_student when gs.status → 'active'.
    if instance.status != 'active':
        return

    group = instance.group

    Debt.objects.get_or_create(
        group_student=instance,
        defaults={
            'company': group.company,
            'amount': group.course.price,
            'due_date': date.today() + timedelta(days=15),
            'status': 'unpaid',
        },
    )
