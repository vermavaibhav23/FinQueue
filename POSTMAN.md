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

Valid job types are:

- `process_payment`
- `fraud_check`
- `send_notification`

Valid priorities are `high`, `medium`, and `low`. Fraud checks are always forced
to high priority, notifications to low priority, and payments default to medium
when priority is omitted.

### Submit a payment job

```http
POST {{base_url}}/jobs/submit/
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

```json
{
  "job_type": "process_payment",
  "priority": "medium",
  "payload": {
    "amount": "1000.00",
    "merchant": "Demo Store",
    "currency": "INR",
    "device_id": "device-123",
    "location": "Chennai"
  }
}
```

Successful response (`201 Created`):

```json
{
  "id": "12f18c85-b610-4bf6-9fd9-1b5a9c645e78",
  "job_type": "process_payment",
  "priority": "medium",
  "status": "pending",
  "queue_score": 2.1770000000,
  "created_at": "2026-07-06T10:00:00Z"
}
```

The queue score is illustrative and varies with creation time. Submission is
limited to 10 jobs per user per 60 seconds by default.

### Submit a fraud-check job

```http
POST {{base_url}}/jobs/submit/
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

```json
{
  "job_type": "fraud_check",
  "payload": {
    "amount": "75000.00",
    "merchant": "Demo Store",
    "device_id": "new-device",
    "location": "Chennai"
  }
}
```

### Submit a notification job

```http
POST {{base_url}}/jobs/submit/
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

```json
{
  "job_type": "send_notification",
  "payload": {
    "status": "SUCCESS",
    "amount": "1000.00",
    "merchant": "Demo Store",
    "transaction_id": "demo-transaction"
  }
}
```

### List the current user's jobs

```http
GET {{base_url}}/jobs/
Authorization: Bearer {{access_token}}
```

Optional filters:

```text
/jobs/?status=pending
/jobs/?job_type=process_payment
/jobs/?status=completed&job_type=fraud_check
```

The current configuration does not enable pagination, so the response is a JSON
array.

### Retrieve a job

```http
GET {{base_url}}/jobs/{{job_id}}/
Authorization: Bearer {{access_token}}
```

Example response:

```json
{
  "id": "12f18c85-b610-4bf6-9fd9-1b5a9c645e78",
  "job_type": "process_payment",
  "priority": "medium",
  "status": "completed",
  "payload": {
    "amount": "1000.00",
    "merchant": "Demo Store"
  },
  "retry_count": 0,
  "result": {
    "transaction_id": "33661c14-c3f7-4a72-8943-a317f6808423",
    "status": "SUCCESS",
    "amount": "1000.00",
    "merchant": "Demo Store",
    "currency": "INR"
  },
  "failure_reason": null,
  "created_at": "2026-07-06T10:00:00Z",
  "updated_at": "2026-07-06T10:00:02Z",
  "started_at": "2026-07-06T10:00:00Z",
  "completed_at": "2026-07-06T10:00:02Z"
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
2. Pops one job with the lowest priority score.
3. Marks it as running and executes its handler.
4. Marks success as completed.
5. On an exception, schedules retries after 2, 4, and 8 seconds.
6. Moves the job to the dead-letter queue after the final failed attempt.

The payment handler waits two seconds and simulates an 80% success rate.

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
      "job_type": "fraud_check",
      "total": 2
    },
    {
      "job_type": "process_payment",
      "total": 3
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
