# Deploy FinQueue on Railway

FinQueue needs five running services: Django API, MySQL, Redis, job worker, and stale-job recovery worker. The current repository has no React frontend, so this deployment exposes the API; add the frontend as a separate service once it exists.

## 1. Create the project

Create a Railway project linked to this GitHub repository and branch. Add MySQL and Redis database services. Keep both databases private.

Create three services from the same GitHub repository, each using the root `Dockerfile`:

| Service | Start command | Public domain |
| --- | --- | --- |
| API | `sh deploy/web.sh` | Yes |
| Worker | `sh deploy/worker.sh` | No |
| Recovery | `sh deploy/recovery.sh` | No |

Use one instance of Worker and one instance of Recovery initially. In the API service settings, set the health check path to `/health/`. The API start command applies migrations and collects static files before accepting traffic.

## 2. Configure variables

Set these variables on **all three** app services, using Railway variable references for database credentials:

```text
DJANGO_SECRET_KEY=<generate a long random secret>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<api-domain>.up.railway.app,healthcheck.railway.app
MYSQL_DATABASE=${{MySQL.MYSQLDATABASE}}
MYSQL_USER=${{MySQL.MYSQLUSER}}
MYSQL_PASSWORD=${{MySQL.MYSQLPASSWORD}}
MYSQL_HOST=${{MySQL.MYSQLHOST}}
MYSQL_PORT=${{MySQL.MYSQLPORT}}
REDIS_URL=${{Redis.REDIS_URL}}
```

Replace `MySQL` and `Redis` with the actual service names if different. Add your custom API domain to `DJANGO_ALLOWED_HOSTS` if you use one. Add `FRONTEND_ORIGINS=https://<your-frontend-domain>` to the API when the React frontend exists. Do not put secrets in the React build.

## 3. Verify

Open `https://<api-domain>/health/` and expect `{"status":"ok"}`. Run `python manage.py check --deploy` with production variables in the API service. Register a demo account, submit a refund job with an `Idempotency-Key`, and verify that the worker moves it through the queue. Check worker and recovery logs and the jobs/history API. Test a duplicate submission with the same key to show idempotency.

Use only synthetic demo transactions and recipient data. Put the public demo URL and GitHub repository link at the top of the README and on the resume once the end-to-end demo works.

Railway references: [MySQL](https://docs.railway.com/databases/mysql), [Redis](https://docs.railway.com/databases/redis), [multiple services from one repository](https://docs.railway.com/deployments/monorepo), [health checks](https://docs.railway.com/deployments/healthchecks).
