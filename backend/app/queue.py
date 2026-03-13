from redis import Redis
from rq import Queue

from .config import settings


def get_queue() -> Queue:
    connection = Redis.from_url(settings.redis_url)
    return Queue("sync", connection=connection)

