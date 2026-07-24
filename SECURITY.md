# Security Policy

## Supported Versions

This is an early-stage educational project. Only the latest commit on `main` is supported.

## Reporting a Vulnerability

If you find a security issue (auth bypass, injection, container escape, secrets exposure, etc.), please **do not** open a public GitHub issue.

Instead:
1. Email the maintainer directly (see repo owner's GitHub profile for contact) with a clear description and, if possible, reproduction steps.
2. Allow a reasonable window to investigate and patch before any public disclosure.

## Known Security Considerations (read before deploying publicly)

This project currently has a **shared single workspace container** for all students — meaning every logged-in user's terminal points at the *same* `/workspace-data/repo` on disk. This is fine for a single-user demo or classroom with one student at a time, but is **not safe for multi-tenant public deployment** yet: students would be able to see and overwrite each other's work, and task validation would be ambiguous across concurrent users.

Before deploying to a shared/public server or AWS with multiple simultaneous students, you should:
- Give each student their own isolated workspace container (or namespaced directory) and update `WORKSPACE_REPO_PATH` resolution in `api/app.py` to be per-user.
- Set a strong, random `SECRET_KEY` via `.env` (never use the default dev key in production).
- Set `COOKIE_SECURE=true` and serve everything over HTTPS.
- Restrict `CORS_ORIGIN` to your actual frontend domain instead of `*`.
- Put the `workspace` terminal (ttyd) behind authentication at the proxy level too — right now anyone with the URL can reach the raw terminal directly on port 7681, bypassing the app's login if that port is publicly exposed.
- Rate-limit `/api/auth/login` and `/api/auth/register` to reduce brute-force risk.
- Review resource limits (CPU/memory) on the workspace container so one student can't exhaust the host.

## Password Storage

Passwords are hashed with Werkzeug's `generate_password_hash` (PBKDF2) before storage — plaintext passwords are never stored or logged.
