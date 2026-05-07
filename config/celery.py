import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

app = Celery('eduhub')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'check-overdue-debts': {
        'task': 'apps.debts.tasks.check_overdue_debts',
        'schedule': crontab(hour=9, minute=0),
    },
    'send-overdue-sms': {
        'task': 'apps.notifications.tasks.send_overdue_sms',
        'schedule': crontab(hour=10, minute=0),
    },
    'check-subscription-billing': {
        'task': 'apps.subscriptions.tasks.check_subscription_billing',
        'schedule': crontab(hour=8, minute=0),
    },
    'check-subscription-expiry': {
        'task': 'apps.subscriptions.tasks.check_subscription_expiry',
        'schedule': crontab(hour=0, minute=0),
    },
}
