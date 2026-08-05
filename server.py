#!/usr/bin/env python3
"""
server.py -- one-command bootstrap for testing learn-git locally.

Handles everything docker-compose.yml assumes is already done by hand:
  - creates .env from .env.example if missing, with a real random SECRET_KEY
  - creates the students-data/ directory and fills in STUDENTS_HOST_PATH
    with its actual absolute path (the #1 recurring setup mistake)
  - builds the workspace image (needed before api can spin up students)
  - brings the whole stack up

This is meant for local/testing use. For a real deployment (EC2, a real
domain, HTTPS), follow DEPLOYMENT.md instead -- this script does not set
up TLS, doesn't harden any secrets, and assumes you're fine with the
defaults in .env.example.

Usage:
    python3 server.py            # bootstrap + start everything
    python3 server.py --down     # stop everything (docker compose down)
    python3 server.py --logs     # tail logs after starting
"""
import os
import secrets
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(REPO_ROOT, ".env")
ENV_EXAMPLE_PATH = os.path.join(REPO_ROOT, ".env.example")
STUDENTS_DATA_DIR = os.path.join(REPO_ROOT, "students-data")


def run(cmd, **kwargs):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, **kwargs)
    if result.returncode != 0:
        print(f"\nCommand failed (exit {result.returncode}): {' '.join(cmd)}")
        sys.exit(result.returncode)
    return result


def check_docker():
    if shutil.which("docker") is None:
        print("Docker isn't installed or isn't on PATH. Install Docker first.")
        sys.exit(1)
    result = subprocess.run(["docker", "info"], capture_output=True)
    if result.returncode != 0:
        print("Docker is installed but the daemon isn't running (or you lack permission).")
        print("Try: sudo systemctl start docker   (and make sure your user is in the docker group)")
        sys.exit(1)


def ensure_env():
    if os.path.exists(ENV_PATH):
        print(f".env already exists at {ENV_PATH} -- leaving it alone.")
        return

    if not os.path.exists(ENV_EXAMPLE_PATH):
        print(f"Can't find {ENV_EXAMPLE_PATH} -- is this script in the repo root?")
        sys.exit(1)

    print("No .env found -- creating one for local testing...")
    with open(ENV_EXAMPLE_PATH) as f:
        content = f.read()

    secret_key = secrets.token_hex(32)
    content = content.replace(
        "STUDENTS_HOST_PATH=/absolute/path/to/learn-git/students-data",
        f"STUDENTS_HOST_PATH={STUDENTS_DATA_DIR}",
    )
    content = content.replace(
        "SECRET_KEY=change-me-to-a-long-random-string",
        f"SECRET_KEY={secret_key}",
    )

    with open(ENV_PATH, "w") as f:
        f.write(content)

    print(f"Created .env with STUDENTS_HOST_PATH={STUDENTS_DATA_DIR} and a fresh random SECRET_KEY.")
    print("Edit .env afterward if you want to set ADMIN_REG_NOS or change anything else.")


def ensure_students_dir():
    os.makedirs(STUDENTS_DATA_DIR, exist_ok=True)
    print(f"students-data directory ready at {STUDENTS_DATA_DIR}")


def main():
    args = sys.argv[1:]

    if "--down" in args:
        run(["docker", "compose", "down"])
        return

    check_docker()
    ensure_env()
    ensure_students_dir()

    print("\nBuilding the per-student workspace image...")
    run(["docker", "compose", "build", "workspace-image"])

    print("\nBuilding and starting the rest of the stack...")
    run(["docker", "compose", "up", "-d", "--build"])

    print("\n" + "=" * 60)
    print("learn-git is starting up.")
    print("Dashboard: http://localhost:8080")
    print("=" * 60)

    if "--logs" in args:
        subprocess.run(["docker", "compose", "logs", "-f"], cwd=REPO_ROOT)


if __name__ == "__main__":
    main()
