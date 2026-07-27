import os

import redis

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _client = redis.Redis.from_url(redis_url, decode_responses=True)
    return _client


def close_redis() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def check_redis() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception:
        return False


RECENT_KEY = "cowsay:recent"
RECENT_MAX = 5


def push_recent(text: str) -> None:
    client = get_redis()
    client.lpush(RECENT_KEY, text)
    client.ltrim(RECENT_KEY, 0, RECENT_MAX - 1)
