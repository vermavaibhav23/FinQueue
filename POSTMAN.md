# FinQueue API testing guide

Base URL:

```text
http://127.0.0.1:8000
```

Create Postman variables named `base_url`, `access_token`, `refresh_token`,
`job_id`, and `dlq_id`.

## Authentication

### Register

```http
POST {{base_url}}/auth/register/
Content-Type: application/json
```

```json
{
  "username": "testuser",
  "email": "test@example.com",
  "password": "securepassword123"
}
```

Successful response (`201 Created`):

```json
{
  "user": {
    "id": 1,
    "username": "testuser",
    "email": "test@example.com"
  },
  "tokens": {
    "refresh": "<refresh-token>",
    "access": "<access-token>"
  }
}
```

### Login

```http
POST {{base_url}}/auth/login/
Content-Type: application/json
```

```json
{
  "username": "testuser",
  "password": "securepassword123"
}
```

Successful response (`200 OK`):

```json
{
  "refresh": "<refresh-token>",
  "access": "<access-token>"
}
```

Use the access token on authenticated endpoints:

```http
Authorization: Bearer {{access_token}}
```

### Logout

```http
POST {{base_url}}/auth/logout/
Content-Type: application/json
```

```json
{
  "refresh": "{{refresh_token}}"
}
```

Successful response (`205 Reset Content`):

```json
{
  "detail": "Logged out successfully."
}
```

Logging out blacklists the refresh token. An already-issued access token remains
valid until it expires.

## Jobs

Server-assigned priorities are:

- `refund_processing` -> high
- `webhook_delivery` -> medium
- `send_notification` -> low

The client does not choose priority.

## Normal flow: submit only the refund job

The normal project flow starts with one `refund_processing` request. When it
reaches `completed` or `dead`, FinQueue automatically creates the appropriate
webhook and notification jobs.

```http
POST {{base_url}}/jobs/submit/
Authorization: Bearer {{access_token}}
Idempotency-Key: refund-1001
Content-Type: application/json
```

```json
{
  "job_type": "refund_processing",
  "payload": {
    "transaction_id": "txn-1001",
    "amount": "1000.00",
    "currency": "INR",
    "webhook_url": "https://merchant.example/webhooks",
    "notification": {
      "channel": "email",
      "recipient": "customer@example.com"
    }
  }
}
```

Successful response (`202 Accepted`):

```json
{
  "id": "12f18c85-b610-4bf6-9fd9-1b5a9c645e78",
  "job_type": "refund_processing",
  "priority": "high",
  "status": "pending",
  "created_at": "2026-10-08T10:00:00Z",
  "idempotent_replay": false
}
```

The API has accepted the job; the worker will complete it later.

### Merchant/API idempotency

`Idempotency-Key` is required on job submission.

- same merchant + same key + same payload -> return the existing job
- same merchant + same key + different payload -> `409 Conflict`
- new key -> create a new job

FinQueue stores this mapping in the `idempotency_requests` table using the
authenticated user, idempotency key, SHA-256 request hash, and created job ID.
An idempotent replay returns `200 OK` with `"idempotent_replay": true`.

This is separate from follow-up idempotency, which uses
`UNIQUE(source_job, job_type, source_event)`.

### On refund success

The refund becomes `completed` and FinQueue internally creates:

```text
webhook_delivery    priority=medium    event=refund.completed
send_notification   priority=low       success message
```

Both follow-up jobs have `source_job` set to the original refund job and
`source_event` set to `refund.completed`.

Example generated webhook payload:

```json
{
  "url": "https://merchant.example/webhooks",
  "event": "refund.completed",
  "data": {
    "source_job_id": "12f18c85-b610-4bf6-9fd9-1b5a9c645e78",
    "transaction_id": "txn-1001",
    "refund_id": "refund-12f18c85",
    "amount": "1000.00",
    "currency": "INR",
    "status": "completed"
  }
}
```

Example generated notification payload:

```json
{
  "channel": "email",
  "recipient": "customer@example.com",
  "message": "Your refund of 1000.00 INR has been processed."
}
```

### On terminal refund failure

Temporary failures are retried after 2, 4, and 8 seconds. After retries are
exhausted, the refund becomes `dead` and FinQueue internally creates:

```text
webhook_delivery    priority=medium    event=refund.failed
send_notification   priority=low       failure message
```

The failed webhook contains the final `failure_reason`.

Follow-up creation is idempotent per terminal event: at most one webhook and
one notification job are created for each `source_job + source_event` pair.

## Direct webhook/notification submission

The API still accepts these job types directly for isolated testing, but the
normal business flow creates them automatically from a terminal refund.

### Webhook test

```json
{
  "job_type": "webhook_delivery",
  "payload": {
    "url": "https://merchant.example/webhooks",
    "event": "refund.completed",
    "data": {
      "refund_id": "refund-123"
    }
  }
}
```

### Notification test

```json
{
  "job_type": "send_notification",
  "payload": {
    "channel": "email",
    "recipient": "customer@example.com",
    "message": "Your refund has been processed."
  }
}
```

## Simulate provider failure

Add `simulate_failure: true` to a valid handler payload to exercise retry and
DLQ behavior.

For example, to force the refund itself to fail on every attempt:

```json
{
  "job_type": "refund_processing",
  "payload": {
    "transaction_id": "txn-1001",
    "amount": "1000.00",
    "currency": "INR",
    "webhook_url": "https://merchant.example/webhooks",
    "notification": {
      "channel": "email",
      "recipient": "customer@example.com"
    },
    "simulate_failure": true
  }
}
```

After the final retry fails, the refund becomes `dead`, then its
`refund.failed` webhook and failure notification are queued.

## List jobs

```http
GET {{base_url}}/jobs/
Authorization: Bearer {{access_token}}
```

Optional filters:

```text
/jobs/?status=pending
/jobs/?job_type=refund_processing
/jobs/?status=completed&job_type=webhook_delivery
```

The current configuration does not enable pagination, so the response is a JSON
array.

## Retrieve a job

```http
GET {{base_url}}/jobs/{{job_id}}/
Authorization: Bearer {{access_token}}
```

Follow-up jobs include the original refund UUID in `source_job` and the
triggering terminal event in `source_event`.

Example completed refund:

```json
{
  "id": "12f18c85-b610-4bf6-9fd9-1b5a9c645e78",
  "source_job": null,
  "job_type": "refund_processing",
  "priority": "high",
  "status": "completed",
  "payload": {
    "transaction_id": "txn-1001",
    "amount": "1000.00",
    "currency": "INR",
    "webhook_url": "https://merchant.example/webhooks",
    "notification": {
      "channel": "email",
      "recipient": "customer@example.com"
    }
  },
  "retry_count": 0,
  "result": {
    "refund_id": "refund-12f18c85",
    "transaction_id": "txn-1001",
    "status": "REFUNDED",
    "amount": "1000.00",
    "currency": "INR"
  },
  "failure_reason": null
}
```

## Cancel a pending job

```http
DELETE {{base_url}}/jobs/{{job_id}}/
Authorization: Bearer {{access_token}}
```

Only pending jobs can be deleted. A successful deletion returns `204 No Content`.

## Worker behavior

Run the worker in another terminal:

```powershell
python .\worker.py
```

The worker:

1. Promotes due retry jobs into the main Redis queue.
2. Pops one job with the lowest score (high before medium before low).
3. Marks it running and dispatches the matching handler.
4. Marks success as completed.
5. Retries temporary failures with exponential backoff.
6. Moves a job to the DLQ after its final failed attempt.
7. If the terminal job is a refund, creates webhook + notification follow-ups.

Webhook or notification terminal states do not create additional follow-ups.

## Dead-letter queue

These endpoints require a staff/superuser account.

```http
GET {{base_url}}/dlq/
Authorization: Bearer {{admin_access_token}}
```

Requeue an entry:

```http
POST {{base_url}}/dlq/{{dlq_id}}/requeue/
Authorization: Bearer {{admin_access_token}}
```

## Metrics

All metrics are scoped to the authenticated user.

### Summary

```http
GET {{base_url}}/metrics/summary/
Authorization: Bearer {{access_token}}
```

### Counts by job type

```http
GET {{base_url}}/metrics/job-types/
Authorization: Bearer {{access_token}}
```

### Failure rate

```http
GET {{base_url}}/metrics/failure-rate/
Authorization: Bearer {{access_token}}
```

Terminal worker failures use the `dead` status. The failure-rate endpoint counts
both `failed` and `dead` statuses.
