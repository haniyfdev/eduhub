from .base import *
import urllib.parse as _up
from decouple import config

DEBUG = True

ALLOWED_HOSTS = ['*']

_database_url = config('DATABASE_URL', default='postgresql://postgres:sheyh123@localhost:5432/eduhub')
_parsed = _up.urlparse(_database_url)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _parsed.path.lstrip('/'),
        'USER': _parsed.username,
        'PASSWORD': _parsed.password,
        'HOST': _parsed.hostname,
        'PORT': _parsed.port or 5432,
    }
}

CORS_ALLOW_ALL_ORIGINS = True

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

CELERY_TASK_ALWAYS_EAGER = True
