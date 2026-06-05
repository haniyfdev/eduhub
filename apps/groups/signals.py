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

    # due_date = first lesson date + 1 month, fallback to 15 days
    from apps.lessons.models import Lesson
    from dateutil.relativedelta import relativedelta
    first_lesson = Lesson.objects.filter(group=group).order_by('date').first()
    if first_lesson:
        due_date = first_lesson.date + relativedelta(months=1)
    else:
        due_date = date.today() + timedelta(days=15)

    Debt.objects.get_or_create(
        group_student=instance,
        defaults={
            'company': group.company,
            'amount': group.course.price,
            'due_date': due_date,
            'status': 'unpaid',
        },
    )
