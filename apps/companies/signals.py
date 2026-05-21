from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Company

DEFAULT_TEMPLATES = [
    {
        'name': 'Qarzdorlik eslatmasi',
        'trigger': 'debt_reminder',
        'is_default': True,
        'body': "Hurmatli {student_name}, {company_name} o'quv markazida {course_name} kursidan {amount} so'm qarzdorligingiz bor. To'lov muddati: {due_date}.",
    },
    {
        'name': "To'lov tasdiqi",
        'trigger': 'payment_confirmed',
        'is_default': True,
        'body': "Hurmatli {student_name}, {amount} so'm to'lovingiz qabul qilindi. Keyingi to'lov: {due_date}.",
    },
    {
        'name': 'Dars eslatmasi',
        'trigger': 'lesson_reminder',
        'is_default': True,
        'body': "Hurmatli {student_name}, bugun {group_name} guruhida {teacher_name} bilan dars bor.",
    },
    {
        'name': 'Kurs boshlanishi',
        'trigger': 'course_started',
        'is_default': True,
        'body': "Hurmatli {student_name}, {course_name} kursi boshlandi. Guruhingiz: {group_name}.",
    },
    {
        'name': "Muddati o'tgan qarz",
        'trigger': 'overdue_debt',
        'is_default': True,
        'body': "Hurmatli {student_name}, {amount} so'm to'lov muddati {due_date} da o'tib ketdi. Iltimos tezroq to'lang.",
    },
]


@receiver(post_save, sender=Company)
def create_default_sms_templates(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.notifications.models import SmsTemplate
    for tmpl in DEFAULT_TEMPLATES:
        SmsTemplate.objects.create(company=instance, **tmpl)
