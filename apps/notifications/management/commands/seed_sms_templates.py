from django.core.management.base import BaseCommand

from apps.companies.models import Company
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
    help = 'Seed default SMS templates for all companies'

    def handle(self, *args, **kwargs):
        companies = Company.objects.all()
        count = 0
        for company in companies:
            for t in DEFAULT_TEMPLATES:
                obj, created = SmsTemplate.objects.get_or_create(
                    company=company,
                    name=t['name'],
                    is_default=True,
                    defaults={
                        'trigger': t['trigger'],
                        'body': t['body'],
                        'is_active': True,
                        'is_default': True,
                    }
                )
                if created:
                    count += 1
        self.stdout.write(self.style.SUCCESS(f'{count} ta shablon yaratildi'))
