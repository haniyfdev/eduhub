from django.db import migrations


def backfill_debts(apps, schema_editor):
    from dateutil.relativedelta import relativedelta

    Company = apps.get_model('companies', 'Company')
    SubscriptionPlan = apps.get_model('superadmin_panel', 'SubscriptionPlan')
    CompanySubscriptionDebt = apps.get_model('superadmin_panel', 'CompanySubscriptionDebt')

    plan = SubscriptionPlan.objects.first()
    price = plan.price if plan else 0

    companies_without_debt = Company.objects.filter(
        subscription_debts__isnull=True
    ).order_by('created_at')

    count = 0
    for company in companies_without_debt:
        period_start = company.created_at.date()
        period_end = period_start + relativedelta(months=1)
        CompanySubscriptionDebt.objects.create(
            company=company,
            amount=price,
            period_start=period_start,
            period_end=period_end,
            status='pending',
        )
        count += 1
        print(f'  Created debt for {company.name}')

    print(f'  backfill_subscription_debts: created {count} debts')


class Migration(migrations.Migration):

    dependencies = [
        ('superadmin_panel', '0005_add_payment_method'),
        ('companies', '0006_backfill_company_status'),
    ]

    operations = [
        migrations.RunPython(backfill_debts, migrations.RunPython.noop),
    ]
