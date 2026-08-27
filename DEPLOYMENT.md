# Deployment Guide

This covers deploying `learn-git` to your own server or an AWS EC2 instance, with a reverse proxy and HTTPS in front of it.

> **Read [SECURITY.md](./SECURITY.md) first.** In particular: the current build uses one shared workspace for all students. This guide gets you a working public deployment, but it is suitable for a single student/demo or a controlled classroom session where only one person uses the terminal at a time — not a large multi-tenant rollout, until per-student workspace isolation is added.

## 1. Prerequisites

- A server (AWS EC2, DigitalOcean droplet, your own machine) with:
  - Docker + Docker Compose plugin installed
  - A public IP or domain name pointed at it
  - Ports 80/443 open (and optionally 22 for SSH)
- A domain name (optional but recommended for HTTPS)

## 2. AWS EC2 setup (if using AWS)

1. Launch an EC2 instance — Ubuntu 24.04 LTS, t3.small or larger (t3.micro can work for a small class but will be tight).
2. Security group inbound rules:
   - `22` (SSH) — from your IP only
   - `80` (HTTP) — from anywhere
   - `443` (HTTPS) — from anywhere
   - Do **not** expose `9418` (git clone/push/pull) publicly unless you specifically want unauthenticated git-over-git-protocol reachable from the internet — most setups should drop this. Everything else (dashboard, API, every student's terminal) only ever goes through the app's own `caddy` container, published on host ports 80/443, so no other app ports need opening.
3. SSH in and install Docker:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-plugin
   sudo systemctl enable --now docker
   sudo usermod -aG docker $USER
   # log out and back in for the group change to apply
   ```
4. Point your domain's DNS A record at the EC2 instance's public IP.

## 3. Build and deploy the app

The app now ships its own `nginx` container that routes the dashboard, API, and every student's isolated terminal — you don't hand-write that config per deployment, it's `caddy/Caddyfile` in the repo.

```bash
git clone <your-repo-url>
cd learn-git
cp .env.example .env
mkdir -p students-data
```

Edit `.env`:
```bash
STUDENTS_HOST_PATH=/absolute/path/to/learn-git/students-data   # REQUIRED -- must be absolute, use `pwd` to get it
SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
ADMIN_REG_NOS=<your reg no, e.g. 21CS045>
CORS_ORIGIN=https://your-domain.com
COOKIE_SECURE=true
```

`STUDENTS_HOST_PATH` must be an **absolute** path, not `./students-data` -- the `api` container talks to the host Docker daemon over a socket, and it resolves bind-mount sources on the host filesystem, not inside any container's own view. Run `pwd` inside `learn-git/` and append `/students-data` to get the right value.

Build the per-student workspace image first (it's not started directly, only used as a template — see `docker-compose.yml`), then bring the stack up:

```bash
docker compose build workspace-image
docker compose up -d --build
```

Confirm it's running: `docker compose ps` — you should see `caddy`, `webapp`, `api`, and `git-server`. Individual `workspace-<reg_no>` containers appear as students log in.

Only `caddy` publishes ports (80/443). `webapp`, `api`, and every `workspace-*` container are reachable only through it — do not add `ports:` to those services in a public deployment.

## 4. Automatic HTTPS with Caddy

The app ships with Caddy as its reverse proxy. Caddy can automatically provision and renew TLS certificates from Let's Encrypt for you.

To enable HTTPS:
1. Open `caddy/Caddyfile`.
2. Change the `:80` at the top to your actual domain name, e.g., `your-domain.com`.
3. Restart Caddy: `docker compose restart caddy`.

Caddy will automatically fetch the certificates and serve everything over HTTPS securely!
## 5. Verify

- `https://your-domain.com` → login page
- Register with your reg no → should land on the dashboard
- Terminal loads and commands validate correctly
- `docker compose down && docker compose up -d` → progress and accounts persist (they're on named volumes)

## 6. Ongoing operations

- **Logs:** `docker compose logs -f api`
- **Backups:** back up the `progress_data` volume regularly — it holds accounts and progress:
  ```bash
  docker run --rm -v learn-git_progress_data:/data -v $(pwd):/backup alpine \
    tar czf /backup/progress-backup-$(date +%F).tar.gz -C /data .
  ```
- **Updating:** `git pull && docker compose up -d --build`
- **Renewing HTTPS:** certbot sets up auto-renewal via a systemd timer/cron — verify with `sudo certbot renew --dry-run`

## 7. Serving many concurrent students

Short version: **you don't need a traditional load balancer for a single-EC2 classroom deployment** — the architecture already dedicates one container per student, so the bottlenecks are elsewhere. Here's what actually matters as your student count grows:

**Instance size is the real constraint.** Each connected student holds a workspace container capped at 256MB RAM / 0.5 vCPU (`workspace_manager.py`). Budget roughly that much per *simultaneously connected* student when picking an instance size — 30 concurrent students could need up to ~7.5GB RAM and use up to 15 vCPU-equivalents under full load. A `t3.large` will struggle well before 20 students; something like `t3.2xlarge` (32GB/8vCPU) or a compute-optimized instance is more realistic for a full classroom session. Size up before the first real class, not after it lags.

**`api` runs under uvicorn** (multiple ASGI worker processes, not a single-threaded dev server) so task-check and dashboard requests don't queue behind each other. Tune worker count via the `WEB_CONCURRENCY` env var if you have more CPU headroom:
```bash
# .env
WEB_CONCURRENCY=8
```

**SQLite runs in WAL mode**, which handles concurrent reads/writes from multiple `api` workers reasonably well for a classroom-scale student count (tens to low hundreds). If you ever outgrow SQLite (very large deployments, many admins/instructors hitting the admin dashboard simultaneously), migrating to Postgres would be the next step — not something to do preemptively.

**When you'd actually want a load balancer:** only if you split this across *multiple hosts* (e.g. running out of RAM/CPU on one EC2 instance, or wanting redundancy). That's a bigger architectural change than this app currently supports out of the box — student containers, the SQLite DB, and the Docker socket access are all tied to a single host right now. If you get to the point of genuinely needing multi-host scaling (hundreds of concurrent students), that's worth a dedicated conversation rather than a quick config tweak — it touches session storage, the DB, and how student containers get scheduled across hosts.

**Practical recommendation for a normal class size (up to a few dozen concurrent students):** one appropriately-sized EC2 instance, the uvicorn changes above, and you're fine without any load balancer.

## 7. Scaling to Hundreds of Students

If your application scales to hundreds of concurrent students, a single Docker daemon might struggle to handle spinning up and managing all the `workspace-image` containers concurrently.

At this scale, you should consider transitioning from a single-host `docker-compose` setup to a container orchestration platform:
*   **Docker Swarm:** A simpler step up, where multiple servers form a swarm and containers are distributed across them automatically.
*   **Kubernetes (K8s):** A more robust (and complex) solution for very large deployments, handling auto-scaling, node failure, and advanced ingress rules.

To migrate to K8s/Swarm, the dynamic container creation in `api/workspace_manager.py` (which currently uses the Docker socket) would need to be updated to talk to the Kubernetes API or Docker Swarm services API instead.

## 8. Secret Management

The application is configured to refuse running with a default or missing `SECRET_KEY` in production to enforce security. 
For a production deployment, do not rely on plain-text `.env` files if possible. Consider using a robust secret manager to inject secrets into your container environment:
*   **AWS Secrets Manager** or **AWS Systems Manager Parameter Store**
*   **HashiCorp Vault**
*   **GitHub Actions Secrets** (for CI/CD deployments)
