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
   - Do **not** expose `5000`, `7681`, or `9418` publicly — those go through the reverse proxy instead (see step 4).
3. SSH in and install Docker:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-plugin
   sudo systemctl enable --now docker
   sudo usermod -aG docker $USER
   # log out and back in for the group change to apply
   ```
4. Point your domain's DNS A record at the EC2 instance's public IP.

## 3. Deploy the app

```bash
git clone <your-repo-url>
cd learn-git
cp .env.example .env
```

Edit `.env`:
```bash
SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
ADMIN_REG_NOS=<your reg no, e.g. 21CS045>
CORS_ORIGIN=https://your-domain.com
COOKIE_SECURE=true
```

```bash
docker compose up -d --build
```

Confirm it's running: `docker compose ps`

## 4. Put nginx + HTTPS in front of it

Install nginx and certbot on the host (outside Docker, or as another container — host install is simpler to start):

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/learn-git`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_cookie_path / "/; Secure; HttpOnly; SameSite=Lax";
    }

    location /terminal/ {
        proxy_pass http://127.0.0.1:7681/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

Enable it and get a certificate:

```bash
sudo ln -s /etc/nginx/sites-available/learn-git /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.com
```

certbot will rewrite the config to listen on 443 with your cert and auto-renew.

> **Note on the terminal path:** the webapp's `index.html` currently points its iframe/link directly at `http://localhost:7681`. For a real deployment behind nginx, update those references (in `webapp/index.html`) to use `https://your-domain.com/terminal/` instead, so the terminal traffic also goes through your reverse proxy and gets HTTPS/WSS.

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
