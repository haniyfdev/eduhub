import os
import sys
from unittest.mock import MagicMock, mock_open, patch

from django.apps import apps


def _scheduler_config():
    return apps.get_app_config('scheduler')


class TestApschedulerLock:
    def test_first_worker_acquires_lock_and_starts(self):
        fake_fcntl = MagicMock()

        with patch.dict(sys.modules, {'fcntl': fake_fcntl}), \
                patch('builtins.open', mock_open()), \
                patch('apps.scheduler.jobs.start_scheduler') as mock_start, \
                patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'config.settings.production'}):
            _scheduler_config().ready()

        fake_fcntl.flock.assert_called_once()
        mock_start.assert_called_once()

    def test_second_worker_skips_if_lock_taken(self):
        fake_fcntl = MagicMock()
        fake_fcntl.flock.side_effect = IOError("another instance holds the lock")

        with patch.dict(sys.modules, {'fcntl': fake_fcntl}), \
                patch('builtins.open', mock_open()), \
                patch('apps.scheduler.jobs.start_scheduler') as mock_start, \
                patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'config.settings.production'}):
            _scheduler_config().ready()

        mock_start.assert_not_called()

    def test_lock_file_path_is_tmp_apscheduler_lock(self):
        fake_fcntl = MagicMock()
        m = mock_open()

        with patch.dict(sys.modules, {'fcntl': fake_fcntl}), \
                patch('builtins.open', m), \
                patch('apps.scheduler.jobs.start_scheduler'), \
                patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'config.settings.production'}):
            _scheduler_config().ready()

        m.assert_called_once_with('/tmp/apscheduler.lock', 'w')

    def test_scheduler_not_started_in_dev_environment(self):
        with patch('apps.scheduler.jobs.start_scheduler') as mock_start, \
                patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'config.settings.local', 'RUN_MAIN': 'false'}):
            _scheduler_config().ready()

        mock_start.assert_not_called()

    def test_scheduler_started_in_production_environment(self):
        fake_fcntl = MagicMock()

        with patch.dict(sys.modules, {'fcntl': fake_fcntl}), \
                patch('builtins.open', mock_open()), \
                patch('apps.scheduler.jobs.start_scheduler') as mock_start, \
                patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'config.settings.production'}):
            _scheduler_config().ready()

        mock_start.assert_called_once()
