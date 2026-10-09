import logging
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.dlq.services import move_to_dead_letter_queue
from apps.jobs.models import Job
from apps.jobs.services import (
    calculate_retry_delay,
    create_refund_follow_up_jobs,
    promote_due_retries,
    schedule_retry,
)
from apps.worker.handlers import dispatch_job
from core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class WorkerEngine:
    def __init__(self, poll_interval=1):
        self.poll_interval = poll_interval
        self.redis_client = get_redis_client()

    def run_forever(self):
        logger.info('FinQueue worker started.')

        while True:
            processed = self.process_next_job()

            if not processed:
                time.sleep(self.poll_interval)

    def process_next_job(self):
        promote_due_retries(self.redis_client)
        popped_jobs = self.redis_client.zpopmin(settings.FINQUEUE_JOBS_KEY, count=1)

        if not popped_jobs:
            return False

        job_id, score = popped_jobs[0]
        logger.info('Picked job %s from Redis with score %s.', job_id, score)
        self.execute_job(job_id)

        return True

    def execute_job(self, job_id):
        with transaction.atomic():
            try:
                job = Job.objects.select_for_update().get(id=job_id)
            except Job.DoesNotExist:
                logger.warning('Skipping missing job %s.', job_id)
                return

            if job.status != Job.Status.PENDING:
                logger.warning(
                    'Skipping job %s because status is %s.',
                    job.id,
                    job.status,
                )
                return

            now = timezone.now()
            job.status = Job.Status.RUNNING
            job.started_at = now
            job.lease_expires_at = now + timedelta(
                seconds=settings.FINQUEUE_JOB_LEASE_SECONDS
            )
            job.save(
                update_fields=(
                    'status',
                    'started_at',
                    'lease_expires_at',
                    'updated_at',
                )
            )

        stop_heartbeat, heartbeat_thread = self._start_lease_heartbeat(job.id)

        try:
            result = self.handle_job(job)
        except Exception as exc:
            self._stop_lease_heartbeat(stop_heartbeat, heartbeat_thread)
            self.mark_failed(job, str(exc))
            return

        self._stop_lease_heartbeat(stop_heartbeat, heartbeat_thread)
        self.mark_completed(job, result)

    def handle_job(self, job):
        return dispatch_job(job)

    def mark_completed(self, job, result):
        job.status = Job.Status.COMPLETED
        job.result = result
        job.completed_at = timezone.now()
        job.failure_reason = None
        job.lease_expires_at = None
        job.save(
            update_fields=(
                'status',
                'result',
                'completed_at',
                'failure_reason',
                'lease_expires_at',
                'updated_at',
            )
        )
        logger.info('Completed job %s.', job.id)
        self._enqueue_terminal_follow_ups(job)

    def mark_failed(self, job, failure_reason):
        job.lease_expires_at = None

        if job.retry_count < settings.FINQUEUE_MAX_RETRIES:
            job.retry_count += 1
            delay_seconds = calculate_retry_delay(job.retry_count)
            job.status = Job.Status.PENDING
            job.failure_reason = failure_reason
            job.completed_at = None
            job.save(
                update_fields=(
                    'status',
                    'retry_count',
                    'failure_reason',
                    'completed_at',
                    'lease_expires_at',
                    'updated_at',
                )
            )
            retry_at = schedule_retry(job, delay_seconds, self.redis_client)
            logger.warning(
                'Retrying job %s in %s seconds at %s.',
                job.id,
                delay_seconds,
                retry_at,
            )
            return

        dlq_entry = move_to_dead_letter_queue(job, failure_reason)
        logger.error(
            'Moved job %s to DLQ entry %s after %s retries: %s',
            job.id,
            dlq_entry.id,
            job.retry_count,
            failure_reason,
        )
        self._enqueue_terminal_follow_ups(job)

    def _start_lease_heartbeat(self, job_id):
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(job_id, stop_event),
            name=f'finqueue-heartbeat-{job_id}',
            daemon=True,
        )
        thread.start()
        return stop_event, thread

    @staticmethod
    def _stop_lease_heartbeat(stop_event, thread):
        stop_event.set()
        thread.join(timeout=1)

    @staticmethod
    def _heartbeat_loop(job_id, stop_event):
        interval = settings.FINQUEUE_HEARTBEAT_INTERVAL_SECONDS
        lease_seconds = settings.FINQUEUE_JOB_LEASE_SECONDS

        while not stop_event.wait(interval):
            close_old_connections()
            try:
                now = timezone.now()
                updated = Job.objects.filter(
                    id=job_id,
                    status=Job.Status.RUNNING,
                ).update(
                    lease_expires_at=now + timedelta(seconds=lease_seconds)
                )

                if updated == 0:
                    return

                logger.debug('Renewed lease for job %s.', job_id)
            except Exception:
                logger.exception('Could not renew lease for job %s.', job_id)
            finally:
                close_old_connections()

    def _enqueue_terminal_follow_ups(self, job):
        if job.job_type != Job.JobType.REFUND_PROCESSING:
            return

        try:
            follow_up_jobs = create_refund_follow_up_jobs(
                job,
                redis_client=self.redis_client,
            )
        except Exception:
            # The refund has already reached a terminal state. A failure while
            # creating side-effect jobs must not roll the refund back.
            logger.exception(
                'Could not create follow-up jobs for refund job %s.',
                job.id,
            )
            return

        logger.info(
            'Created/queued %s follow-up jobs for refund job %s.',
            len(follow_up_jobs),
            job.id,
        )
