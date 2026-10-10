from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.redis_client import get_redis_client

from .models import Job, JobHistory


def record_job_history(job, message=None):
    return JobHistory.objects.create(
        job=job,
        status=job.status,
        retry_count=job.retry_count,
        message=message,
    )


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
        with transaction.atomic():
            job = (
                Job.objects.select_for_update()
                .filter(id=job_id)
                .first()
            )

            if job is None:
                redis_client.zrem(settings.FINQUEUE_RETRY_KEY, job_id)
                continue

            if job.status == Job.Status.FAILED:
                job.status = Job.Status.PENDING
                job.save(update_fields=('status', 'updated_at'))
                record_job_history(
                    job,
                    message='Retry delay elapsed; job returned to the main queue.',
                )
            elif job.status != Job.Status.PENDING:
                redis_client.zrem(settings.FINQUEUE_RETRY_KEY, job_id)
                continue

        # Enqueue first, then remove from the retry set. If the process dies
        # between these two Redis operations, re-adding the same member is safe.
        enqueue_job(job, redis_client=redis_client)
        redis_client.zrem(settings.FINQUEUE_RETRY_KEY, job_id)
        promoted_count += 1

    return promoted_count


def create_refund_follow_up_jobs(refund_job, redis_client=None):
    if refund_job.job_type != Job.JobType.REFUND_PROCESSING:
        return []

    if refund_job.status not in (Job.Status.COMPLETED, Job.Status.DEAD):
        return []

    payload = refund_job.payload
    notification = payload.get('notification', {})

    if refund_job.status == Job.Status.COMPLETED:
        event = 'refund.completed'
        refund_id = (refund_job.result or {}).get('refund_id')
        message = (
            f"Your refund of {payload.get('amount')} "
            f"{payload.get('currency', 'INR')} has been processed."
        )
    else:
        event = 'refund.failed'
        refund_id = None
        message = (
            f"Your refund of {payload.get('amount')} "
            f"{payload.get('currency', 'INR')} could not be processed."
        )

    # These IDs stay stable for the same logical external side effect.
    # A downstream merchant/provider can use them as its idempotency key.
    event_id = f'webhook:{event}:{refund_job.id}'
    notification_id = f'notification:{event}:{refund_job.id}'

    event_data = {
        'source_job_id': str(refund_job.id),
        'transaction_id': payload.get('transaction_id'),
        'refund_id': refund_id,
        'amount': str(payload.get('amount')),
        'currency': payload.get('currency', 'INR'),
        'status': refund_job.status,
    }

    if refund_job.failure_reason:
        event_data['failure_reason'] = refund_job.failure_reason

    follow_up_specs = (
        (
            Job.JobType.WEBHOOK_DELIVERY,
            Job.Priority.MEDIUM,
            {
                'url': payload.get('webhook_url'),
                'event': event,
                'event_id': event_id,
                'data': event_data,
            },
        ),
        (
            Job.JobType.SEND_NOTIFICATION,
            Job.Priority.LOW,
            {
                'channel': notification.get('channel'),
                'recipient': notification.get('recipient'),
                'message': message,
                'notification_id': notification_id,
            },
        ),
    )

    follow_up_jobs = []

    with transaction.atomic():
        for job_type, priority, follow_up_payload in follow_up_specs:
            follow_up_job, created = Job.objects.get_or_create(
                source_job=refund_job,
                source_event=event,
                job_type=job_type,
                defaults={
                    'user': refund_job.user,
                    'priority': priority,
                    'payload': follow_up_payload,
                },
            )
            if created:
                record_job_history(
                    follow_up_job,
                    message=f'Follow-up job created from {event}.',
                )
            follow_up_jobs.append(follow_up_job)

    for follow_up_job in follow_up_jobs:
        if follow_up_job.status == Job.Status.PENDING:
            enqueue_job(follow_up_job, redis_client=redis_client)

    return follow_up_jobs
