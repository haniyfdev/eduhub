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

    student = instance.student
    if student.status != 'active':
        return  # trial/pending students get no debt on enrollment

    group = instance.group

    Debt.objects.get_or_create(
        student=student,
        defaults={
            'company': group.company,
            'amount': group.course.price,
            'due_date': date.today() + timedelta(days=15),
            'status': 'unpaid',
        },
    )
