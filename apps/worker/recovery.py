import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.jobs.models import Job
from apps.jobs.services import enqueue_job, record_job_history
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


def recover_stale_running_jobs(redis_client=None, now=None):
    """
    Requeue jobs that have remained RUNNING beyond the configured threshold.

    The educational project uses a simple 30-second threshold. started_at is
    intentionally preserved after recovery so FinQueue still knows the job was
    previously attempted. Because an external call may already have succeeded
    before a worker crash, every retry must reuse its stable external
    idempotency/event ID.
    """
    redis_client = redis_client or get_redis_client()
    now = now or timezone.now()
    stale_before = now - timedelta(
        seconds=settings.FINQUEUE_STALE_RUNNING_SECONDS
    )

    stale_ids = list(
        Job.objects.filter(
            status=Job.Status.RUNNING,
            started_at__isnull=False,
            started_at__lte=stale_before,
        ).values_list('id', flat=True)
    )

    recovered_count = 0

    for job_id in stale_ids:
        with transaction.atomic():
            job = (
                Job.objects.select_for_update()
                .filter(
                    id=job_id,
                    status=Job.Status.RUNNING,
                    started_at__isnull=False,
                    started_at__lte=stale_before,
                )
                .first()
            )

            if job is None:
                continue

            job.status = Job.Status.PENDING
            job.failure_reason = (
                'Recovered after remaining RUNNING beyond the stale-job '
                'threshold; previous external attempt outcome may be unknown.'
            )
            job.save(
                update_fields=(
                    'status',
                    'failure_reason',
                    'updated_at',
                )
            )
            record_job_history(job, message=job.failure_reason)

        enqueue_job(job, redis_client=redis_client)
        recovered_count += 1
        logger.warning(
            'Recovered stale RUNNING job %s back to PENDING.',
            job_id,
        )

    return recovered_count


class StaleJobRecoveryWorker:
    def __init__(self, poll_interval=None):
        self.poll_interval = (
            poll_interval
            if poll_interval is not None
            else settings.FINQUEUE_RECOVERY_POLL_SECONDS
        )
        self.redis_client = get_redis_client()

    def run_once(self):
        return recover_stale_running_jobs(redis_client=self.redis_client)

    def run_forever(self):
        logger.info('FinQueue stale-job recovery worker started.')

        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception('Stale-job recovery scan failed.')

            time.sleep(self.poll_interval)
