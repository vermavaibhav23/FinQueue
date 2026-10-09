import logging
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

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


def recover_stale_running_jobs(redis_client=None, now=None):
    """
    Requeue RUNNING jobs whose worker lease expired.

    A healthy worker keeps extending lease_expires_at from a heartbeat thread.
    A hard process crash stops that heartbeat. The separate recovery process
    then moves the abandoned job back to PENDING and puts it in Redis again.

    started_at is intentionally preserved so we still know the job was already
    attempted. Because an external call may have succeeded just before the
    crash, handlers must reuse a stable external idempotency/event ID.
    """
    redis_client = redis_client or get_redis_client()
    now = now or timezone.now()

    stale_ids = list(
        Job.objects.filter(
            status=Job.Status.RUNNING,
            lease_expires_at__isnull=False,
            lease_expires_at__lte=now,
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
                    lease_expires_at__isnull=False,
                    lease_expires_at__lte=timezone.now(),
                )
                .first()
            )

            if job is None:
                continue

            job.status = Job.Status.PENDING
            job.lease_expires_at = None
            job.failure_reason = (
                'Recovered after worker lease expired; previous external '
                'attempt outcome may be unknown.'
            )
            job.save(
                update_fields=(
                    'status',
                    'lease_expires_at',
                    'failure_reason',
                    'updated_at',
                )
            )

            # Enqueue while the DB row lock is still held. If Redis fails, the
            # transaction rolls back and the job remains RUNNING so the next
            # recovery scan can try again. If the DB later rolls back after the
            # Redis write, a normal worker will pop the ID, see RUNNING, and skip.
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
