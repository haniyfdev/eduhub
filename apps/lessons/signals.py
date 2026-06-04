from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender='lessons.Lesson')
def create_teacher_work_log(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.salaries.models import TeacherWorkLog
    from apps.groups.models import GroupStudent
    students_count = GroupStudent.objects.filter(
        group=instance.group,
        left_at__isnull=True,
    ).count()
    TeacherWorkLog.objects.create(
        company=instance.group.company,
        teacher=instance.teacher,
        lesson=instance,
        students_count=students_count,
    )


def auto_promote_trial_student(sender, instance, **kwargs):
    if instance.status not in ('present', 'late'):
        return

    try:
        student = instance.student

        with transaction.atomic():
            from apps.students.models import Student
            from apps.groups.models import GroupStudent

            student = Student.objects.select_for_update().get(id=student.id)
            lesson  = instance.lesson

            gs = GroupStudent.objects.select_for_update().filter(
                student=student,
                group=lesson.group,
                left_at__isnull=True,
            ).select_related('group__course').first()

            if not gs:
                return

            logger.info(
                f'Attendance signal: {student.first_name}, '
                f'student.status={student.status}, gs.status={gs.status}'
            )

            # CASE 1: pending → trial on first attendance
            if student.status == 'pending':
                Student.objects.filter(id=student.id).update(status='trial')
                gs.status = 'trial'
                gs.save(update_fields=['status'])
                if student.lead_id:
                    from apps.leads.models import Lead
                    Lead.objects.filter(id=student.lead_id).update(status='trial')
                logger.info(f'Pending→trial: {student.first_name}')
                return

            # CASE 2: trial GroupStudent → promote to active after 2 present attendances
            if gs.status != 'trial':
                return

            from apps.attendance.models import Attendance as Att
            present_count = Att.objects.filter(
                student=student,
                lesson__group=lesson.group,
                status__in=['present', 'late'],
            ).count()

            logger.info(f'{student.first_name} present_count in group {lesson.group}={present_count}')

            if present_count < 2:
                return

            # Promote this GroupStudent to active
            gs.status = 'active'
            gs.save(update_fields=['status'])
            logger.info(f'GroupStudent→active: {student.first_name} in {lesson.group}')

            # Promote the Student if not already active
            if student.status != 'active':
                Student.objects.filter(id=student.id).update(status='active')
                logger.info(f'Student→active: {student.first_name}')

                if student.lead_id:
                    from apps.leads.models import Lead
                    Lead.objects.filter(id=student.lead_id).delete()
                    Student.objects.filter(id=student.id).update(lead=None)
                    logger.info(f'Lead deleted for {student.first_name}')

            # Create debt for this GroupStudent
            if gs.group.course and gs.group.course.price > 0:
                from apps.debts.models import Debt
                from decimal import Decimal

                course_price   = gs.group.course.price
                current_month  = date.today().replace(day=1)
                active_discount = None
                try:
                    active_discount = student.discounts.filter(
                        start_month__lte=current_month,
                        end_month__gte=current_month,
                        course=gs.group.course,
                    ).first()
                except Exception:
                    pass

                if active_discount:
                    discount_amt = Decimal(str(course_price)) * active_discount.percent / 100
                    final_amount = Decimal(str(course_price)) - discount_amt
                else:
                    discount_amt = Decimal('0')
                    final_amount = Decimal(str(course_price))

                debt, debt_created = Debt.objects.get_or_create(
                    group_student=gs,
                    company=student.company,
                    defaults={
                        'amount': final_amount,
                        'discount': active_discount,
                        'discount_amount': discount_amt,
                        'due_date': date.today() + timedelta(days=15),
                        'status': 'unpaid',
                    },
                )
                logger.info(
                    f'Debt {"created" if debt_created else "exists"}: '
                    f'{debt.amount} for {student.first_name}'
                )

    except Exception as e:
        logger.error(f'Promotion signal error: {e}', exc_info=True)
