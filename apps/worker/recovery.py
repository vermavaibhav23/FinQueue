import logging

from apps.jobs.models import Job
from apps.jobs.services import enqueue_job
from core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


def recover_pending_jobs():
    redis_client = get_redis_client()
    pending_jobs = Job.objects.filter(status=Job.Status.PENDING).order_by('created_at')
    recovered_count = 0

    for job in pending_jobs:
        enqueue_job(job, redis_client=redis_client)
        recovered_count += 1

    logger.info('Recovered %s pending jobs into Redis.', recovered_count)

    return recovered_count
