import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

logger = logging.getLogger(__name__)


def assign_monthly_student_debts():
    """For every active enrollment, roll the debt forward to the next 30-day
    cycle once its due date has passed (or create the first debt if missing)."""
    from apps.companies.models import Company
    from apps.discounts.models import Discount
    from apps.debts.models import Debt
    from apps.groups.models import GroupStudent

    logger.info("assign_monthly_student_debts: started")
    logger.error("JOB START: assign_monthly_student_debts")
    today = date.today()
    created = 0
    updated = 0
    skipped = 0

    try:
        enrollments = GroupStudent.objects.filter(
            status='active',
            group__status='active',
            group__company__status='active',
        ).exclude(
            student__status='frozen',
        ).select_related('student', 'group__course', 'group__company')

        for gs in enrollments:
            course = gs.group.course
            if not course or not course.price:
                skipped += 1
                continue

            try:
                with transaction.atomic():
                    course_price = Decimal(str(course.price))
                    current_month = today.replace(day=1)
                    discount = Discount.objects.filter(
                        student=gs.student,
                        course=course,
                        start_month__lte=current_month,
                        end_month__gte=current_month,
                    ).first()

                    if discount:
                        discount_amount = (course_price * discount.percent / Decimal('100')).quantize(
                            Decimal('1'), rounding=ROUND_HALF_UP
                        )
                        final_amount = course_price - discount_amount
                    else:
                        discount_amount = Decimal('0')
                        final_amount = course_price

                    debt = Debt.objects.select_for_update().filter(group_student=gs).first()

                    if debt is None:
                        Debt.objects.create(
                            company=gs.group.company,
                            group_student=gs,
                            amount=final_amount,
                            due_date=gs.joined_at.date() + timedelta(days=30),
                            status='unpaid',
                            discount=discount,
                            discount_amount=discount_amount,
                        )
                        created += 1
                        continue

                    # Never create a duplicate: skip if this debt already
                    # covers a future due date.
                    if debt.due_date > today:
                        skipped += 1
                        continue

                    debt.amount = final_amount
                    debt.due_date = debt.due_date + timedelta(days=30)
                    debt.status = 'unpaid'
                    debt.discount = discount
                    debt.discount_amount = discount_amount
                    debt.save(update_fields=['amount', 'due_date', 'status', 'discount', 'discount_amount'])
                    updated += 1
            except Exception:
                logger.exception("assign_monthly_student_debts: failed for group_student %s", gs.id)

        logger.info(
            "assign_monthly_student_debts: completed created=%d updated=%d skipped=%d",
            created, updated, skipped,
        )
        logger.error("JOB DONE: assign_monthly_student_debts")
    except Exception:
        logger.exception("assign_monthly_student_debts: failed")


def mark_overdue_student_debts():
    """Mark unpaid debts whose due date has passed as overdue."""
    from apps.debts.models import Debt

    logger.info("mark_overdue_student_debts: started")
    logger.error("JOB START: mark_overdue_student_debts")
    try:
        today = date.today()
        updated = Debt.objects.filter(status='unpaid', due_date__lt=today).update(status='overdue')
        logger.info("mark_overdue_student_debts: completed updated=%d", updated)
        logger.error("JOB DONE: mark_overdue_student_debts")
    except Exception:
        logger.exception("mark_overdue_student_debts: failed")


def renew_subscription_debts():
    """Create the next subscription billing period once the current one is paid."""
    from apps.superadmin_panel.models import CompanySubscriptionDebt, SubscriptionPlan

    logger.info("renew_subscription_debts: started")
    logger.error("JOB START: renew_subscription_debts")
    created = 0

    try:
        today = date.today()
        plan = SubscriptionPlan.objects.first()
        if plan is None:
            logger.warning("renew_subscription_debts: no SubscriptionPlan configured, skipping")
            logger.error("JOB DONE: renew_subscription_debts")
            return

        paid_debts = CompanySubscriptionDebt.objects.filter(status='paid', period_end__lte=today)

        for debt in paid_debts:
            next_period_start = debt.period_end

            already_exists = CompanySubscriptionDebt.objects.filter(
                company=debt.company,
                period_start=next_period_start,
            ).exists()
            if already_exists:
                continue

            try:
                with transaction.atomic():
                    CompanySubscriptionDebt.objects.create(
                        company=debt.company,
                        amount=plan.price,
                        period_start=next_period_start,
                        period_end=next_period_start + timedelta(days=30),
                        status='pending',
                    )
                    created += 1
            except Exception:
                logger.exception("renew_subscription_debts: failed for company %s", debt.company_id)

        logger.info("renew_subscription_debts: completed created=%d", created)
        logger.error("JOB DONE: renew_subscription_debts")
    except Exception:
        logger.exception("renew_subscription_debts: failed")


def mark_overdue_subscription_debts():
    """Mark pending/partial subscription debts whose period has ended as overdue."""
    from apps.superadmin_panel.models import CompanySubscriptionDebt

    logger.info("mark_overdue_subscription_debts: started")
    logger.error("JOB START: mark_overdue_subscription_debts")
    try:
        today = date.today()
        updated = CompanySubscriptionDebt.objects.filter(
            status__in=['pending', 'partial'],
            period_end__lt=today,
        ).update(status='overdue')
        logger.info("mark_overdue_subscription_debts: completed updated=%d", updated)
        logger.error("JOB DONE: mark_overdue_subscription_debts")
    except Exception:
        logger.exception("mark_overdue_subscription_debts: failed")


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from django_apscheduler.jobstores import DjangoJobStore

    scheduler = BackgroundScheduler(timezone='Asia/Tashkent')

    try:
        scheduler.add_jobstore(DjangoJobStore(), 'default')
    except Exception:
        logger.exception(
            "APScheduler: failed to initialize DjangoJobStore, "
            "falling back to in-memory jobstore"
        )

    scheduler.add_job(
        assign_monthly_student_debts,
        trigger=CronTrigger(hour=1, minute=0),
        id='assign_monthly_student_debts',
        replace_existing=True,
        jobstore='default',
    )
    scheduler.add_job(
        mark_overdue_student_debts,
        trigger=CronTrigger(hour=1, minute=0),
        id='mark_overdue_student_debts',
        replace_existing=True,
        jobstore='default',
    )
    scheduler.add_job(
        renew_subscription_debts,
        trigger=CronTrigger(hour=1, minute=0),
        id='renew_subscription_debts',
        replace_existing=True,
        jobstore='default',
    )
    scheduler.add_job(
        mark_overdue_subscription_debts,
        trigger=CronTrigger(hour=1, minute=0),
        id='mark_overdue_subscription_debts',
        replace_existing=True,
        jobstore='default',
    )

    try:
        logger.error("APScheduler: attempting to start...")
        scheduler.start()
        logger.error("APScheduler: started successfully.")
    except Exception as e:
        logger.error(f"APScheduler failed to start: {e}")
