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


