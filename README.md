# FinQueue

FinQueue is an asynchronous job-processing simulation built with Django,
Django REST Framework, MySQL, and Redis.

It demonstrates:

- JWT-based registration, login, and logout
- Redis-backed priority queues
- Server-assigned job priorities
- Exponential retry scheduling
- Dead-letter queue handling
- Simulated refund processing, webhook delivery, and user notifications
- Per-user operational metrics
- Submission rate limiting

## Job types and priority policy

FinQueue supports three asynchronous job types:

| Job type | Priority | Purpose |
| --- | --- | --- |
| `refund_processing` | High | Simulates returning money through a payment provider |
| `webhook_delivery` | Medium | Simulates system-to-system HTTP event delivery |
| `send_notification` | Low | Simulates email, SMS, or push communication to a person |

Priority is derived by the server from `job_type`; clients cannot escalate their
own work by supplying a higher priority.

## Architecture

MySQL is the durable source of truth for jobs. Redis sorted sets provide the
main priority queue and retry queue. The standalone worker promotes due retries,
pops the highest-priority job, dispatches it to the appropriate handler, and
stores the outcome in MySQL.

```text
Client -> Django REST API -> MySQL
                    |
                    +------> Redis main queue
                                  |
                               Worker
                    /              |               \
          refund handler    webhook handler    notification handler
                    \              |               /
                     +------ completed / retry ------+
                                      |
                                     DLQ
```

Job submission returns `202 Accepted` because the API accepts and queues the
work while the worker completes it asynchronously.

## Failure simulation

Handlers are intentionally self-contained so the project can run without real
payment, webhook, email, or SMS providers. Add:

```json
{
  "simulate_failure": true
}
```

inside a valid job payload to simulate a temporary provider failure. The worker
then exercises the normal retry, exponential-backoff, and DLQ flow.

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
and the provider calls are simulated. A production deployment would normally add
multiple worker processes, hard execution timeouts, atomic job reservation,
idempotency, provider-specific security such as webhook signatures, and recovery
for abandoned running jobs.
