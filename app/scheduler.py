"""APScheduler — worker 컨테이너 내 별도 프로세스 (DESIGN §2 '알람시계').

정해진 시각에 run_pipeline 잡을 Redis(Arq) 큐에 등록만 한다. 실제 실행은 워커가 한다.
무거운 일을 직접 하지 않으므로 가볍고, 운영 시 Arq cron으로 흡수 가능.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings

logger = logging.getLogger("lede.scheduler")


async def main() -> None:
    settings = get_settings()
    redis = await create_pool(RedisSettings.from_dsn(str(settings.redis_url)))

    async def trigger() -> None:
        job = await redis.enqueue_job("run_pipeline")
        logger.info("run_pipeline enqueued (job_id=%s)", job.job_id if job else None)

    scheduler = AsyncIOScheduler(timezone=settings.schedule_timezone)
    scheduler.add_job(
        trigger,
        CronTrigger(
            hour=settings.schedule_hour,
            minute=settings.schedule_minute,
            timezone=settings.schedule_timezone,
        ),
        id="daily_pipeline",
    )
    scheduler.start()
    logger.info(
        "scheduler started: daily run_pipeline at %02d:%02d %s",
        settings.schedule_hour,
        settings.schedule_minute,
        settings.schedule_timezone,
    )
    await asyncio.Event().wait()  # 프로세스 유지


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(main())
