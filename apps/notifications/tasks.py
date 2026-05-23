import re

from celery import shared_task
from django.utils import timezone


def resolve_template(body: str, **kwargs) -> str:
    def replacer(match):
        key = match.group(1)
        return str(kwargs.get(key, f'{{{key}}}'))
    return re.sub(r'\{(\w+)\}', replacer, body)


@shared_task
def send_overdue_sms():
    from apps.debts.models import Debt
    from .models import SmsTemplate
    from .models import Notification

    overdue_debts = Debt.objects.filter(status='overdue').select_related('student__company', 'company')

    for debt in overdue_debts:
        template = SmsTemplate.objects.filter(
            company=debt.company,
            type='debt',
        ).first()

        if not template:
            continue

        student = debt.student
        gs = student.group_memberships.filter(
            left_at__isnull=True
        ).select_related('group__course', 'group__teacher__user').first()

        message = resolve_template(
            template.body,
            student_name=f"{student.first_name} {student.last_name}",
            amount=f"{int(debt.amount):,}".replace(',', ' '),
            due_date=debt.due_date.strftime('%d.%m.%Y') if debt.due_date else '',
            company_name=debt.company.name if debt.company else '',
            course_name=gs.group.course.name if gs and gs.group and gs.group.course else '',
            group_name=gs.group.display_name if gs and gs.group else '',
            teacher_name=(
                f"{gs.group.teacher.user.first_name} {gs.group.teacher.user.last_name}"
                if gs and gs.group and gs.group.teacher else ''
            ),
            phone=student.phone or '',
            balance=f"{int(debt.amount):,}".replace(',', ' '),
        )

        phone = student.second_phone or student.phone
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

    gs = student.group_memberships.filter(
        left_at__isnull=True
    ).select_related('group__course', 'group__teacher__user').first()

    message = resolve_template(
        template.body,
        student_name=f"{student.first_name} {student.last_name}",
        amount=f"{int(amount):,}".replace(',', ' '),
        due_date='',
        company_name=student.company.name if student.company else '',
        course_name=gs.group.course.name if gs and gs.group and gs.group.course else '',
        group_name=gs.group.display_name if gs and gs.group else '',
        teacher_name=(
            f"{gs.group.teacher.user.first_name} {gs.group.teacher.user.last_name}"
            if gs and gs.group and gs.group.teacher else ''
        ),
        phone=student.phone or '',
        balance='',
    )

    phone = student.phone or student.second_phone
    if phone:
        send_sms_task.delay(
            company_id=str(student.company.id),
            phone=phone,
            message=message,
        )
