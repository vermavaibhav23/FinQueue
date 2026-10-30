# Deploy FinQueue on Oracle Cloud Always Free

This deployment runs the existing Django API, MySQL, Redis, job worker, recovery worker, and Caddy on one Oracle VM. It does not include a React frontend; this repository currently contains only the backend API.

## 1. Create the VM

In Oracle Cloud, create an **Always Free eligible** VM.Standard.A1.Flex instance in your home region with Ubuntu 24.04 LTS. Choose a size within the Always Free allowance (for example, 2 OCPUs and 12 GB RAM). Give it a public IPv4 address and add your SSH public key. Oracle may report that the A1 shape is out of capacity in your region; try another availability domain or later.

Create VCN ingress rules for TCP ports **80** and **443** from the internet. Restrict port **22** to your own IP if possible. Do not expose MySQL port 3306 or Redis port 6379. If Ubuntu's local firewall is enabled, allow 80 and 443 there too.

Point a hostname at the VM's public IP. A domain you own works; a free DuckDNS subdomain also works. The hostname is required for Caddy to obtain a public HTTPS certificate.

## 2. Install Docker and get the code

SSH to the VM as `ubuntu`. Install Docker Engine and the Compose plugin using [Docker's official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/); the Ubuntu image for A1 is Arm64, which Docker supports. Confirm `sudo docker compose version` works.

```sh
git clone https://github.com/vermavaibhav23/FinQueue.git
cd FinQueue
git fetch origin codex/railway-deployment
git checkout codex/railway-deployment
cp .env.oracle.example .env.oracle
```

Edit `.env.oracle`: set `SITE_ADDRESS` and `DJANGO_ALLOWED_HOSTS` to the hostname that points to the VM; generate a unique `DJANGO_SECRET_KEY`, `MYSQL_PASSWORD`, and `MYSQL_ROOT_PASSWORD`. Keep `DJANGO_DEBUG=False`. The file is gitignored and should never be committed. Set permissions with `chmod 600 .env.oracle`.

## 3. Start and verify

```sh
sudo docker compose --env-file .env.oracle -f compose.oracle.yml config
sudo docker compose --env-file .env.oracle -f compose.oracle.yml up -d --build
sudo docker compose --env-file .env.oracle -f compose.oracle.yml ps
sudo docker compose --env-file .env.oracle -f compose.oracle.yml logs --tail=100 api worker recovery caddy
```

The API waits for healthy MySQL and Redis; its start script applies migrations, collects static files, and starts Gunicorn. Caddy obtains and renews the HTTPS certificate. Wait until DNS resolves and open `https://<your-hostname>/health/`; it should return `{"status":"ok"}`.

Run the Django deployment checks:

```sh
sudo docker compose --env-file .env.oracle -f compose.oracle.yml exec api python manage.py check --deploy
```

Create a test account via `/auth/register/`, submit a synthetic refund to `/jobs/submit/` with an `Idempotency-Key`, and confirm its status advances while the worker runs. Check `/jobs/`, `/metrics/`, and the logs. Repeat the submission with the same key to check the idempotent replay. Keep demo data synthetic.

## Operations

To deploy updates after merging the PR:

```sh
git checkout main
git pull --ff-only
sudo docker compose --env-file .env.oracle -f compose.oracle.yml up -d --build
```

Named volumes keep MySQL, Redis, and Caddy certificate state across container replacements. Back up the MySQL volume or database before risky changes; a VM and its volumes are a single point of failure. Keep Ubuntu and container images updated. Never run `docker compose down -v` unless you intend to erase the database and Redis volumes.

Only share the demo URL on your resume after the React interface and an end-to-end public demo are working. For now this deployment is an API demo.

References: [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [Oracle security rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm), [Docker Ubuntu install](https://docs.docker.com/engine/install/ubuntu/), [Caddy HTTPS](https://caddyserver.com/docs/automatic-https).
