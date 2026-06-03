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
        logger.info(
            f'Attendance signal fired: {student.first_name}, '
            f'student status={student.status}'
        )

        with transaction.atomic():
            from apps.students.models import Student
            student = Student.objects.select_for_update().get(id=student.id)

            if student.status != 'trial':
                return

            from apps.attendance.models import Attendance
            present_count = Attendance.objects.filter(
                student=student,
                status__in=['present', 'late'],
            ).count()

            logger.info(f'{student.first_name} present_count={present_count}')

            if present_count >= 2:
                # 1. Promote to active — use update() to skip pre_save chain
                #    (student.save() triggers _update_lead which hits a DB check constraint)
                Student.objects.filter(id=student.id).update(status='active')
                logger.info(f'Promoted {student.first_name} to active')

                # 2. Delete linked lead
                if student.lead_id:
                    from apps.leads.models import Lead
                    Lead.objects.filter(id=student.lead_id).delete()
                    Student.objects.filter(id=student.id).update(lead=None)
                    logger.info(f'Lead deleted for {student.first_name}')

                # 3. Create debt
                from apps.groups.models import GroupStudent
                from apps.debts.models import Debt

                gs = GroupStudent.objects.filter(
                    student=student,
                    left_at__isnull=True,
                ).select_related('group__course').first()

                if gs and gs.group.course and gs.group.course.price > 0:
                    debt, debt_created = Debt.objects.get_or_create(
                        group_student=gs,
                        company=student.company,
                        defaults={
                            'amount': gs.group.course.price,
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
