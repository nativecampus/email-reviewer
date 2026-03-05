"""Redis connection factory and RQ queue helpers."""

from redis import Redis
from rq import Queue, Worker

from app.config import settings

QUEUE_NAME = "email-reviewer"


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
    return Queue(QUEUE_NAME, connection=conn)


def validate_redis() -> str | None:
    """Check Redis connectivity and worker availability.

    Returns None if everything is ok, or an error message string.
    """
    if not settings.REDIS_URL:
        return None

    conn = _get_connection()
    try:
        conn.ping()
    except Exception:
        return (
            f"REDIS_URL is configured ({settings.REDIS_URL}) but Redis is not reachable. "
            "Either start Redis or remove REDIS_URL from .env to run jobs in-process."
        )

    workers = Worker.all(connection=conn, queue_class=Queue)
    queue_workers = [
        w for w in workers if QUEUE_NAME in [q.name for q in w.queues]
    ]
    if not queue_workers:
        return (
            f"Redis is reachable but no workers are listening on the '{QUEUE_NAME}' queue. "
            f"Start a worker with: rq worker --url {settings.REDIS_URL} {QUEUE_NAME}"
        )

    return None


def redis_available() -> bool:
    """Return True if a Redis URL is configured."""
    return bool(settings.REDIS_URL)
