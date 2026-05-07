from celery import shared_task
from django.utils import timezone


@shared_task
def send_overdue_sms():
    from apps.debts.models import Debt
    from .models import SmsTemplate
    from .models import Notification

    overdue_debts = Debt.objects.filter(status='overdue').select_related('student', 'company')

    for debt in overdue_debts:
        template = SmsTemplate.objects.filter(
            company=debt.company,
            type='debt',
        ).first()

        if not template:
            continue

        message = template.body.format(
            student_name=f"{debt.student.first_name} {debt.student.last_name}",
            amount=debt.amount,
            due_date=debt.due_date,
        )

        phone = debt.student.second_phone or debt.student.phone
        if not phone:
            continue

        send_sms_task.delay(
            company_id=str(debt.company.id),
            phone=phone,
            message=message,
            notification_type='sms',
        )


@shared_task
def send_sms_task(company_id, phone, message, notification_type='sms'):
    from utils.sms import send_sms
    from .models import Notification

    notification = Notification.objects.create(
        company_id=company_id,
        recipient_phone=phone,
        message=message,
        type=notification_type,
        status='pending',
    )

    success = send_sms(phone, message)
    notification.status = 'sent' if success else 'failed'
    notification.sent_at = timezone.now() if success else None
    notification.save()


@shared_task
def send_payment_confirmation_sms(student_id, amount):
    from apps.students.models import Student
    from .models import SmsTemplate

    student = Student.objects.select_related('company').get(id=student_id)

    template = SmsTemplate.objects.filter(
        company=student.company,
        type='welcome',
    ).first()

    if not template:
        return

    message = template.body.format(
        student_name=f"{student.first_name} {student.last_name}",
        amount=amount,
    )

    phone = student.phone or student.second_phone
    if phone:
        send_sms_task.delay(
            company_id=str(student.company.id),
            phone=phone,
            message=message,
        )
