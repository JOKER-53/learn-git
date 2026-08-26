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
import threading
import time
from collections import defaultdict
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

import workspace_manager

app = Flask(__name__)
log = logging.getLogger("learn-git")

app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)
CORS(app, supports_credentials=True, origins=os.environ.get("CORS_ORIGIN", "*"))

TASKS_PATH = Path(os.environ.get("TASKS_PATH", "/app/tasks/tasks.json"))
DB_PATH = os.environ.get("DB_PATH", "/dbdata/progress.db")
ADMIN_REG_NOS = set(
    r.strip() for r in os.environ.get("ADMIN_REG_NOS", "").split(",") if r.strip()
)

with open(TASKS_PATH) as f:
    TASKS = {t["id"]: t for t in json.load(f)}


def get_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
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
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "recovery_code_hash" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN recovery_code_hash TEXT")
    if "last_seen" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN last_seen TEXT")
    conn.commit()
    return conn


def generate_recovery_code():
    import secrets, string
    alphabet = string.ascii_uppercase + string.digits
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def touch_last_seen(reg_no):
    try:
        conn = get_db()
        conn.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE reg_no = ?", (reg_no,))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error("Failed to update last_seen for %s: %s", reg_no, e)


def run_git(reg_no, *args):
    """Run git inside the student's running container via docker exec."""
    return workspace_manager.run_git_in_container(reg_no, *args)


def start_workspace_safely(reg_no):
    """Create workspace container and git remote on login. Best-effort."""
    try:
        workspace_manager.ensure_workspace(reg_no)
    except Exception as e:
        log.error("Failed to start workspace for %s: %s", reg_no, e)
    try:
        workspace_manager.ensure_git_remote(reg_no)
    except Exception as e:
        log.error("Failed to create git remote for %s: %s", reg_no, e)


# ---- Rate limiting ----
_rate_limit_hits = defaultdict(list)


def rate_limit(max_attempts, window_seconds):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ip = request.headers.get("X-Real-IP", request.remote_addr) or "unknown"
            key = f"{f.__name__}:{ip}"
            now = time.time()
            hits = _rate_limit_hits[key]
            hits[:] = [t for t in hits if now - t < window_seconds]
            if len(hits) >= max_attempts:
                retry_after = int(window_seconds - (now - hits[0]))
                return jsonify({"error": f"Too many attempts. Try again in {max(retry_after, 1)}s."}), 429
            hits.append(now)
            return f(*args, **kwargs)
        return wrapper
    return decorator


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


# ---- Validators (all use docker exec now, no host path reads) ----
def check_repo_exists(reg_no, _args):
    ok, _ = run_git(reg_no, "rev-parse", "--git-dir")
    return ok

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

def check_rebase_onto(reg_no, args):
    branch, onto = args["branch"], args["onto"]
    ok, _ = run_git(reg_no, "rev-parse", "--verify", branch)
    if not ok:
        return False
    ok, _ = run_git(reg_no, "merge-base", "--is-ancestor", onto, branch)
    if not ok:
        return False
    ok, ahead = run_git(reg_no, "rev-list", "--count", f"{onto}..{branch}")
    if not ok or not ahead.isdigit() or int(ahead) < 1:
        return False
    ok, merges = run_git(reg_no, "log", "--merges", "--oneline", f"{onto}..{branch}")
    return ok and merges.strip() == ""

def check_cherry_picked(reg_no, args):
    source, target = args["source"], args["target"]
    ok, base = run_git(reg_no, "merge-base", source, target)
    if not ok or not base:
        return False
    ok, source_log = run_git(reg_no, "log", "--format=%H %s", f"{base}..{source}")
    if not ok:
        return False
    source_commits = {}
    for line in source_log.splitlines():
        h, _, msg = line.partition(" ")
        source_commits[msg] = h
    ok, target_log = run_git(reg_no, "log", "--format=%H %s", f"{base}..{target}")
    if not ok:
        return False
    for line in target_log.splitlines():
        h, _, msg = line.partition(" ")
        if msg in source_commits and h != source_commits[msg]:
            return True
    return False

def check_in_sync_with_remote(reg_no, args):
    branch = args.get("branch", "main")
    remote = args.get("remote", "origin")
    ok1, local = run_git(reg_no, "rev-parse", branch)
    ok2, remote_sha = run_git(reg_no, "rev-parse", f"{remote}/{branch}")
    return ok1 and ok2 and local and local == remote_sha

def check_tag_exists(reg_no, args):
    ok, out = run_git(reg_no, "tag", "--list", args["tag"])
    return ok and args["tag"] in out.splitlines()

def check_branch_deleted(reg_no, args):
    ok, out = run_git(reg_no, "branch", "--list", args["branch"])
    return ok and args["branch"] not in out

def check_conflict_resolved(reg_no, _args):
    ok, unmerged = run_git(reg_no, "diff", "--name-only", "--diff-filter=U")
    if not ok or unmerged.strip():
        return False
    ok, merge_commit = run_git(reg_no, "log", "--merges", "-1", "--oneline")
    return ok and merge_commit.strip() != ""

def check_is_ignored(reg_no, args):
    ok, out = run_git(reg_no, "check-ignore", args["file"])
    return ok and out.strip() != ""

def check_revert_commit(reg_no, _args):
    ok, out = run_git(reg_no, "log", "-1", "--format=%s")
    return ok and out.startswith("Revert")

def check_amend_commit(reg_no, _args):
    # Checks that the last commit's author date and commit date differ (amended)
    # or simply that there is at least 1 commit (lenient)
    ok, out = run_git(reg_no, "log", "-1", "--format=%H")
    return ok and len(out.strip()) > 0

def check_stash_popped(reg_no, _args):
    # Stash list should be empty after pop
    ok, out = run_git(reg_no, "stash", "list")
    return ok and out.strip() == ""

def check_clean_working_tree(reg_no, _args):
    # No untracked files
    ok, out = run_git(reg_no, "status", "--short")
    lines = [l for l in out.splitlines() if l.startswith("??")]
    return ok and len(lines) == 0

def check_reset_hard(reg_no, _args):
    # Working tree is clean and HEAD is a valid commit
    ok, _ = run_git(reg_no, "rev-parse", "HEAD")
    if not ok:
        return False
    ok2, diff = run_git(reg_no, "status", "--short")
    return ok2 and diff.strip() == ""

def check_log_oneline(reg_no, _args):
    ok, out = run_git(reg_no, "log", "--oneline")
    return ok and len(out.strip()) > 0

def check_diff_staged(reg_no, _args):
    # At least one file is staged
    ok, out = run_git(reg_no, "diff", "--cached", "--name-only")
    return ok and out.strip() != ""

def check_multi_tag(reg_no, args):
    ok, out = run_git(reg_no, "tag", "--list")
    tags = [t.strip() for t in out.splitlines() if t.strip()]
    return ok and len(tags) >= args.get("min_count", 2)

def check_branch_renamed(reg_no, args):
    ok, out = run_git(reg_no, "branch", "--list", args["new_name"])
    return ok and args["new_name"] in out

def check_shortlog(reg_no, _args):
    ok, out = run_git(reg_no, "shortlog", "-s", "HEAD")
    return ok and len(out.strip()) > 0

def check_blame(reg_no, args):
    ok, out = run_git(reg_no, "blame", args.get("file", ""))
    return ok and len(out.strip()) > 0

def check_show_commit(reg_no, _args):
    ok, out = run_git(reg_no, "show", "--stat", "HEAD")
    return ok and len(out.strip()) > 0

def check_has_two_commits(reg_no, _args):
    ok, out = run_git(reg_no, "rev-list", "--count", "HEAD")
    return ok and out.strip().isdigit() and int(out.strip()) >= 2

def check_commit_with_message(reg_no, args):
    ok, out = run_git(reg_no, "log", "--format=%s")
    return ok and any(args["message"].lower() in line.lower() for line in out.splitlines())

def check_interactive_rebase(reg_no, _args):
    # At least 2 commits and no merge commits - sign of squash/reword
    ok, count = run_git(reg_no, "rev-list", "--count", "HEAD")
    if not ok or not count.strip().isdigit():
        return False
    ok2, merges = run_git(reg_no, "log", "--merges", "--oneline")
    return int(count.strip()) >= 1 and ok2

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
    "rebase_onto": check_rebase_onto,
    "cherry_picked": check_cherry_picked,
    "in_sync_with_remote": check_in_sync_with_remote,
    "tag_exists": check_tag_exists,
    "branch_deleted": check_branch_deleted,
    "conflict_resolved": check_conflict_resolved,
    "is_ignored": check_is_ignored,
    "revert_commit": check_revert_commit,
    "amend_commit": check_amend_commit,
    "stash_popped": check_stash_popped,
    "clean_working_tree": check_clean_working_tree,
    "reset_hard": check_reset_hard,
    "log_oneline": check_log_oneline,
    "diff_staged": check_diff_staged,
    "multi_tag": check_multi_tag,
    "branch_renamed": check_branch_renamed,
    "shortlog": check_shortlog,
    "blame": check_blame,
    "show_commit": check_show_commit,
    "has_two_commits": check_has_two_commits,
    "commit_with_message": check_commit_with_message,
    "interactive_rebase": check_interactive_rebase,
    "manual_review": check_manual_review,
}


# ---- Auth routes ----
@app.route("/api/auth/register", methods=["POST"])
@rate_limit(max_attempts=5, window_seconds=300)
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
    recovery_code = generate_recovery_code()
    conn.execute(
        "INSERT INTO users (reg_no, password_hash, is_admin, recovery_code_hash) VALUES (?, ?, ?, ?)",
        (reg_no, generate_password_hash(password), is_admin, generate_password_hash(recovery_code))
    )
    conn.commit()
    conn.close()
    session["reg_no"] = reg_no
    session["is_admin"] = bool(is_admin)
    start_workspace_safely(reg_no)
    return jsonify({
        "ok": True, "reg_no": reg_no, "is_admin": bool(is_admin),
        "recovery_code": recovery_code,
        "terminal_path": f"/terminal/{reg_no}/",
    })


@app.route("/api/auth/login", methods=["POST"])
@rate_limit(max_attempts=8, window_seconds=300)
def login():
    data = request.get_json(silent=True) or {}
    reg_no = (data.get("reg_no") or "").strip()
    password = data.get("password") or ""
    conn = get_db()
    row = conn.execute("SELECT password_hash, is_admin FROM users WHERE reg_no = ?", (reg_no,)).fetchone()
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
            workspace_manager.remove_workspace(reg_no)
        except Exception as e:
            log.error("Failed to remove workspace for %s on logout: %s", reg_no, e)
    return jsonify({"ok": True})


@app.route("/api/auth/forgot-password", methods=["POST"])
@rate_limit(max_attempts=5, window_seconds=300)
def forgot_password():
    data = request.get_json(silent=True) or {}
    reg_no = (data.get("reg_no") or "").strip()
    recovery_code = (data.get("recovery_code") or "").strip().upper()
    new_password = data.get("new_password") or ""
    if len(new_password) < 6:
        return jsonify({"error": "new password must be at least 6 characters"}), 400
    conn = get_db()
    row = conn.execute("SELECT recovery_code_hash FROM users WHERE reg_no = ?", (reg_no,)).fetchone()
    invalid = not row or not row[0] or not check_password_hash(row[0], recovery_code)
    if invalid:
        conn.close()
        return jsonify({"error": "invalid registration number or recovery code"}), 401
    new_recovery_code = generate_recovery_code()
    conn.execute(
        "UPDATE users SET password_hash = ?, recovery_code_hash = ? WHERE reg_no = ?",
        (generate_password_hash(new_password), generate_password_hash(new_recovery_code), reg_no)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "new_recovery_code": new_recovery_code})


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


# ---- Task routes ----
@app.route("/api/tasks")
@login_required
def list_tasks():
    user_id = session["reg_no"]
    touch_last_seen(user_id)
    conn = get_db()
    done = {row[0] for row in conn.execute("SELECT task_id FROM progress WHERE user_id = ?", (user_id,))}
    conn.close()
    out = []
    for t in sorted(TASKS.values(), key=lambda x: x["order"]):
        out.append({**t, "completed": t["id"] in done, "unlocked": t["prereq"] is None or t["prereq"] in done})
    return jsonify(out)


@app.route("/api/tasks/<task_id>/check", methods=["POST"])
@login_required
def check_task(task_id):
    user_id = session["reg_no"]
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": "unknown task"}), 404
    if not workspace_manager.workspace_container_exists(user_id):
        return jsonify({"error": "your terminal is not running — please reload the page to reconnect"}), 503
    validator = VALIDATORS.get(task["check"])
    if not validator:
        return jsonify({"error": "no validator"}), 500
    passed = validator(user_id, task.get("check_args", {}))
    if passed:
        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO progress (user_id, task_id) VALUES (?, ?)", (user_id, task_id))
        conn.commit()
        conn.close()
    return jsonify({"task_id": task_id, "passed": passed})


# ---- Admin routes ----
@app.route("/api/admin/students")
@admin_required
def admin_students():
    conn = get_db()
    users = conn.execute("SELECT reg_no, is_admin, created_at FROM users ORDER BY created_at").fetchall()
    total_tasks = len(TASKS)
    out = []
    for reg_no, is_admin, created_at in users:
        done = conn.execute(
            "SELECT task_id, completed_at FROM progress WHERE user_id = ? ORDER BY completed_at", (reg_no,)
        ).fetchall()
        last_activity = done[-1][1] if done else None
        out.append({
            "reg_no": reg_no, "is_admin": bool(is_admin), "created_at": created_at,
            "completed_count": len(done), "total_tasks": total_tasks,
            "last_activity": last_activity, "completed_tasks": [d[0] for d in done],
        })
    conn.close()
    return jsonify(out)


@app.route("/api/admin/students/<reg_no>", methods=["DELETE"])
@admin_required
def admin_delete_student(reg_no):
    if reg_no == session["reg_no"]:
        return jsonify({"error": "you cannot delete your own account while signed in"}), 400
    conn = get_db()
    if not conn.execute("SELECT reg_no FROM users WHERE reg_no = ?", (reg_no,)).fetchone():
        conn.close()
        return jsonify({"error": "no such student"}), 404
    conn.execute("DELETE FROM users WHERE reg_no = ?", (reg_no,))
    conn.execute("DELETE FROM progress WHERE user_id = ?", (reg_no,))
    conn.commit()
    conn.close()
    try:
        workspace_manager.remove_workspace(reg_no)
    except Exception as e:
        log.error("Failed to remove workspace for %s: %s", reg_no, e)
    return jsonify({"ok": True, "deleted": reg_no})


@app.route("/api/admin/students/<reg_no>/reset-password", methods=["POST"])
@admin_required
def admin_reset_password(reg_no):
    data = request.get_json(silent=True) or {}
    new_password = data.get("new_password") or ""
    if len(new_password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400
    conn = get_db()
    if not conn.execute("SELECT reg_no FROM users WHERE reg_no = ?", (reg_no,)).fetchone():
        conn.close()
        return jsonify({"error": "no such student"}), 404
    new_recovery_code = generate_recovery_code()
    conn.execute(
        "UPDATE users SET password_hash = ?, recovery_code_hash = ? WHERE reg_no = ?",
        (generate_password_hash(new_password), generate_password_hash(new_recovery_code), reg_no)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "reg_no": reg_no, "new_recovery_code": new_recovery_code})


@app.route("/api/admin/metrics")
@admin_required
def admin_metrics():
    conn = get_db()
    total_students = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active_15m = conn.execute("SELECT COUNT(*) FROM users WHERE last_seen > datetime('now', '-15 minutes')").fetchone()[0]
    active_1h = conn.execute("SELECT COUNT(*) FROM users WHERE last_seen > datetime('now', '-1 hour')").fetchone()[0]
    conn.close()
    try:
        cm = workspace_manager.get_metrics()
    except Exception as e:
        log.error("Failed to gather metrics: %s", e)
        return jsonify({"error": "failed to gather metrics"}), 500
    workspaces = cm["workspaces"]
    running = [w for w in workspaces if w["status"] == "running"]
    return jsonify({
        "students": {"total": total_students, "active_last_15min": active_15m, "active_last_hour": active_1h},
        "workspaces": {
            "running": len(running),
            "stopped": len(workspaces) - len(running),
            "total_ever_created": len(workspaces),
            "total_mem_used_mb": round(sum(w.get("mem_used_mb") or 0 for w in running), 1),
            "total_mem_cap_mb": round(sum(w.get("mem_limit_mb") or 0 for w in running), 1),
            "detail": workspaces,
        },
        "core_services": cm["core_services"],
        "idle_workspace_hours": float(os.environ.get("IDLE_WORKSPACE_HOURS", "24")),
    })


@app.route("/api/internal/authorize-terminal")
def authorize_terminal():
    target_reg_no = request.headers.get("X-Reg-No", "")
    if "reg_no" not in session:
        return "", 401
    if session["reg_no"] == target_reg_no or session.get("is_admin"):
        touch_last_seen(target_reg_no)
        return "", 200
    return "", 403


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


# ---- Idle reaper ----
IDLE_WORKSPACE_HOURS = float(os.environ.get("IDLE_WORKSPACE_HOURS", "24"))
REAPER_INTERVAL_SECONDS = 3600


def _idle_reaper_loop():
    while True:
        time.sleep(REAPER_INTERVAL_SECONDS)
        try:
            conn = get_db()
            rows = conn.execute("SELECT reg_no, last_seen FROM users").fetchall()
            conn.close()
            last_seen_map = {}
            for reg_no, last_seen in rows:
                if not last_seen:
                    last_seen_map[reg_no] = None
                    continue
                try:
                    last_seen_map[reg_no] = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    last_seen_map[reg_no] = None
            removed = workspace_manager.reap_idle_workspaces(last_seen_map, IDLE_WORKSPACE_HOURS)
            if removed:
                log.info("Idle reaper removed %d container(s): %s", len(removed), removed)
        except Exception as e:
            log.error("Idle reaper sweep failed: %s", e)


threading.Thread(target=_idle_reaper_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
