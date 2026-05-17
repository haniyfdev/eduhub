from django.db.models.signals import post_save
from django.dispatch import receiver


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
    if instance.status != 'present':
        return
    student = instance.student
    if student.status != 'trial':
        return
    from apps.attendance.models import Attendance
    present_count = Attendance.objects.filter(student=student, status='present').count()
    if present_count >= 2:
        lead_id = student.lead_id    # capture raw FK before clearing
        student.status = 'active'
        student.lead = None
        student.save(update_fields=['status', 'lead'])

        # Delete linked lead — student fully converted, must not appear in leads
        if lead_id:
            try:
                from apps.leads.models import Lead
                Lead.objects.filter(id=lead_id).delete()
            except Exception:
                pass

        # Create debt now that student is active
        try:
            from apps.debts.models import Debt
            from apps.groups.models import GroupStudent
            from datetime import date, timedelta
            gs = GroupStudent.objects.filter(student=student, left_at__isnull=True).first()
            if gs:
                Debt.objects.get_or_create(
                    student=student,
                    company=student.company,
                    defaults={
                        'amount': gs.group.course.price,
                        'due_date': date.today() + timedelta(days=15),
                        'status': 'unpaid',
                    },
                )
        except Exception:
            pass


