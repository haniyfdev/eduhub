# EduHub — Celery Tasks

## Setup

```python
# config/celery.py
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery('eduhub')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {

    # Daily at 09:00 — mark overdue debts
    'check-overdue-debts': {
        'task': 'apps.debts.tasks.check_overdue_debts',
        'schedule': crontab(hour=9, minute=0),
    },

    # Daily at 10:00 — send SMS to overdue debtors
    'send-overdue-sms': {
        'task': 'apps.notifications.tasks.send_overdue_sms',
        'schedule': crontab(hour=10, minute=0),
    },

    # Daily at 08:00 — check if any company's billing date is today
    'check-subscription-billing': {
        'task': 'apps.subscriptions.tasks.check_subscription_billing',
        'schedule': crontab(hour=8, minute=0),
    },

    # Daily at 00:00 — expire subscriptions past their expires_at
    'check-subscription-expiry': {
        'task': 'apps.subscriptions.tasks.check_subscription_expiry',
        'schedule': crontab(hour=0, minute=0),
    },
}
```

---

## Task Definitions

### `apps/debts/tasks.py`

```python
from celery import shared_task
from django.utils import timezone
from .models import Debt

@shared_task
def check_overdue_debts():
    """
    Runs daily at 09:00.
    Marks debts as overdue when due_date has passed.
    """
    today = timezone.now().date()
    updated = Debt.objects.filter(
        due_date__lt=today,
        status__in=['unpaid', 'partial']
    ).update(status='overdue')
    return f"Marked {updated} debts as overdue"

@shared_task
def assign_monthly_debts(company_id):
    """
    Triggered per-company on their billing date.
    Adds monthly course fee to each active student's debt.
    See BUSINESS_LOGIC.md section 3 for full logic.
    """
    from apps.companies.models import Company
    from apps.groups.models import GroupStudent
    from apps.discounts.models import Discount
    from django.db.models import Q
    from datetime import timedelta
    import decimal

    company = Company.objects.get(id=company_id)
    billing_date = timezone.now().date()

    active_enrollments = GroupStudent.objects.filter(
        group__company=company,
        group__status='active',
        left_at__isnull=True
    ).select_related('student', 'group__course')

    for enrollment in active_enrollments:
        course_price = enrollment.group.course.price

        discount = Discount.objects.filter(
            company=company,
            status='active'
        ).filter(
            Q(course=enrollment.group.course) | Q(course__isnull=True)
        ).order_by('-course').first()

        if discount:
            if discount.type == 'percent':
                final_price = course_price * (1 - discount.value / 100)
            else:
                final_price = course_price - discount.value
        else:
            final_price = course_price

        debt, _ = Debt.objects.get_or_create(
            student=enrollment.student,
            company=company,
            defaults={'amount': decimal.Decimal('0'), 'status': 'unpaid'}
        )
        debt.amount += final_price
        debt.due_date = billing_date + timedelta(days=15)
        debt.status = 'unpaid'
        debt.save()
```

---

### `apps/notifications/tasks.py`

```python
from celery import shared_task
from .models import Notification
from utils.sms import send_sms

@shared_task
def send_overdue_sms():
    """
    Runs daily at 10:00.
    Sends debt reminder SMS to all overdue debtors.
    """
    from apps.debts.models import Debt
    from apps.notifications.models import SmsTemplate

    overdue_debts = Debt.objects.filter(
        status='overdue'
    ).select_related('student', 'company')

    for debt in overdue_debts:
        template = SmsTemplate.objects.filter(
            company=debt.company,
            type='debt',
            status='active'
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
    """
    Core SMS sending task. Logs result to notifications table.
    Never call Eskiz API directly from a view — always use this task.
    """
    from utils.sms import send_sms

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
    """
    Triggered immediately after a payment is recorded.
    """
    from apps.students.models import Student
    from apps.notifications.models import SmsTemplate

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
```

---

### `apps/subscriptions/tasks.py`

```python
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Subscription

@shared_task
def check_subscription_billing():
    """
    Runs daily at 08:00.
    Triggers monthly debt assignment for companies whose billing date is today.
    Billing date = started_at + (30 * N) days — NOT the 1st of the month.
    Each company has its own independent billing cycle.
    """
    from apps.debts.tasks import assign_monthly_debts

    today = timezone.now().date()

    for subscription in Subscription.objects.filter(status='active'):
        delta = {'monthly': 30, 'quarterly': 90, 'yearly': 365}[subscription.interval]
        days_since_start = (today - subscription.started_at).days

        if days_since_start > 0 and days_since_start % delta == 0:
            assign_monthly_debts.delay(str(subscription.company_id))
            calculate_subscription_fee.delay(str(subscription.id))

@shared_task
def calculate_subscription_fee(subscription_id):
    """
    Calculates and records how much to bill the education center.
    """
    from apps.students.models import Student

    subscription = Subscription.objects.get(id=subscription_id)

    if subscription.billing_type == 'per_student':
        count = Student.objects.filter(
            company=subscription.company,
            status='active'
        ).count()
        subscription.students_count = count
        subscription.amount_billed = count * subscription.price_per_unit

    elif subscription.billing_type == 'flat':
        subscription.amount_billed = subscription.price_per_unit

    subscription.save()

@shared_task
def check_subscription_expiry():
    """
    Runs daily at 00:00.
    Marks subscriptions as expired when expires_at has passed.
    """
    today = timezone.now().date()
    Subscription.objects.filter(
        expires_at__lt=today,
        status='active'
    ).update(status='expired')
```

---

### `apps/salaries/tasks.py`

```python
from celery import shared_task

@shared_task
def calculate_all_teacher_salaries(company_id, month_str):
    """
    Triggered on company billing date.
    Calculates salary for every active teacher in the company.
    See BUSINESS_LOGIC.md section 5 for full salary type logic.
    """
    from datetime import datetime
    from apps.teachers.models import Teacher
    from .logic import calculate_teacher_salary

    month = datetime.strptime(month_str, '%Y-%m-%d').date()

    teachers = Teacher.objects.filter(
        company_id=company_id,
        status='active'
    )

    for teacher in teachers:
        calculate_teacher_salary(teacher, month)
```

---

## Eskiz.uz SMS Wrapper

```python
# utils/sms.py
import requests
from django.conf import settings

_token = None

def get_eskiz_token():
    global _token
    response = requests.post('https://notify.eskiz.uz/api/auth/login', data={
        'email': settings.ESKIZ_EMAIL,
        'password': settings.ESKIZ_PASSWORD,
    })
    _token = response.json()['data']['token']
    return _token

def send_sms(phone: str, message: str) -> bool:
    """
    Sends SMS via Eskiz.uz.
    Returns True if successful, False otherwise.
    Never raises exceptions — always returns bool.
    """
    try:
        token = get_eskiz_token()
        response = requests.post(
            'https://notify.eskiz.uz/api/message/sms/send',
            headers={'Authorization': f'Bearer {token}'},
            data={
                'mobile_phone': phone.replace('+', ''),
                'message': message,
                'from': '4546',
            },
            timeout=10,
        )
        return response.status_code == 200
    except Exception:
        return False
```

---

## Running Celery Locally

```bash
# Terminal 1 — worker
celery -A config worker --loglevel=info

# Terminal 2 — beat scheduler
celery -A config beat --loglevel=info

# Terminal 3 — Django dev server
python manage.py runserver
```

## Running on Render

Add two background worker services on Render:
- **Worker**: `celery -A config worker --loglevel=info`
- **Beat**: `celery -A config beat --loglevel=info`
