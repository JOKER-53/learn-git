import os
import secrets
import string
import time
from collections import defaultdict
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import logging
from werkzeug.security import generate_password_hash as werkzeug_generate, check_password_hash as werkzeug_check

log = logging.getLogger("learn-git")


def get_password_hash(password):
    return werkzeug_generate(password)

def verify_password(plain_password, hashed_password):
    return werkzeug_check(hashed_password, plain_password)

def generate_recovery_code():
    alphabet = string.ascii_uppercase + string.digits
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"

_rate_limit_hits = defaultdict(list)

def check_rate_limit(request: Request, max_attempts: int, window_seconds: int):
    ip = request.headers.get("X-Real-IP", request.client.host) or "unknown"
    key = f"{request.url.path}:{ip}"
    now = time.time()
    hits = _rate_limit_hits[key]
    hits[:] = [t for t in hits if now - t < window_seconds]
    if len(hits) >= max_attempts:
        retry_after = int(window_seconds - (now - hits[0]))
        raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in {max(retry_after, 1)}s.")
    hits.append(now)

from .db import User
def touch_last_seen(db: Session, reg_no: str):
    user = db.query(User).filter(User.reg_no == reg_no).first()
    if user:
        user.last_seen = datetime.utcnow()
        db.commit()
