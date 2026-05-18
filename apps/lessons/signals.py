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


def auto_promote_trial_student(sender, instance, created, **kwargs):  # noqa: ARG001
    if not created:
        return
    if instance.status != 'present':
        return

    try:
        student = instance.student
        logger.info(f'Attendance signal: {student.first_name} {student.last_name}, status={student.status}')

        with transaction.atomic():
            from apps.students.models import Student
            student = Student.objects.select_for_update().get(id=student.id)

            # CASE 1: pending → trial
            if student.status == 'pending':
                student.status = 'trial'
                student.save(update_fields=['status'])
                logger.info(f'Promoted {student.first_name} to trial')

                if student.lead_id:
                    from apps.leads.models import Lead
                    Lead.objects.filter(id=student.lead_id).update(status='trial')
                return

            # CASE 2: trial → active (on 2nd present attendance)
            if student.status == 'trial':
                from apps.attendance.models import Attendance as Att
                present_count = Att.objects.filter(
                    student=student,
                    status='present',
                ).count()

                logger.info(f'{student.first_name} present_count={present_count}')

                if present_count < 2:
                    return

                # 1. Promote to active
                student.status = 'active'
                student.save(update_fields=['status'])
                logger.info(f'Promoted {student.first_name} to active')

                # 2. Delete linked lead
                if student.lead_id:
                    from apps.leads.models import Lead
                    deleted = Lead.objects.filter(id=student.lead_id).delete()
                    Student.objects.filter(id=student.id).update(lead=None)
                    logger.info(f'Deleted lead for {student.first_name}: {deleted}')

                # 3. Create debt
                from apps.groups.models import GroupStudent
                gs = (
                    GroupStudent.objects
                    .filter(student=student, left_at__isnull=True)
                    .select_related('group__course', 'group__teacher')
                    .first()
                )
                if gs and gs.group.course and gs.group.course.price > 0:
                    from apps.debts.models import Debt
                    debt, created_debt = Debt.objects.get_or_create(
                        student=student,
                        company=student.company,
                        defaults={
                            'amount': gs.group.course.price,
                            'due_date': date.today() + timedelta(days=15),
                            'status': 'unpaid',
                        },
                    )
                    logger.info(f'Debt {"created" if created_debt else "exists"} for {student.first_name}: {debt.amount}')
                else:
                    logger.warning(f'No active group/course for {student.first_name}')
                    gs = None

                # 4. Recalculate teacher salary for current month
                if gs and gs.group.teacher:
                    try:
                        from apps.salaries.logic import calculate_teacher_salary
                        current_month = date.today().replace(day=1)
                        salary = calculate_teacher_salary(gs.group.teacher, current_month)
                        logger.info(f'Recalculated salary for {gs.group.teacher}: {salary.calculated_amount}')
                    except Exception as e:
                        logger.error(f'Teacher salary calc error: {e}', exc_info=True)

    except Exception as e:
        logger.error(f'Error in auto_promote signal: {e}', exc_info=True)
