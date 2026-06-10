from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Payment


@receiver(post_save, sender=Payment)
def notify_student_on_payment(sender, instance, created, **kwargs):
    """Send a Telegram payment_confirmed notification to the student, if linked."""
    if not created:
        return

    student = instance.group_student.student
    if not student.telegram_chat_id:
        return

    from apps.notifications.telegram_views import _send_to_student

    lang = cache.get(f"bot_lang:{student.telegram_chat_id}", 'uz')
    _send_to_student(student, 'payment_confirmed', lang, {
        'amount': f"{int(instance.amount):,}".replace(',', ' '),
    }, instance.company)
