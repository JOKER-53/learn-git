import secrets
import string
import time
import logging
from functools import wraps
from flask import request, jsonify, session
from collections import defaultdict
from db import get_db

log = logging.getLogger("learn-git")

def generate_recovery_code():
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

import workspace_manager

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
