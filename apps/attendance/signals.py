from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Attendance


@receiver(post_save, sender=Attendance)
def apply_absent_policy(sender, instance, created, **kwargs):
    """Adjust student debt based on company absent_policy when an absence is recorded."""
    if not created or instance.status != 'absent':
        return

    company = instance.lesson.group.company
    try:
        policy = company.settings.absent_policy
    except Exception:
        return

    if policy == 'ignore':
        return

    from apps.debts.models import Debt

    try:
        debt = Debt.objects.get(student=instance.student, company=company)
    except Debt.DoesNotExist:
        return

    course_price = instance.lesson.group.course.price
    lesson_price = course_price / Decimal('20')

    if policy == 'deduct':
        debt.amount = max(Decimal('0'), debt.amount - lesson_price)
        if debt.amount == 0:
            debt.status = 'paid'
        debt.save()
    elif policy == 'penalty':
        penalty = lesson_price * Decimal('0.05')
        debt.amount += penalty
        if debt.status == 'paid':
            debt.status = 'unpaid'
        debt.save()
