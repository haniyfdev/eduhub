from django.core.management.base import BaseCommand

from apps.scheduler.jobs import (
    assign_monthly_student_debts,
    mark_overdue_student_debts,
    renew_subscription_debts,
    mark_overdue_subscription_debts,
)

TASKS = {
    'assign_monthly_student_debts': assign_monthly_student_debts,
    'mark_overdue_student_debts': mark_overdue_student_debts,
    'renew_subscription_debts': renew_subscription_debts,
    'mark_overdue_subscription_debts': mark_overdue_subscription_debts,
}


class Command(BaseCommand):
    help = 'Manually run one or all of the daily APScheduler tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--task',
            type=str,
            required=True,
            choices=list(TASKS.keys()) + ['all'],
            help='Task to run, or "all" to run every task',
        )

    def handle(self, *args, **options):
        task_name = options['task']
        names = list(TASKS.keys()) if task_name == 'all' else [task_name]

        for name in names:
            self.stdout.write(f"Running {name}...")
            TASKS[name]()
            self.stdout.write(self.style.SUCCESS(f"{name} done"))
