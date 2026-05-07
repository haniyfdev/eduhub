from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='salaries.TeacherSalary')
def mirror_teacher_salary(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.expenses.models import Expense
    Expense.objects.create(
        company=instance.company,
        category='teacher_salary',
        source='auto',
        amount=instance.total_amount,
        description=f"Teacher salary: {instance.teacher.user.get_full_name()} — {instance.month.strftime('%B %Y')}",
        expense_date=instance.month,
        reference_id=instance.id,
    )


@receiver(post_save, sender='salaries.StaffSalary')
def mirror_staff_salary(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.expenses.models import Expense
    Expense.objects.create(
        company=instance.company,
        category='staff_salary',
        source='auto',
        amount=instance.amount,
        description=f"Staff salary: {instance.user.get_full_name()} — {instance.month.strftime('%B %Y')}",
        expense_date=instance.month,
        reference_id=instance.id,
        created_by=None,
    )
