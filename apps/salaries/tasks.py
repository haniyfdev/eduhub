from celery import shared_task


@shared_task
def calculate_all_teacher_salaries(company_id, month_str):
    from datetime import datetime
    from apps.teachers.models import Teacher
    from .logic import calculate_teacher_salary

    month = datetime.strptime(month_str, '%Y-%m-%d').date()
    teachers = Teacher.objects.filter(company_id=company_id, status='active')

    for teacher in teachers:
        calculate_teacher_salary(teacher, month)
