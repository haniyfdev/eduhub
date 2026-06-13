import logging
import os

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class SchedulerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.scheduler'

    def ready(self):
        logger.error("Scheduler AppConfig.ready() called")
        logger.error(f"RUN_MAIN={os.environ.get('RUN_MAIN')}")
        logger.error(f"SETTINGS={os.environ.get('DJANGO_SETTINGS_MODULE')}")

        # Prevent double-start in dev (reloader) and multi-worker envs
        if os.environ.get('RUN_MAIN') == 'true' or \
                os.environ.get('DJANGO_SETTINGS_MODULE', '').endswith('production'):
            from .jobs import start_scheduler
            start_scheduler()
