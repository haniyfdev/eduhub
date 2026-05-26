from django.apps import AppConfig


class DebtsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.debts'

    def ready(self):
        from apps.debts.scheduler import start
        try:
            start()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error('Scheduler start error: %s', e)
