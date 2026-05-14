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


@receiver(post_save, sender='attendance.Attendance')
def auto_promote_student(sender, instance, created, **kwargs):
    """pending → trial on first present; trial → active on 2nd+ present."""
    if not created or instance.status != 'present':
        return

    from apps.attendance.models import Attendance

    student = instance.student
    if student.status == 'pending':
        student.status = 'trial'
        student.save(update_fields=['status'])
    elif student.status == 'trial':
        present_count = Attendance.objects.filter(
            student=student,
            status='present',
        ).count()
        if present_count >= 2:
            student.status = 'active'
            student.save(update_fields=['status'])
