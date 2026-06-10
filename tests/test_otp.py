from unittest.mock import patch

import pytest

from utils.otp import check_rate_limit, get_rate_limit_key, increment_attempts

PHONE = '+998901234567'


class FakeRedis:
    """In-memory stand-in for the raw Redis connection used by utils.otp."""

    def __init__(self):
        self.store = {}
        self.ttls = {}

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, seconds):
        self.ttls[key] = seconds

    def get(self, key):
        value = self.store.get(key)
        return str(value).encode() if value is not None else None

    def delete(self, key):
        self.store.pop(key, None)
        self.ttls.pop(key, None)

    def ttl(self, key):
        return self.ttls.get(key, -2)


@pytest.fixture
def fake_redis():
    redis = FakeRedis()
    with patch('utils.otp.get_redis', return_value=redis):
        yield redis


class TestRateLimit:
    def test_two_attempts_allowed(self, fake_redis):
        increment_attempts(PHONE)
        increment_attempts(PHONE)

        assert check_rate_limit(PHONE) == {"allowed": True, "wait_seconds": 0}

    def test_three_attempts_blocked_30_minutes(self, fake_redis):
        for _ in range(3):
            increment_attempts(PHONE)

        assert check_rate_limit(PHONE) == {"allowed": False, "wait_seconds": 1800}

    def test_clear_after_three_attempts_unblocks(self, fake_redis):
        for _ in range(3):
            increment_attempts(PHONE)

        fake_redis.delete(get_rate_limit_key(PHONE))

        assert check_rate_limit(PHONE) == {"allowed": True, "wait_seconds": 0}

    def test_five_attempts_blocked_5_hours(self, fake_redis):
        for _ in range(5):
            increment_attempts(PHONE)

        assert check_rate_limit(PHONE) == {"allowed": False, "wait_seconds": 18000}

    def test_seven_attempts_blocked_24_hours(self, fake_redis):
        for _ in range(7):
            increment_attempts(PHONE)

        assert check_rate_limit(PHONE) == {"allowed": False, "wait_seconds": 86400}

    def test_key_ttl_set_to_30_minutes(self, fake_redis):
        increment_attempts(PHONE)

        assert fake_redis.ttl(get_rate_limit_key(PHONE)) == 1800
