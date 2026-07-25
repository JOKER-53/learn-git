"""
learn-git API
- Auth: register/login students by registration number (REG NO) + password
- Serves task list, validates task completion against the student's repo
- Stores progress + accounts in SQLite (persisted via docker volume)
- Admin endpoints for viewing all students' progress
- Spins up an isolated workspace container per student (see workspace_manager.py)
  so concurrent students never share a terminal or a repo.
"""
import json
import logging
import os
import sqlite3
import subprocess
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

import workspace_manager

app = Flask(__name__)
log = logging.getLogger("learn-git")

# SECRET_KEY must be set to a real random value in production (env var).
# Falls back to a dev-only key so local `docker compose up` still works.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)

CORS(app, supports_credentials=True, origins=os.environ.get("CORS_ORIGIN", "*"))

TASKS_PATH = Path(os.environ.get("TASKS_PATH", "/app/tasks/tasks.json"))
# NOTE: DB_PATH deliberately lives outside /data -- /data is the shared
# students-workspace volume mount, and DB_PATH must not collide with it.
DB_PATH = os.environ.get("DB_PATH", "/dbdata/progress.db")

# First reg_no(s) that register are auto-promoted to admin (comma-separated env var).
# e.g. ADMIN_REG_NOS="21CS001,21CS002"
ADMIN_REG_NOS = set(
    r.strip() for r in os.environ.get("ADMIN_REG_NOS", "").split(",") if r.strip()
)

with open(TASKS_PATH) as f:
    TASKS = {t["id"]: t for t in json.load(f)}


def get_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            reg_no TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            user_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            completed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, task_id)
        )
    """)
    conn.commit()
    return conn


def run_git(reg_no, *args):
    """Run a git command inside THIS student's repo, return (ok, stdout)."""
    repo_path = workspace_manager.workspace_repo_path(reg_no)
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def start_workspace_safely(reg_no):
    """Best-effort: don't block login/register if Docker orchestration hiccups."""
    try:
        workspace_manager.ensure_workspace(reg_no)
    except Exception as e:
        log.error("Failed to start workspace for %s: %s", reg_no, e)


# ---- Auth helpers ----

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "reg_no" not in session:
            return jsonify({"error": "not authenticated"}), 401
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "reg_no" not in session:
            return jsonify({"error": "not authenticated"}), 401
        if not session.get("is_admin"):
            return jsonify({"error": "admin only"}), 403
        return f(*args, **kwargs)
    return wrapper


# ---- Validators ----
# All validators take (reg_no, args) so each check runs against the
# correct student's isolated workspace.

def check_repo_exists(reg_no, _args):
    return os.path.isdir(os.path.join(workspace_manager.workspace_repo_path(reg_no), ".git"))


def check_has_commit(reg_no, _args):
    ok, out = run_git(reg_no, "log", "--oneline")
    return ok and len(out) > 0


def check_branch_exists(reg_no, args):
    ok, out = run_git(reg_no, "branch", "--list", args["branch"])
    return ok and args["branch"] in out


def check_current_branch_is(reg_no, args):
    ok, out = run_git(reg_no, "rev-parse", "--abbrev-ref", "HEAD")
    return ok and out == args["branch"]


def check_branch_merged_into(reg_no, args):
    ok, out = run_git(reg_no, "branch", "--merged", args["into"])
    branches = [b.strip().lstrip("* ").strip() for b in out.splitlines()]
    return ok and args["branch"] in branches


def check_stash_not_empty(reg_no, _args):
    ok, out = run_git(reg_no, "stash", "list")
    return ok and len(out) > 0


def check_has_remote(reg_no, args):
    ok, out = run_git(reg_no, "remote")
    return ok and args["remote"] in out.splitlines()


def check_manual_review(reg_no, _args):
    return False


VALIDATORS = {
    "repo_exists": check_repo_exists,
    "has_commit": check_has_commit,
    "branch_exists": check_branch_exists,
    "current_branch_is": check_current_branch_is,
    "branch_merged_into": check_branch_merged_into,
    "stash_not_empty": check_stash_not_empty,
    "has_remote": check_has_remote,
    "manual_review": check_manual_review,
}


# ---- Auth routes ----

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    reg_no = (data.get("reg_no") or "").strip()
    password = data.get("password") or ""

    if not reg_no or not password:
        return jsonify({"error": "reg_no and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400
    if not workspace_manager.is_safe_reg_no(reg_no):
        return jsonify({"error": "reg_no may only contain letters, numbers, - and _"}), 400

    conn = get_db()
    existing = conn.execute("SELECT reg_no FROM users WHERE reg_no = ?", (reg_no,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "account already exists"}), 409

    is_admin = 1 if reg_no in ADMIN_REG_NOS else 0
    conn.execute(
        "INSERT INTO users (reg_no, password_hash, is_admin) VALUES (?, ?, ?)",
        (reg_no, generate_password_hash(password), is_admin)
    )
    conn.commit()
    conn.close()

    session["reg_no"] = reg_no
    session["is_admin"] = bool(is_admin)
    start_workspace_safely(reg_no)
    return jsonify({
        "ok": True, "reg_no": reg_no, "is_admin": bool(is_admin),
        "terminal_path": f"/terminal/{reg_no}/",
    })


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    reg_no = (data.get("reg_no") or "").strip()
    password = data.get("password") or ""

    conn = get_db()
    row = conn.execute(
        "SELECT password_hash, is_admin FROM users WHERE reg_no = ?", (reg_no,)
    ).fetchone()
    conn.close()

    if not row or not check_password_hash(row[0], password):
        return jsonify({"error": "invalid registration number or password"}), 401

    session["reg_no"] = reg_no
    session["is_admin"] = bool(row[1])
    start_workspace_safely(reg_no)
    return jsonify({
        "ok": True, "reg_no": reg_no, "is_admin": bool(row[1]),
        "terminal_path": f"/terminal/{reg_no}/",
    })


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    reg_no = session.get("reg_no")
    session.clear()
    if reg_no:
        try:
            workspace_manager.restart_workspace(reg_no)
        except Exception as e:
            log.error("Failed to restart workspace for %s on logout: %s", reg_no, e)
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def me():
    if "reg_no" not in session:
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "authenticated": True,
        "reg_no": session["reg_no"],
        "is_admin": bool(session.get("is_admin")),
        "terminal_path": f"/terminal/{session['reg_no']}/",
    })


# ---- Task routes (require login) ----

@app.route("/api/tasks")
@login_required
def list_tasks():
    user_id = session["reg_no"]
    conn = get_db()
    done = {row[0] for row in conn.execute(
        "SELECT task_id FROM progress WHERE user_id = ?", (user_id,)
    )}
    conn.close()

    out = []
    for t in sorted(TASKS.values(), key=lambda x: x["order"]):
        out.append({
            **t,
            "completed": t["id"] in done,
            "unlocked": t["prereq"] is None or t["prereq"] in done,
        })
    return jsonify(out)


@app.route("/api/tasks/<task_id>/check", methods=["POST"])
@login_required
def check_task(task_id):
    user_id = session["reg_no"]
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": "unknown task"}), 404

    validator = VALIDATORS.get(task["check"])
    if not validator:
        return jsonify({"error": "no validator"}), 500

    passed = validator(user_id, task.get("check_args", {}))

    if passed:
        conn = get_db()
        conn.execute(
            "INSERT OR IGNORE INTO progress (user_id, task_id) VALUES (?, ?)",
            (user_id, task_id)
        )
        conn.commit()
        conn.close()

    return jsonify({"task_id": task_id, "passed": passed})


# ---- Admin routes ----

@app.route("/api/admin/students")
@admin_required
def admin_students():
    conn = get_db()
    users = conn.execute(
        "SELECT reg_no, is_admin, created_at FROM users ORDER BY created_at"
    ).fetchall()

    total_tasks = len(TASKS)
    out = []
    for reg_no, is_admin, created_at in users:
        done = conn.execute(
            "SELECT task_id, completed_at FROM progress WHERE user_id = ? ORDER BY completed_at",
            (reg_no,)
        ).fetchall()
        last_activity = done[-1][1] if done else None
        out.append({
            "reg_no": reg_no,
            "is_admin": bool(is_admin),
            "created_at": created_at,
            "completed_count": len(done),
            "total_tasks": total_tasks,
            "last_activity": last_activity,
            "completed_tasks": [d[0] for d in done],
        })
    conn.close()
    return jsonify(out)


@app.route("/api/admin/students/<reg_no>", methods=["DELETE"])
@admin_required
def admin_delete_student(reg_no):
    if reg_no == session["reg_no"]:
        return jsonify({"error": "you cannot delete your own account while signed in"}), 400

    conn = get_db()
    existing = conn.execute("SELECT reg_no FROM users WHERE reg_no = ?", (reg_no,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "no such student"}), 404

    conn.execute("DELETE FROM users WHERE reg_no = ?", (reg_no,))
    conn.execute("DELETE FROM progress WHERE user_id = ?", (reg_no,))
    conn.commit()
    conn.close()

    # Best-effort: stop and remove their workspace container too.
    # Their repo files remain on the students_data volume (not auto-deleted,
    # in case of accidental deletion) -- remove manually if you also want
    # the on-disk repo gone.
    try:
        workspace_manager.remove_workspace(reg_no)
    except Exception as e:
        log.error("Failed to remove workspace container for %s: %s", reg_no, e)

    return jsonify({"ok": True, "deleted": reg_no})


@app.route("/api/admin/students/<reg_no>/reset-password", methods=["POST"])
@admin_required
def admin_reset_password(reg_no):
    data = request.get_json(silent=True) or {}
    new_password = data.get("new_password") or ""
    if len(new_password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400

    conn = get_db()
    existing = conn.execute("SELECT reg_no FROM users WHERE reg_no = ?", (reg_no,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "no such student"}), 404

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE reg_no = ?",
        (generate_password_hash(new_password), reg_no)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "reg_no": reg_no})


@app.route("/api/internal/authorize-terminal")
def authorize_terminal():
    """Called by nginx (auth_request) on every /terminal/<reg_no>/ hit.
    Returns 200 only if the requester's own session belongs to that
    student, or the requester is an admin. Never called directly by
    the browser -- nginx marks the matching location `internal`."""
    target_reg_no = request.headers.get("X-Reg-No", "")
    if "reg_no" not in session:
        return "", 401
    if session["reg_no"] == target_reg_no or session.get("is_admin"):
        return "", 200
    return "", 403


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
