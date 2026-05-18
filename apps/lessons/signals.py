from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from datetime import date, timedelta


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


def auto_promote_trial_student(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.status != 'present':
        return

    student = instance.student

    with transaction.atomic():
        # Re-fetch inside transaction to get the authoritative status
        from apps.students.models import Student
        student = Student.objects.select_for_update().get(pk=student.pk)

        # CASE 1: pending → trial (first lesson attended)
        if student.status == 'pending':
            student.status = 'trial'
            student.save(update_fields=['status'])
            if student.lead_id:
                from apps.leads.models import Lead
                Lead.objects.filter(id=student.lead_id).update(status='trial')
            return

        # CASE 2: trial → active (2nd present attendance)
        if student.status == 'trial':
            from apps.attendance.models import Attendance
            present_count = Attendance.objects.filter(
                student=student,
                status='present',
            ).count()

            if present_count < 2:
                return

            # 1. Promote student
            student.status = 'active'
            student.save(update_fields=['status'])

            # 2. Delete linked lead (on_delete=SET_NULL handles student.lead → NULL)
            if student.lead_id:
                from apps.leads.models import Lead
                Lead.objects.filter(id=student.lead_id).delete()
                Student.objects.filter(pk=student.pk).update(lead=None)

            # 3. Create debt
            from apps.groups.models import GroupStudent
            gs = (
                GroupStudent.objects
                .filter(student=student, left_at__isnull=True)
                .select_related('group__course')
                .first()
            )
            if gs and gs.group.course and gs.group.course.price:
                from apps.debts.models import Debt
                Debt.objects.get_or_create(
                    student=student,
                    company=student.company,
                    defaults={
                        'amount': gs.group.course.price,
                        'due_date': date.today() + timedelta(days=15),
                        'status': 'unpaid',
                    },
                )
