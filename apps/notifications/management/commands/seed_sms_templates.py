from django.core.management.base import BaseCommand

from apps.notifications.models import SmsTemplate

DEFAULT_TEMPLATES = [
    {
        'name': 'Qarzdorlik eslatmasi',
        'trigger': 'debt_reminder',
        'body': "Hurmatli {student_name}, {company_name} o'quv markazida {course_name} kursidan {amount} so'm qarzdorligingiz bor. To'lov muddati: {due_date}.",
    },
    {
        'name': "To'lov tasdiqi",
        'trigger': 'payment_confirmed',
        'body': "Hurmatli {student_name}, {amount} so'm to'lovingiz qabul qilindi. Keyingi to'lov: {due_date}.",
    },
    {
        'name': 'Dars eslatmasi',
        'trigger': 'lesson_reminder',
        'body': "Hurmatli {student_name}, bugun {group_name} guruhida {teacher_name} bilan dars bor.",
    },
    {
        'name': 'Kurs boshlanishi',
        'trigger': 'course_started',
        'body': "Hurmatli {student_name}, {course_name} kursi boshlandi. Guruhingiz: {group_name}.",
    },
    {
        'name': "Muddati o'tgan qarz",
        'trigger': 'overdue_debt',
        'body': "Hurmatli {student_name}, {amount} so'm to'lov muddati {due_date} da o'tib ketdi. Iltimos, imkon qadar tezroq to'lang.",
    },
]


class Command(BaseCommand):
    help = 'Seed global default SMS templates (company=None) and clean up old per-company defaults'

    def handle(self, *args, **kwargs):
        # Remove old per-company default templates
        deleted, _ = SmsTemplate.objects.filter(
            is_default=True,
            company__isnull=False,
        ).delete()
        if deleted:
            self.stdout.write(f'{deleted} ta eski shablon o\'chirildi')

        # Create global templates (company=None)
        count = 0
        for t in DEFAULT_TEMPLATES:
            obj, created = SmsTemplate.objects.get_or_create(
                company=None,
                name=t['name'],
                is_default=True,
                defaults={
                    'trigger': t['trigger'],
                    'body': t['body'],
                    'is_active': True,
                    'is_default': True,
                },
            )
            if created:
                count += 1

        self.stdout.write(self.style.SUCCESS(f'{count} ta global shablon yaratildi'))
