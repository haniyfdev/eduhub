from django.apps import AppConfig


class LessonsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.lessons'

    def ready(self):
        import apps.lessons.signals  # noqa: F401
        from django.db.models.signals import post_save
        from apps.attendance.models import Attendance
        from apps.lessons.signals import auto_promote_trial_student
        post_save.connect(auto_promote_trial_student, sender=Attendance,
                          dispatch_uid='lessons.auto_promote_trial_student')

