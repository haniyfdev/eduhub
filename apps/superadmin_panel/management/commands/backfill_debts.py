from django.core.management.base import BaseCommand
from dateutil.relativedelta import relativedelta
from apps.companies.models import Company
from apps.superadmin_panel.models import SubscriptionPlan, CompanySubscriptionDebt


class Command(BaseCommand):
    help = 'Create missing subscription debts for companies that have none'

    def handle(self, *args, **kwargs):
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
            self.stdout.write(f'  Created debt for {company.name}')

        self.stdout.write(self.style.SUCCESS(f'Done. Created {count} debts.'))
