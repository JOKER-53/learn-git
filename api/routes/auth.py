from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import os
import workspace_manager
from db import get_db
from utils import rate_limit, generate_recovery_code, start_workspace_safely

auth_bp = Blueprint("auth", __name__)
ADMIN_REG_NOS = set(r.strip() for r in os.environ.get("ADMIN_REG_NOS", "").split(",") if r.strip())

@auth_bp.route("/register", methods=["POST"])
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

@auth_bp.route("/login", methods=["POST"])
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

@auth_bp.route("/logout", methods=["POST"])
def logout():
    reg_no = session.get("reg_no")
    session.clear()
    if reg_no:
        try:
            workspace_manager.remove_workspace(reg_no)
        except Exception as e:
            import logging
            log = logging.getLogger("learn-git")
            log.error("Failed to remove workspace for %s on logout: %s", reg_no, e)
    return jsonify({"ok": True})

@auth_bp.route("/forgot-password", methods=["POST"])
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

@auth_bp.route("/me")
def me():
    if "reg_no" not in session:
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "authenticated": True,
        "reg_no": session["reg_no"],
        "is_admin": bool(session.get("is_admin")),
        "terminal_path": f"/terminal/{session['reg_no']}/",
    })
