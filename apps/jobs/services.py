from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from core.redis_client import get_redis_client

from .models import Job


PRIORITY_SCORES = {
    Job.Priority.HIGH: 1,
    Job.Priority.MEDIUM: 2,
    Job.Priority.LOW: 3,
}


def calculate_priority_score(job):
    priority_base = PRIORITY_SCORES[job.priority]
    timestamp_tiebreaker = job.created_at.timestamp() / 10**10

    return priority_base + timestamp_tiebreaker


def enqueue_job(job, redis_client=None):
    redis_client = redis_client or get_redis_client()
    score = calculate_priority_score(job)

    redis_client.zadd(settings.FINQUEUE_JOBS_KEY, {str(job.id): score})

    return score


def remove_job_from_queues(job_id, redis_client=None):
    redis_client = redis_client or get_redis_client()

    redis_client.zrem(settings.FINQUEUE_JOBS_KEY, str(job_id))
    redis_client.zrem(settings.FINQUEUE_RETRY_KEY, str(job_id))


def calculate_retry_delay(retry_count):
    return 2**retry_count


def schedule_retry(job, delay_seconds, redis_client=None):
    redis_client = redis_client or get_redis_client()
    retry_at = timezone.now() + timedelta(seconds=delay_seconds)

    redis_client.zadd(settings.FINQUEUE_RETRY_KEY, {str(job.id): retry_at.timestamp()})

    return retry_at


def promote_due_retries(redis_client=None):
    redis_client = redis_client or get_redis_client()
    now_score = timezone.now().timestamp()
    due_job_ids = redis_client.zrangebyscore(settings.FINQUEUE_RETRY_KEY, 0, now_score)

    if not due_job_ids:
        return 0

    promoted_count = 0

    for job_id in due_job_ids:
        removed = redis_client.zrem(settings.FINQUEUE_RETRY_KEY, job_id)

        if removed:
            job = Job.objects.filter(id=job_id, status=Job.Status.PENDING).first()

            if job is None:
                continue

            enqueue_job(job, redis_client=redis_client)
            promoted_count += 1

    return promoted_count
