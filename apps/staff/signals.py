import datetime

from dateutil.relativedelta import relativedelta
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='staff.Staff')
def create_salary_on_hire(sender, instance, created, **kwargs):
    if not created or instance.status != 'active':
        return

    from .models import StaffSalary

    month = datetime.date.today().replace(day=1)
    due_date = (month + relativedelta(months=1)).replace(day=1)

    StaffSalary.objects.get_or_create(
        staff=instance,
        company=instance.company,
        month=month,
        defaults={
            'calculated_amount': instance.salary_amount,
            'carry_over': 0,
            'due_date': due_date,
            'status': 'unpaid',
        },
    )
