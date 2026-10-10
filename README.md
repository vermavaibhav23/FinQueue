# FinQueue

FinQueue is an asynchronous job-processing simulation built with Django,
Django REST Framework, MySQL, and Redis.

The project focuses on queueing, priorities, retries, dead-letter handling, and
decoupling follow-up work from the main business operation.

It demonstrates:

- JWT-based registration, login, and logout
- Redis-backed priority queues
- Server-assigned job priorities
- Exponential retry scheduling
- Dead-letter queue handling
- Automatic follow-up jobs after a refund reaches a terminal state
- Simulated webhook delivery and user notifications
- Per-user operational metrics
- Submission rate limiting
- Merchant API idempotency using `Idempotency-Key` + request hash
- Separate stale-job recovery process for RUNNING jobs older than 30 seconds
- Stable external operation/event IDs for retry-safe downstream calls

## Persistent tables

The active design intentionally keeps persistence small:

- `jobs` — asynchronous job state plus Layer 1 submission idempotency metadata
- `dead_letter_queue` — jobs that exhausted retries

The old `transactions` model/table was removed because it duplicated information
already available in the job workflow and was not used by the current handlers.

## Job types and priority policy

| Job type | Priority | Purpose |
| --- | --- | --- |
| `refund_processing` | High | Main business operation: simulate returning money |
| `webhook_delivery` | Medium | Reliably tell an external merchant backend what happened |
| `send_notification` | Low | Inform a human through email, SMS, or push |

Priority is derived by the server from `job_type`; clients cannot escalate
their own work by sending a higher priority.

## Idempotency layers

FinQueue now demonstrates all three idempotency layers discussed in the design:

1. **Merchant/API submission idempotency** — every external job submission must
   include an `Idempotency-Key`. FinQueue stores `idempotency_key` and the
   SHA-256 `request_hash` directly on the submitted `jobs` row, with
   `UNIQUE(user, idempotency_key)`. The same key and same payload return the
   existing job; the same key with a different payload returns `409 Conflict`.
   Internally generated follow-up jobs leave these fields `NULL`.
2. **Follow-up job creation idempotency** — internally generated webhook and
   notification jobs are protected by
   `UNIQUE(source_job, job_type, source_event)`.
3. **External side-effect idempotency** — every retry of the same logical
   external action reuses a stable ID:
   - refund provider call: `Idempotency-Key: refund:<job_uuid>`
   - webhook delivery: `event_id = webhook:refund.completed:<source_job_uuid>`
     (or `webhook:refund.failed:<source_job_uuid>`)
   - notification delivery:
     `notification_id = notification:<event>:<source_job_uuid>`

Layer 3 is cooperative: FinQueue guarantees that it sends the **same stable ID**
on every retry, but the payment gateway, merchant webhook receiver, or
notification provider must store/check that ID and avoid applying the same side
effect twice. Because the external providers are simulated in this project,
the code demonstrates FinQueue's side of that contract rather than pretending
the local database can guarantee exactly-once behavior in another system.

## Main asynchronous flow

The normal flow starts with **one refund job**. The merchant does not need to
submit webhook and notification jobs separately.

```text
Merchant/API client
        |
        | POST /jobs/submit/
        | Idempotency-Key: <merchant-generated-key>
        v
refund_processing (HIGH)
        |
        v
Redis priority queue
        |
        v
Worker
        |
        +-------------------- success --------------------+
        |                                                 |
        |                                           refund COMPLETED
        |                                                 |
        |                             +-------------------+-------------------+
        |                             |                                       |
        |                             v                                       v
        |                    webhook_delivery                         send_notification
        |                       (MEDIUM)                                  (LOW)
        |                             |                                       |
        |                             +--------------> Redis <----------------+
        |
        +---- temporary failure -> retry 2s -> 4s -> 8s
                                      |
                                      v
                              retries exhausted
                                      |
                                      v
                                 refund DEAD
                                      |
                    +-----------------+------------------+
                    |                                    |
                    v                                    v
            refund.failed webhook              failure notification
               (MEDIUM)                              (LOW)
```

Only `refund_processing` creates these follow-up jobs. Completing or failing a
webhook/notification job does **not** create more jobs, so there is no recursive
chain.

## Why webhook delivery is a job

A webhook is not an update to FinQueue's own database. It is an outbound HTTP
call to a different system, for example the merchant's backend:

```text
FinQueue -> POST https://merchant.example/webhooks -> Merchant backend
```

The merchant can then update its own refund/order state. Because that external
server can be slow, unavailable, or return a 5xx response, webhook delivery is
decoupled into its own retryable background job.

A notification is different: it is system-to-human communication such as email,
SMS, or push.

## Terminal refund events

When a refund completes:

- a medium-priority webhook job is created with event `refund.completed`
- a low-priority notification job is created for the customer

When a refund exhausts all retries and becomes `dead`:

- a medium-priority webhook job is created with event `refund.failed`
- a low-priority failure notification job is created

The refund status is never rolled back because a webhook or notification later
fails.

Follow-up jobs store both `source_job` and `source_event` (for example,
`refund.completed` or `refund.failed`). A database uniqueness constraint
allows at most one webhook and one notification per source event, making
follow-up creation idempotent while still allowing a requeued failed refund to
later emit a separate success event.

## Demo routing data

To keep this educational project focused on asynchronous processing rather than
merchant/customer domain modeling, the initial refund payload also carries the
routing data needed for its later side effects:

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

In a production system, the webhook URL would normally be loaded from merchant
configuration and customer contact details from stored transaction/customer
data instead of being repeated in every refund request.

## Architecture

MySQL is the durable source of truth for job state. Redis sorted sets provide
the main priority queue and retry queue.

```text
Client -> Django REST API -> MySQL
                    |
                    +------> Redis main queue
                                  |
                               Worker
                                  |
                    refund / webhook / notification
                                  |
                   completed / retry / dead-letter
```

Job submission returns `202 Accepted` because the API accepts and queues the
work while the worker completes it asynchronously. The submit response is kept
minimal: `id`, current `status`, and `idempotent_replay`.

Worker `result` JSON is also kept focused on the actual outcome:
- refund: refund ID, transaction ID, refund status, amount, currency
- webhook: `webhook_delivery_status` and HTTP status
- notification: `notification_status` and channel

Stable Layer 3 idempotency/event IDs are used for the outbound external call
but are not duplicated inside the final `result` JSON.

## Worker crash recovery

A normal worker does not resume from the exact Python instruction where it
crashed. If a worker dies after changing a job to `RUNNING`, that job would
otherwise remain stuck forever.

For this educational version, a separate recovery process uses a simple
30-second stale threshold:

```text
status = RUNNING
started_at older than 30 seconds
        |
        v
treat as stale
        |
        v
RUNNING -> PENDING
        |
        v
re-enqueue the same job ID in Redis
```

The recovered job keeps its original `started_at`, so FinQueue still knows it
was attempted before. This matters because the external operation may already
have succeeded immediately before the worker crashed.

That creates the classic uncertainty window:

```text
external system processes request successfully
        |
worker crashes before saving COMPLETED
        |
FinQueue cannot know the external outcome with certainty
        |
30-second stale recovery retries the same job
        |
same stable external idempotency/event ID is sent again
```

Layer 3 idempotency therefore makes stale-job retries safe at the downstream
service. A lease + heartbeat mechanism would be a stronger production
enhancement because it avoids incorrectly reclaiming a legitimately long-running
healthy job; it is intentionally not implemented in the current version.

## Failure simulation

Provider calls are simulated so the project runs without real payment, webhook,
email, or SMS providers. The dummy handlers now use Python's `random` module
to occasionally fail by default:

- refund provider: 20% simulated failure rate
- webhook endpoint: 15% simulated failure rate
- notification provider: 10% simulated failure rate

This lets retries, exponential backoff, and DLQ behavior happen naturally during
a demo. For a deterministic forced-failure test, add:

```json
{
  "simulate_failure": true
}
```

inside a valid job payload.

## Local setup

Start MySQL and Redis, create a MySQL database named `finqueue`, and set:

```powershell
$env:MYSQL_HOST = '127.0.0.1'
$env:MYSQL_PORT = '3306'
$env:MYSQL_DATABASE = 'finqueue'
$env:MYSQL_USER = 'root'
$env:MYSQL_PASSWORD = 'your_password'
$env:REDIS_URL = 'redis://127.0.0.1:6379/0'
```

Apply migrations and start the API:

```powershell
python .\manage.py migrate
python .\manage.py runserver
```

In another terminal, set the same environment variables and start the normal
job worker:

```powershell
python .\worker.py
```

Start the stale-job recovery process in a third terminal:

```powershell
python .\recovery_worker.py
```

By default, the recovery process treats a RUNNING job as stale after 30 seconds
and scans every 5 seconds. These values can be changed with
`FINQUEUE_STALE_RUNNING_SECONDS` and `FINQUEUE_RECOVERY_POLL_SECONDS`.

Alternatively, start MySQL and Redis with Docker Desktop:

```powershell
docker compose up -d
```

The Compose file starts the infrastructure only; Django and the worker still run
with the commands above.

## API endpoints

- `POST /auth/register/`
- `POST /auth/login/`
- `POST /auth/logout/`
- `POST /jobs/submit/`
- `GET /jobs/`
- `GET /jobs/<job_id>/`
- `DELETE /jobs/<job_id>/` (only a never-started pending job)
- `GET /dlq/` (admin only)
- `POST /dlq/<dlq_id>/requeue/` (admin only)
- `GET /metrics/summary/`
- `GET /metrics/job-types/`
- `GET /metrics/failure-rate/`

See [POSTMAN.md](POSTMAN.md) for request and response examples.

## Tests

```powershell
python .\manage.py test --settings=finqueue.test_settings
```

## Project scope

FinQueue is an educational simulation. Each worker process handles one job at
a time and external providers are simulated. Multiple worker processes can be
run for concurrent job processing. A production deployment would normally add
managed worker supervision, stronger outbox/reconciliation patterns, webhook
signatures, real provider integrations that honor the stable idempotency IDs,
and richer merchant/customer models. A lease + heartbeat worker-ownership
mechanism is also a future enhancement beyond the current fixed 30-second
stale threshold.
