import logging
import random
import time
from decimal import Decimal, InvalidOperation

from apps.jobs.models import Job

logger = logging.getLogger(__name__)

REFUND_FAILURE_RATE = 0.20
WEBHOOK_FAILURE_RATE = 0.15
NOTIFICATION_FAILURE_RATE = 0.10


def get_external_operation_id(job):
    """
    Return the stable ID FinQueue sends to the downstream system.

    The same Job row is retried after failures/recovery, so deriving the ID from
    persisted job/source information guarantees every retry sends the same ID.
    The receiving system still has to honor that ID for true external
    idempotency.
    """
    if job.job_type == Job.JobType.REFUND_PROCESSING:
        return f'refund:{job.id}'

    if job.job_type == Job.JobType.WEBHOOK_DELIVERY:
        event_id = str(job.payload.get('event_id', '')).strip()
        return event_id or f'webhook:{job.id}'

    if job.job_type == Job.JobType.SEND_NOTIFICATION:
        notification_id = str(job.payload.get('notification_id', '')).strip()
        return notification_id or f'notification:{job.id}'

    return f'job:{job.id}'


def handle_refund_processing(job):
    payload = job.payload
    amount = _get_amount(payload)
    transaction_id = str(payload.get('transaction_id', '')).strip()
    idempotency_key = get_external_operation_id(job)

    if amount <= 0:
        raise ValueError('Refund amount must be greater than 0.')

    if not transaction_id:
        raise ValueError('Refund requires transaction_id.')

    # Simulate:
    # POST payment-provider/refunds
    # Idempotency-Key: refund:<job UUID>
    #
    # A real provider must store/honor this key so retrying the same FinQueue
    # job cannot create a second refund.
    logger.info(
        'Simulated refund provider call for transaction %s with Idempotency-Key=%s.',
        transaction_id,
        idempotency_key,
    )
    time.sleep(1)

    if _should_simulate_failure(payload, REFUND_FAILURE_RATE):
        raise RuntimeError('Refund provider is temporarily unavailable.')

    refund_id = f'refund-{str(job.id)[:8]}'

    return {
        'refund_id': refund_id,
        'transaction_id': transaction_id,
        'status': 'REFUNDED',
        'amount': str(amount),
        'currency': payload.get('currency', 'INR'),
    }


def handle_webhook_delivery(job):
    payload = job.payload
    url = str(payload.get('url', '')).strip()
    event = str(payload.get('event', '')).strip()
    event_id = get_external_operation_id(job)

    if not url.startswith(('http://', 'https://')):
        raise ValueError('Webhook requires a valid http/https url.')

    if not event:
        raise ValueError('Webhook requires an event name.')

    # A real outbound body would contain event_id. The merchant backend should
    # store processed event IDs and return success without re-applying the side
    # effect when it receives the same event_id again.
    outbound_body = {
        'event_id': event_id,
        'event': event,
        'data': payload.get('data', {}),
    }

    time.sleep(0.5)

    if _should_simulate_failure(payload, WEBHOOK_FAILURE_RATE):
        raise RuntimeError('Webhook endpoint returned a temporary 5xx response.')

    logger.info(
        'Simulated webhook delivery to %s with body %s.',
        url,
        outbound_body,
    )

    return {
        'webhook_delivery_status': 'DELIVERED',
        'http_status': 200,
    }


def handle_send_notification(job):
    payload = job.payload
    channel = str(payload.get('channel', '')).lower().strip()
    recipient = str(payload.get('recipient', '')).strip()
    message = str(payload.get('message', '')).strip()
    notification_id = get_external_operation_id(job)

    if channel not in {'email', 'sms', 'push'}:
        raise ValueError('Notification channel must be email, sms, or push.')

    if not recipient or not message:
        raise ValueError('Notification requires recipient and message.')

    # A real notification provider would receive notification_id as an
    # idempotency/deduplication key. Retrying the same FinQueue job reuses it.
    time.sleep(0.25)

    if _should_simulate_failure(payload, NOTIFICATION_FAILURE_RATE):
        raise RuntimeError(f'{channel} provider is temporarily unavailable.')

    logger.info(
        'Simulated %s notification to %s with notification_id=%s: %s',
        channel,
        recipient,
        notification_id,
        message,
    )

    return {
        'notification_status': 'SENT',
        'channel': channel,
    }


def dispatch_job(job):
    handlers = {
        Job.JobType.REFUND_PROCESSING: handle_refund_processing,
        Job.JobType.WEBHOOK_DELIVERY: handle_webhook_delivery,
        Job.JobType.SEND_NOTIFICATION: handle_send_notification,
    }

    handler = handlers.get(job.job_type)
    if handler is None:
        raise ValueError(f'Unsupported job type: {job.job_type}')

    return handler(job)


def _should_simulate_failure(payload, failure_rate):
    # Explicit flag is kept for deterministic demos/tests. Otherwise the dummy
    # provider fails randomly so retries/backoff/DLQ can happen naturally.
    if payload.get('simulate_failure'):
        return True

    return random.random() < failure_rate


def _get_amount(payload):
    try:
        return Decimal(str(payload.get('amount')))
    except (InvalidOperation, TypeError):
        raise ValueError('Payload must include a valid amount.')
