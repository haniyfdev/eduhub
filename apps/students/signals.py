from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Student


@receiver(pre_save, sender=Student)
def on_student_status_change(sender, instance, **kwargs):
    if not instance.pk:
        return  # yangi student, skip

    try:
        old = Student.objects.get(pk=instance.pk)
    except Student.DoesNotExist:
        return

    # trial → active bo'ldi
    if old.status == 'trial' and instance.status == 'active':
        _create_debt(instance)
        _update_lead(instance)


def _create_debt(student):
    from datetime import timedelta
    from django.utils import timezone
    from apps.debts.models import Debt
    from apps.groups.models import GroupStudent

    membership = GroupStudent.objects.filter(
        student=student, left_at__isnull=True
    ).select_related('group__course').first()

    if not membership:
        return

    course_price = membership.group.course.price
    if not course_price:
        return

    due_date = timezone.now().date() + timedelta(days=15)

    Debt.objects.get_or_create(
        student=student,
        company=student.company,
        defaults={
            'amount': course_price,
            'due_date': due_date,
            'status': 'unpaid',
        },
    )


def _update_lead(student):
    try:
        lead = student.lead
        if lead and lead.status != 'active':
            lead.status = 'active'
            lead.save(update_fields=['status'])
    except Exception:
        pass