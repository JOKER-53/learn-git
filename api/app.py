"""
learn-git API
- Serves task list
- Validates task completion by inspecting the student's repo (mounted volume)
- Stores progress in SQLite (persisted via docker volume)
"""
import json
import os
import sqlite3
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

TASKS_PATH = Path(os.environ.get("TASKS_PATH", "/app/tasks/tasks.json"))
WORKSPACE_REPO = os.environ.get("WORKSPACE_REPO_PATH", "/workspace-data/repo")
DB_PATH = os.environ.get("DB_PATH", "/data/progress.db")

with open(TASKS_PATH) as f:
    TASKS = {t["id"]: t for t in json.load(f)}


def get_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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


def run_git(*args):
    """Run a git command inside the student's repo, return (ok, stdout)."""
    try:
        result = subprocess.run(
            ["git", "-C", WORKSPACE_REPO, *args],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


# ---- Validators ----

def check_repo_exists(_args):
    return os.path.isdir(os.path.join(WORKSPACE_REPO, ".git"))


def check_has_commit(_args):
    ok, out = run_git("log", "--oneline")
    return ok and len(out) > 0


def check_branch_exists(args):
    ok, out = run_git("branch", "--list", args["branch"])
    return ok and args["branch"] in out


def check_current_branch_is(args):
    ok, out = run_git("rev-parse", "--abbrev-ref", "HEAD")
    return ok and out == args["branch"]


def check_branch_merged_into(args):
    ok, out = run_git("branch", "--merged", args["into"])
    branches = [b.strip().lstrip("* ").strip() for b in out.splitlines()]
    return ok and args["branch"] in branches


def check_stash_not_empty(_args):
    ok, out = run_git("stash", "list")
    return ok and len(out) > 0


def check_has_remote(args):
    ok, out = run_git("remote")
    return ok and args["remote"] in out.splitlines()


def check_manual_review(_args):
    # Placeholder for tasks needing richer inspection (e.g. reflog diffing).
    # For now these are marked complete via explicit "submit" endpoint.
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


# ---- Routes ----

@app.route("/api/tasks")
def list_tasks():
    user_id = request.args.get("user_id", "anon")
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
def check_task(task_id):
    user_id = request.json.get("user_id", "anon") if request.is_json else "anon"
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": "unknown task"}), 404

    validator = VALIDATORS.get(task["check"])
    if not validator:
        return jsonify({"error": "no validator"}), 500

    passed = validator(task.get("check_args", {}))

    if passed:
        conn = get_db()
        conn.execute(
            "INSERT OR IGNORE INTO progress (user_id, task_id) VALUES (?, ?)",
            (user_id, task_id)
        )
        conn.commit()
        conn.close()

    return jsonify({"task_id": task_id, "passed": passed})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
