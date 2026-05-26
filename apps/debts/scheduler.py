from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore
import logging

logger = logging.getLogger(__name__)


def generate_monthly_debts():
    from datetime import date
    from decimal import Decimal
    from dateutil.relativedelta import relativedelta
    from apps.students.models import Student
    from apps.groups.models import GroupStudent
    from apps.debts.models import Debt

    today = date.today()
    updated = 0
    skipped = 0

    active_students = Student.objects.filter(
        status='active'
    ).select_related('company', 'course')

    for student in active_students:
        # Debt is OneToOneField — each student has exactly one debt record
        try:
            debt = Debt.objects.get(student=student)
        except Debt.DoesNotExist:
            skipped += 1
            continue

        # Only roll forward when the due_date has passed
        if debt.due_date > today:
            skipped += 1
            continue

        # Get current active group to determine course price
        gs = GroupStudent.objects.filter(
            student=student,
            left_at__isnull=True,
        ).select_related('group__course').first()

        if not gs or not gs.group.course:
            skipped += 1
            continue

        course_price = gs.group.course.price

        # Check for an active discount this month
        current_month = today.replace(day=1)
        active_discount = None
        try:
            from apps.discounts.models import Discount
            active_discount = Discount.objects.filter(
                student=student,
                course=gs.group.course,
                start_month__lte=current_month,
                end_month__gte=current_month,
            ).first()
        except Exception:
            pass

        if active_discount:
            discount_amount = Decimal(str(course_price)) * active_discount.percent / 100
            final_amount = Decimal(str(course_price)) - discount_amount
        else:
            discount_amount = Decimal('0')
            final_amount = Decimal(str(course_price))

        # Advance due_date by 1 month and reset the single debt record
        new_due_date = debt.due_date + relativedelta(months=1)

        debt.amount = final_amount
        debt.discount = active_discount
        debt.discount_amount = discount_amount
        debt.due_date = new_due_date
        debt.status = 'unpaid'
        debt.save(update_fields=['amount', 'discount', 'discount_amount', 'due_date', 'status'])

        updated += 1
        logger.info(
            'Debt rolled forward: %s %s  amount=%s  due=%s',
            student.first_name, student.last_name, final_amount, new_due_date,
        )

    logger.info('generate_monthly_debts: updated=%d skipped=%d', updated, skipped)
    return updated


def start():
    scheduler = BackgroundScheduler(timezone='Asia/Tashkent')
    scheduler.add_jobstore(DjangoJobStore(), 'default')

    scheduler.add_job(
        generate_monthly_debts,
        trigger=CronTrigger(hour=1, minute=0),
        id='generate_monthly_debts',
        name='Roll forward monthly debts for active students',
        replace_existing=True,
        jobstore='default',
    )

    logger.info('Scheduler started — monthly debt rollover at 01:00 daily')
    scheduler.start()
