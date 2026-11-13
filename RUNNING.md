# Running FinQueue locally

## Prerequisites

- Python 3.13+
- Project dependencies from `requirements.txt`
- MySQL 8
- Redis 7
- Node.js 20.19+ and npm (for the React frontend)

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

Open a third terminal with the same environment variables to start stale-job recovery:

```powershell
python .\recovery_worker.py
```

In a fourth terminal, start the React frontend:

```powershell
cd .\frontend
npm install
npm run dev
```

Open `http://localhost:5173` for the application. Vite forwards `/api/*` to
the Django API at `http://127.0.0.1:8000`, so no CORS setup is needed locally.
Register an account, submit a sample refund, and watch its status update.
The dead-letter view is available only to Django staff users.

The API is available at `http://127.0.0.1:8000`. The React frontend only stores
the login session in the current browser tab and renews access tokens through
`/auth/refresh/`.

## Run tests

Tests use SQLite and do not require the local MySQL database:

```powershell
python .\manage.py test --settings=finqueue.test_settings
```

Frontend checks:

```powershell
cd .\frontend
npm run lint
npm run build
```

