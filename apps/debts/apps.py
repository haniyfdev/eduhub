from django.apps import AppConfig


class DebtsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.debts'

    def ready(self):
        import os
        # Only start in the main process — avoid double-start with runserver's reloader.
        # Also skip when running management commands (migrate, shell, etc.) that aren't
        # the live server, so the scheduler doesn't fire before apscheduler tables exist.
        if os.environ.get('RUN_MAIN') != 'true':
            return
        try:
            from apps.debts.scheduler import start
            start()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning('APScheduler not started: %s', exc)
