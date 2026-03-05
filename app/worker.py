"""Redis connection factory and RQ queue helpers."""

from redis import Redis
from rq import Queue

from app.config import settings


def _get_connection():
    """Return a Redis connection if REDIS_URL is configured, else None."""
    if not settings.REDIS_URL:
        return None
    return Redis.from_url(settings.REDIS_URL)


def get_queue():
    """Return an RQ Queue for the 'email-reviewer' queue, or None if Redis is unavailable."""
    conn = _get_connection()
    if conn is None:
        return None
    return Queue("email-reviewer", connection=conn)


def redis_available() -> bool:
    """Return True if a Redis URL is configured."""
    return bool(settings.REDIS_URL)
