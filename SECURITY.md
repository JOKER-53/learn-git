# Security Policy

## Supported Versions

This is an early-stage educational project. Only the latest commit on `main` is supported.

## Reporting a Vulnerability

If you find a security issue (auth bypass, injection, container escape, secrets exposure, etc.), please **do not** open a public GitHub issue.

Instead:
1. Email the maintainer directly (see repo owner's GitHub profile for contact) with a clear description and, if possible, reproduction steps.
2. Allow a reasonable window to investigate and patch before any public disclosure.

## Known Security Considerations (read before deploying publicly)

**Fixed: unauthenticated terminal access (previously present, now closed).** Earlier versions of `nginx.conf` routed `/terminal/<reg_no>/` straight to that student's container with no session check at all — anyone who knew or guessed a valid reg_no could open a live shell into that student's workspace without logging in. This is now closed with an `auth_request` gate: nginx calls `/api/internal/authorize-terminal` on every terminal request, which checks the caller's session cookie actually belongs to that reg_no (or that the caller is an admin) before proxying through. If you forked/copied this project before this fix, rebuild `nginx` and `api` and confirm `nginx.conf` contains an `auth_request` block before deploying.

**Per-student workspace isolation (current state):** each student now gets their own dedicated container (`workspace-<reg_no>`), created on login/registration and reused afterward. Students cannot see or overwrite each other's repos — each writes only to `/data/<reg_no>/repo` on a shared volume, and `nginx` routes `/terminal/<reg_no>/` to that specific container by name. This closes the "shared workspace" gap from earlier versions of this project.

**New tradeoff this introduces: the Docker socket.** To launch per-student containers on demand, the `api` service needs to talk to the Docker daemon, so `docker-compose.yml` mounts `/var/run/docker.sock` into it. This is a significant privilege: **anything that can execute arbitrary code inside the `api` container can control the entire Docker host** (start/stop containers, mount host paths, effectively gain root on the server). Mitigations in place and recommended:
- `api`'s only user input that reaches Docker is `reg_no`, which is strictly validated to `[A-Za-z0-9_-]+` before being used in a container/volume name (`workspace_manager.is_safe_reg_no`) — never pass unsanitized user input anywhere near the Docker API.
- Per-student containers are started with CPU/memory limits (`mem_limit`, `nano_cpus` in `workspace_manager.py`) so one student can't exhaust the host.
- Keep the `api` image's dependencies minimal and patched — a code-execution bug in `api` is now equivalent to a host compromise.
- For a hardened production setup, consider replacing the direct socket mount with a scoped Docker API proxy (e.g. Tecnativa's docker-socket-proxy) that only allows the specific container/volume operations `workspace_manager.py` needs, rather than full daemon access.

Other items before deploying to AWS/a public server:
- Set a strong, random `SECRET_KEY` via `.env` (never use the default dev key in production).
- Set `COOKIE_SECURE=true` and serve everything over HTTPS (see DEPLOYMENT.md).
- Restrict `CORS_ORIGIN` to your actual frontend domain instead of `*`.
- Only `nginx`'s port 80/443 should be publicly reachable — `api`, `webapp`, and student `workspace-*` containers have no published ports and are only reachable through the proxy. Don't add `ports:` to those services when deploying.
- Rate-limit `/api/auth/login` and `/api/auth/register` to reduce brute-force risk (not yet implemented — add at the nginx layer with `limit_req` or in Flask).
- Student containers currently don't auto-expire — long-running idle containers accumulate. Consider a cleanup job that stops workspaces inactive for N days.

## Password Storage

Passwords are hashed with Werkzeug's `generate_password_hash` (PBKDF2) before storage — plaintext passwords are never stored or logged.
