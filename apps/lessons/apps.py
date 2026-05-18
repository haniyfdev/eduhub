from django.apps import AppConfig


class LessonsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.lessons'

    def ready(self):
        import apps.lessons.signals  # noqa — registers create_teacher_work_log via @receiver

        from apps.attendance.models import Attendance
        from apps.lessons.signals import auto_promote_trial_student
        from django.db.models.signals import post_save

        post_save.disconnect(
            auto_promote_trial_student,
            sender=Attendance,
            dispatch_uid='auto_promote_trial_student_unique',
        )
        post_save.connect(
            auto_promote_trial_student,
            sender=Attendance,
            dispatch_uid='auto_promote_trial_student_unique',
        )
