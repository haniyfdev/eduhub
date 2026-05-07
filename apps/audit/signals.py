from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.forms.models import model_to_dict

AUDITED_MODELS_NAMES = {
    'Student', 'Payment', 'Teacher', 'Group', 'Course',
    'Discount', 'TeacherSalary', 'StaffSalary',
}

_current_user_store = {}


def get_current_user():
    import threading
    return _current_user_store.get(threading.current_thread().ident)


def set_current_user(user):
    import threading
    _current_user_store[threading.current_thread().ident] = user


@receiver(pre_save)
def capture_old_data(sender, instance, **kwargs):
    if sender.__name__ not in AUDITED_MODELS_NAMES:
        return
    try:
        instance._pre_save_old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._pre_save_old = None


@receiver(post_save)
def write_audit_log(sender, instance, created, **kwargs):
    if sender.__name__ not in AUDITED_MODELS_NAMES:
        return

    current_user = get_current_user()
    if not current_user:
        return

    from .models import AuditLog

    old = getattr(instance, '_pre_save_old', None)

    try:
        old_data = model_to_dict(old) if old else None
    except Exception:
        old_data = None

    try:
        new_data = model_to_dict(instance)
    except Exception:
        new_data = None

    AuditLog.objects.create(
        company=getattr(instance, 'company', None),
        user=current_user,
        action='created' if created else 'updated',
        model_name=sender.__name__,
        object_id=instance.pk,
        old_data=old_data,
        new_data=new_data,
        description='',
    )
