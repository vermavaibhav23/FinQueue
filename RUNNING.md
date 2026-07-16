# Running FinQueue locally

## Prerequisites

- Python 3.13+
- Project dependencies from `requirements.txt`
- MySQL 8
- Redis 7

## Option A: Docker infrastructure

Start Docker Desktop, then start MySQL and Redis:

```powershell
docker compose up -d
```

Configure Django to use those containers:

```powershell
$env:MYSQL_HOST = '127.0.0.1'
$env:MYSQL_PORT = '3306'
$env:MYSQL_DATABASE = 'finqueue'
$env:MYSQL_USER = 'finqueue_user'
$env:MYSQL_PASSWORD = 'finqueue_pass'
$env:REDIS_URL = 'redis://127.0.0.1:6379/0'
```

## Option B: Local MySQL and Redis

Start both services and configure their connection details:

```powershell
$env:MYSQL_HOST = '127.0.0.1'
$env:MYSQL_PORT = '3306'
$env:MYSQL_DATABASE = 'finqueue'
$env:MYSQL_USER = 'root'
$env:MYSQL_PASSWORD = 'your_password'
$env:REDIS_URL = 'redis://127.0.0.1:6379/0'
```

## Start the application

Apply migrations and start Django:

```powershell
python .\manage.py migrate
python .\manage.py runserver
```

Open another terminal, set the same environment variables, and start the worker:

```powershell
python .\worker.py
```

The API is available at `http://127.0.0.1:8000`.

## Run tests

Tests use SQLite and do not require the local MySQL database:

```powershell
python .\manage.py test --settings=finqueue.test_settings
```
