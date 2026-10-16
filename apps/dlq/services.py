from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.jobs.models import Job
from apps.jobs.services import (
    create_refund_follow_up_jobs,
    enqueue_job,
    record_job_history,
)

from .models import DeadLetterQueue


def move_to_dead_letter_queue(job, failure_reason):
    with transaction.atomic():
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
        record_job_history(
            job,
            message=f'Retries exhausted: {failure_reason}',
        )

        dlq_entry = DeadLetterQueue.objects.create(
            original_job=job,
            job_type=job.job_type,
            payload=job.payload,
            failure_reason=failure_reason,
            retry_attempts=job.retry_count,
        )

        follow_up_jobs = create_refund_follow_up_jobs(job)

    return dlq_entry, follow_up_jobs


def requeue_dead_letter_job(dlq_entry, redis_client=None):
    with transaction.atomic():
        # Lock and recheck: two admin requests must not advance the round twice.
        job = Job.objects.select_for_update().get(pk=dlq_entry.original_job_id)
        if job.status != Job.Status.DEAD:
            raise ValidationError('Only DEAD jobs can be manually requeued.')

        # A previously deleted DLQ ID cannot requeue a later DEAD attempt.
        if not DeadLetterQueue.objects.filter(
            pk=dlq_entry.pk, original_job_id=job.pk,
        ).exists():
            raise ValidationError('DLQ entry is no longer active.')

        # A requeued refund produces a *new* terminal event. Retrying a DEAD
        # webhook/notification instead repeats the same existing event.
        if job.job_type == Job.JobType.REFUND_PROCESSING:
            job.processing_round += 1

        job.status = Job.Status.PENDING
        job.retry_count = 0
        job.result = None
        job.failure_reason = None
        job.completed_at = None
        job.save(
            update_fields=(
                'processing_round',
                'status',
                'retry_count',
                'result',
                'failure_reason',
                'completed_at',
                'updated_at',
            )
        )
        record_job_history(job, message='Requeued from dead-letter queue.')
        # Keep the DLQ restricted to currently DEAD jobs; retain audit in history.
        DeadLetterQueue.objects.filter(pk=dlq_entry.pk).delete()

    queue_score = enqueue_job(job, redis_client=redis_client)

    return job, queue_score
