from django.utils import timezone

from apps.jobs.models import Job
from apps.jobs.services import enqueue_job

from .models import DeadLetterQueue


def move_to_dead_letter_queue(job, failure_reason):
    job.status = Job.Status.DEAD
    job.failure_reason = failure_reason
    job.completed_at = timezone.now()
    job.save(
        update_fields=(
            'status',
            'failure_reason',
            'completed_at',
            'updated_at',
        )
    )

    return DeadLetterQueue.objects.create(
        original_job=job,
        job_type=job.job_type,
        payload=job.payload,
        failure_reason=failure_reason,
        retry_attempts=job.retry_count,
    )


def requeue_dead_letter_job(dlq_entry, redis_client=None):
    job = dlq_entry.original_job
    job.status = Job.Status.PENDING
    job.retry_count = 0
    job.result = None
    job.failure_reason = None
    job.started_at = None
    job.completed_at = None
    job.save(
        update_fields=(
            'status',
            'retry_count',
            'result',
            'failure_reason',
            'started_at',
            'completed_at',
            'updated_at',
        )
    )
    queue_score = enqueue_job(job, redis_client=redis_client)

    return job, queue_score
