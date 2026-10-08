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

Valid job types and server-assigned priorities are:

- `refund_processing` -> high
- `webhook_delivery` -> medium
- `send_notification` -> low

The client does **not** choose priority. If a `priority` field is supplied, it
is ignored because priority is a server-side business rule.

### Submit a refund-processing job

```http
POST {{base_url}}/jobs/submit/
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

```json
{
  "job_type": "refund_processing",
  "payload": {
    "transaction_id": "txn-1001",
    "amount": "1000.00",
    "currency": "INR"
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
  "created_at": "2026-10-08T10:00:00Z"
}
```

The API has accepted and queued the work; completion happens later in the
background worker. Submission is limited to 10 jobs per user per 60 seconds by
default.

### Submit a webhook-delivery job

A webhook is system-to-system communication. The destination is another backend,
not a human recipient.

```http
POST {{base_url}}/jobs/submit/
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

```json
{
  "job_type": "webhook_delivery",
  "payload": {
    "url": "https://merchant.example/webhooks",
    "event": "refund.completed",
    "data": {
      "transaction_id": "txn-1001",
      "refund_id": "refund-123",
      "amount": "1000.00"
    }
  }
}
```

### Submit a notification job

A notification is system-to-human communication such as email, SMS, or push.

```http
POST {{base_url}}/jobs/submit/
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

```json
{
  "job_type": "send_notification",
  "payload": {
    "channel": "email",
    "recipient": "customer@example.com",
    "message": "Your refund of Rs.1000 has been processed."
  }
}
```

### Simulate a temporary provider failure

Any valid handler payload can include:

```json
{
  "simulate_failure": true
}
```

For example, a failing webhook job raises a simulated temporary 5xx error. The
worker retries it with exponential backoff and eventually moves it to the DLQ if
all attempts fail.

### List the current user's jobs

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

### Retrieve a job

```http
GET {{base_url}}/jobs/{{job_id}}/
Authorization: Bearer {{access_token}}
```

Example completed refund response:

```json
{
  "id": "12f18c85-b610-4bf6-9fd9-1b5a9c645e78",
  "job_type": "refund_processing",
  "priority": "high",
  "status": "completed",
  "payload": {
    "transaction_id": "txn-1001",
    "amount": "1000.00",
    "currency": "INR"
  },
  "retry_count": 0,
  "result": {
    "refund_id": "refund-12f18c85",
    "transaction_id": "txn-1001",
    "status": "REFUNDED",
    "amount": "1000.00",
    "currency": "INR"
  },
  "failure_reason": null,
  "created_at": "2026-10-08T10:00:00Z",
  "updated_at": "2026-10-08T10:00:01Z",
  "started_at": "2026-10-08T10:00:00Z",
  "completed_at": "2026-10-08T10:00:01Z"
}
```

### Cancel a pending job

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
2. Pops one job with the lowest priority score (high before medium before low).
3. Marks it as running and dispatches the correct handler.
4. Marks successful work as completed.
5. On an exception, schedules retries after 2, 4, and 8 seconds.
6. Moves the job to the dead-letter queue after the final failed attempt.

Provider calls are simulated so the project remains self-contained.

## Dead-letter queue

These endpoints require a staff/superuser account.

### List DLQ entries

```http
GET {{base_url}}/dlq/
Authorization: Bearer {{admin_access_token}}
```

### Requeue an entry

```http
POST {{base_url}}/dlq/{{dlq_id}}/requeue/
Authorization: Bearer {{admin_access_token}}
```

This resets the original job to pending, clears its execution state, and adds it
to the main Redis queue.

## Metrics

All metrics are scoped to the authenticated user.

### Summary

```http
GET {{base_url}}/metrics/summary/
Authorization: Bearer {{access_token}}
```

```json
{
  "total_jobs": 5,
  "pending": 1,
  "running": 0,
  "completed": 3,
  "failed": 0,
  "dead": 1
}
```

### Counts by job type

```http
GET {{base_url}}/metrics/job-types/
Authorization: Bearer {{access_token}}
```

```json
{
  "job_types": [
    {
      "job_type": "refund_processing",
      "total": 2
    },
    {
      "job_type": "webhook_delivery",
      "total": 2
    },
    {
      "job_type": "send_notification",
      "total": 1
    }
  ]
}
```

### Failure rate

```http
GET {{base_url}}/metrics/failure-rate/
Authorization: Bearer {{access_token}}
```

```json
{
  "total_jobs": 5,
  "failed_jobs": 1,
  "failure_rate_percent": 20.0
}
```

In the current implementation, terminal worker failures use the `dead` status.
The failure-rate endpoint counts both `failed` and `dead` statuses.
