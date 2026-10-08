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

## Job types and priority policy

| Job type | Priority | Purpose |
| --- | --- | --- |
| `refund_processing` | High | Main business operation: simulate returning money |
| `webhook_delivery` | Medium | Reliably tell an external merchant backend what happened |
| `send_notification` | Low | Inform a human through email, SMS, or push |

Priority is derived by the server from `job_type`; clients cannot escalate
their own work by sending a higher priority.

## Main asynchronous flow

The normal flow starts with **one refund job**. The merchant does not need to
submit webhook and notification jobs separately.

```text
Merchant/API client
        |
        | POST /jobs/submit/
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

Follow-up jobs store a `source_job` reference to the refund that created them.
A database uniqueness constraint allows at most one webhook and one notification
follow-up per source refund, making follow-up creation idempotent.

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
work while the worker completes it asynchronously.

## Failure simulation

Provider calls are simulated so the project runs without real payment, webhook,
email, or SMS providers. Add:

```json
{
  "simulate_failure": true
}
```

inside a valid job payload to force a temporary handler failure and exercise the
retry/backoff/DLQ flow.

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

In another terminal, set the same environment variables and start the worker:

```powershell
python .\worker.py
```

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
- `DELETE /jobs/<job_id>/`
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

FinQueue is an educational simulation. Its worker processes one job at a time
and external providers are simulated. A production deployment would normally
add multiple workers, hard execution timeouts, atomic reservation/outbox
patterns, request idempotency, webhook signatures, real provider integrations,
and richer merchant/customer models.
