import random
from django.core.cache import cache


def get_redis():
    from django_redis import get_redis_connection
    return get_redis_connection("default")


def generate_otp(phone: str) -> str:
    code = str(random.randint(100000, 999999))
    cache.set(f"otp:{phone}", code, timeout=100)
    return code


def verify_otp(phone: str, code: str) -> str:
    """Returns 'valid', 'invalid', or 'expired'."""
    stored = cache.get(f"otp:{phone}")
    if stored is None:
        return 'expired'
    if str(stored) == str(code):
        cache.delete(f"otp:{phone}")
        return 'valid'
    return 'invalid'


def get_rate_limit_key(phone: str) -> str:
    return f"otp_attempts:{phone}"


def check_rate_limit(phone: str) -> dict:
    key = get_rate_limit_key(phone)
    attempts = get_redis().get(key)
    attempts = int(attempts) if attempts else 0

    if attempts >= 7:
        return {"allowed": False, "wait_seconds": 86400}
    elif attempts >= 6:
        return {"allowed": False, "wait_seconds": 43200}
    elif attempts >= 5:
        return {"allowed": False, "wait_seconds": 18000}
    elif attempts >= 3:
        return {"allowed": False, "wait_seconds": 1800}
    else:
        return {"allowed": True, "wait_seconds": 0}


def increment_attempts(phone: str) -> None:
    key = get_rate_limit_key(phone)
    r = get_redis()
    r.incr(key)
    r.expire(key, 24 * 3600)
