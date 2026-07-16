import logging
import random
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from apps.jobs.models import Job, Transaction

logger = logging.getLogger(__name__)


def handle_process_payment(job):
    payload = job.payload
    amount = _get_amount(payload)

    if amount <= 0:
        raise ValueError('Payment amount must be greater than 0.')

    time.sleep(2)

    outcome = random.choices(
        population=('success', 'failed'),
        weights=(80, 20),
        k=1,
    )[0]

    if outcome == 'failed':
        Transaction.objects.create(
            job=job,
            user=job.user,
            amount=amount,
            merchant=payload.get('merchant', 'Unknown merchant'),
            currency=payload.get('currency', 'INR'),
            device_id=payload.get('device_id', ''),
            location=payload.get('location', ''),
            status=Transaction.Status.FAILED,
            processed_at=timezone.now(),
        )
        raise RuntimeError('Payment gateway failed.')

    transaction = Transaction.objects.create(
        job=job,
        user=job.user,
        amount=amount,
        merchant=payload.get('merchant', 'Unknown merchant'),
        currency=payload.get('currency', 'INR'),
        device_id=payload.get('device_id', ''),
        location=payload.get('location', ''),
        status=Transaction.Status.SUCCESS,
        processed_at=timezone.now(),
    )

    return {
        'transaction_id': str(transaction.id),
        'status': 'SUCCESS',
        'amount': str(transaction.amount),
        'merchant': transaction.merchant,
        'currency': transaction.currency,
    }


def handle_fraud_check(job):
    payload = job.payload
    amount = _get_amount(payload)
    device_id = payload.get('device_id', '')
    location = payload.get('location', '')
    risk_score = 0
    risk_reasons = []

    if amount > Decimal('100000'):
        risk_score += 40
        risk_reasons.append('High value transaction')
    elif amount > Decimal('50000'):
        risk_score += 20
        risk_reasons.append('Medium value transaction')

    recent_count = Transaction.objects.filter(
        user=job.user,
        processed_at__gte=timezone.now() - timedelta(minutes=2),
    ).count()

    if recent_count >= 3:
        risk_score += 40
        risk_reasons.append('Multiple transactions in short time')

    known_devices = set(
        Transaction.objects.filter(user=job.user)
        .exclude(device_id='')
        .values_list('device_id', flat=True)
        .distinct()
    )

    if device_id and device_id not in known_devices:
        risk_score += 20
        risk_reasons.append('New device detected')

    current_hour = timezone.localtime().hour
    if 0 <= current_hour <= 4:
        risk_score += 10
        risk_reasons.append('Unusual transaction hour')

    if risk_score >= 60:
        decision = 'REJECTED'
        transaction_status = Transaction.Status.REJECTED
    elif risk_score >= 30:
        decision = 'SUSPICIOUS'
        transaction_status = Transaction.Status.SUSPICIOUS
    else:
        decision = 'CLEARED'
        transaction_status = Transaction.Status.SUCCESS

    transaction = Transaction.objects.create(
        job=job,
        user=job.user,
        amount=amount,
        merchant=payload.get('merchant', 'Unknown merchant'),
        currency=payload.get('currency', 'INR'),
        device_id=device_id,
        location=location,
        status=transaction_status,
        risk_score=risk_score,
        risk_reasons=risk_reasons,
        processed_at=timezone.now(),
    )

    return {
        'transaction_id': str(transaction.id),
        'decision': decision,
        'risk_score': risk_score,
        'risk_reasons': risk_reasons,
    }


def handle_send_notification(job):
    payload = job.payload
    status = str(payload.get('status', '')).upper()
    amount = payload.get('amount', '0')
    merchant = payload.get('merchant', 'merchant')
    txn_id = payload.get('txn_id', payload.get('transaction_id', 'N/A'))

    messages = {
        'CLEARED': f'Your payment of Rs.{amount} to {merchant} is being processed.',
        'SUSPICIOUS': f'Your payment of Rs.{amount} has been flagged for review.',
        'REJECTED': f'Your payment of Rs.{amount} was declined due to suspicious activity.',
        'SUCCESS': f'Your payment of Rs.{amount} to {merchant} was successful. Txn: {txn_id}',
        'FAILED': f'Your payment of Rs.{amount} to {merchant} failed. Please retry.',
    }
    message = messages.get(status, 'Your payment update is available.')

    logger.info('Simulated notification for user %s: %s', job.user_id, message)
    print(message)

    return {
        'notification_status': 'SENT',
        'message': message,
    }


def dispatch_job(job):
    handlers = {
        Job.JobType.PROCESS_PAYMENT: handle_process_payment,
        Job.JobType.FRAUD_CHECK: handle_fraud_check,
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
