from redis import Redis
from rq import Connection, Worker

from app.config import settings


def main() -> None:
    redis = Redis.from_url(settings.redis_url)
    with Connection(redis):
        worker = Worker(["sync"])
        worker.work()


if __name__ == "__main__":
    main()

