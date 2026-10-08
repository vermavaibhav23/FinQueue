import logging
import time
from decimal import Decimal, InvalidOperation

from apps.jobs.models import Job

logger = logging.getLogger(__name__)


def handle_refund_processing(job):
    payload = job.payload
    amount = _get_amount(payload)
    transaction_id = str(payload.get('transaction_id', '')).strip()

    if amount <= 0:
        raise ValueError('Refund amount must be greater than 0.')

    if not transaction_id:
        raise ValueError('Refund requires transaction_id.')

    # Simulate an external payment provider call without requiring a real gateway.
    time.sleep(1)

    if payload.get('simulate_failure'):
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

    if not url.startswith(('http://', 'https://')):
        raise ValueError('Webhook requires a valid http/https url.')

    if not event:
        raise ValueError('Webhook requires an event name.')

    # This project intentionally simulates the outbound HTTP call so it can be
    # demonstrated locally without depending on an external webhook endpoint.
    time.sleep(0.5)

    if payload.get('simulate_failure'):
        raise RuntimeError('Webhook endpoint returned a temporary 5xx response.')

    logger.info(
        'Simulated webhook delivery to %s for event %s with data %s.',
        url,
        event,
        payload.get('data', {}),
    )

    return {
        'delivery_status': 'DELIVERED',
        'url': url,
        'event': event,
        'http_status': 200,
    }


def handle_send_notification(job):
    payload = job.payload
    channel = str(payload.get('channel', '')).lower().strip()
    recipient = str(payload.get('recipient', '')).strip()
    message = str(payload.get('message', '')).strip()

    if channel not in {'email', 'sms', 'push'}:
        raise ValueError('Notification channel must be email, sms, or push.')

    if not recipient or not message:
        raise ValueError('Notification requires recipient and message.')

    time.sleep(0.25)

    if payload.get('simulate_failure'):
        raise RuntimeError(f'{channel} provider is temporarily unavailable.')

    logger.info(
        'Simulated %s notification to %s: %s',
        channel,
        recipient,
        message,
    )

    return {
        'notification_status': 'SENT',
        'channel': channel,
        'recipient': recipient,
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


def _get_amount(payload):
    try:
        return Decimal(str(payload.get('amount')))
    except (InvalidOperation, TypeError):
        raise ValueError('Payload must include a valid amount.')
