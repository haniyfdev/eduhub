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

        if os.environ.get('DJANGO_SETTINGS_MODULE', '').endswith('production'):
            # Multiple gunicorn workers all call ready() on boot. Only the
            # worker that grabs this lock starts the scheduler; the rest
            # back off so jobs aren't scheduled multiple times.
            import fcntl

            lock_file = open('/tmp/apscheduler.lock', 'w')
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError:
                logger.error("APScheduler: another instance already running, skipping.")
                return

            # Keep the descriptor referenced for the process lifetime so the
            # lock isn't released until this worker exits.
            self._scheduler_lock = lock_file

            from .jobs import start_scheduler
            start_scheduler()
        elif os.environ.get('RUN_MAIN') == 'true':
            # Dev server with the autoreloader: only the reloaded child
            # process sets RUN_MAIN, preventing a double start there too.
            from .jobs import start_scheduler
            start_scheduler()
