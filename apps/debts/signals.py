from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Debt


@receiver(post_save, sender=Debt)
def notify_student_on_debt(sender, instance, created, **kwargs):
    """Send a Telegram payment_reminder notification to the student, if linked."""
    if not created:
        return

    student = instance.group_student.student
    if not student.telegram_chat_id:
        return

    from apps.notifications.telegram_views import _send_to_student

    lang = cache.get(f"bot_lang:{student.telegram_chat_id}", 'uz')
    _send_to_student(student, 'payment_reminder', lang, {
        'amount': f"{int(instance.amount):,}".replace(',', ' '),
        'due_date': instance.due_date.strftime('%d.%m.%Y') if instance.due_date else '',
    }, instance.company)
