from datetime import timedelta

from django.db import migrations, models


def backfill_billing_month(apps, schema_editor):
    """Set billing_month on existing debts.

    Regular debts (billing_type=None) have been rolled by the scheduler.
    Their current due_date is ~30 days ahead of when they were billed, so
    billing_month = (due_date - 30 days).replace(day=1).

    Proration debts (billing_type set) were created fresh, not rolled, so
    billing_month = due_date.replace(day=1).
    """
    Debt = apps.get_model('debts', 'Debt')
    for debt in Debt.objects.filter(billing_month__isnull=True):
        if debt.billing_type is not None:
            bm = debt.due_date.replace(day=1)
        else:
            bm = (debt.due_date - timedelta(days=30)).replace(day=1)
        debt.billing_month = bm
        debt.save(update_fields=['billing_month'])


class Migration(migrations.Migration):

    dependencies = [
        ('debts', '0006_add_billing_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='debt',
            name='billing_month',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_billing_month, migrations.RunPython.noop),
    ]
