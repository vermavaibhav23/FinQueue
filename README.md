# FinQueue

FinQueue is an asynchronous payment job-processing simulation built with Django,
Django REST Framework, MySQL, and Redis.

It demonstrates:

- JWT-based registration, login, and logout
- Redis-backed priority queues
- Exponential retry scheduling
- Dead-letter queue handling
- Simulated payment processing, fraud checks, and notifications
- Per-user operational metrics
- Submission rate limiting

## Architecture

MySQL is the durable source of truth for jobs and transactions. Redis sorted sets
provide the main and retry queues. The standalone worker promotes due retries,
pops the highest-priority job, executes its handler, and saves the outcome in
MySQL.

```text
Client -> Django REST API -> MySQL
                    |
                    +------> Redis main queue
                                  |
                               Worker
                          /         |         \
                     completed   retry queue   DLQ
```

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

FinQueue is an educational simulation. Its worker processes one job at a time and
assumes handlers terminate. A production deployment would normally add multiple
worker processes, hard execution timeouts, atomic job reservation, idempotency,
and recovery for abandoned running jobs.
