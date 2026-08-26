import os

files = {}

files["api/requirements.txt"] = """fastapi==0.111.0
uvicorn[standard]==0.30.1
sqlalchemy==2.0.31
alembic==1.13.1
pydantic==2.7.4
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
docker==7.1.0
"""

files["api/Dockerfile"] = """FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ /app/api
COPY tasks/ /app/tasks

EXPOSE 5000
# Run uvicorn server for FastAPI
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port 5000 --workers ${WEB_CONCURRENCY:-4}"]
"""

files["api/db.py"] = """import os
from sqlalchemy import create_engine, Column, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "/dbdata/progress.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    reg_no = Column(String, primary_key=True, index=True)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    recovery_code_hash = Column(String, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Progress(Base):
    __tablename__ = "progress"
    user_id = Column(String, primary_key=True)
    task_id = Column(String, primary_key=True)
    completed_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
"""

files["api/utils.py"] = """import os
import secrets
import string
import time
from collections import defaultdict
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import logging
from passlib.context import CryptContext

log = logging.getLogger("learn-git")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

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
"""

files["api/deps.py"] = """from fastapi import Depends, Request, HTTPException
from sqlalchemy.orm import Session
from .db import get_db, User

def get_current_user(request: Request, db: Session = Depends(get_db)):
    reg_no = request.session.get("reg_no")
    if not reg_no:
        raise HTTPException(status_code=401, detail={"error": "not authenticated"})
    return reg_no

def get_admin_user(request: Request, db: Session = Depends(get_db)):
    reg_no = request.session.get("reg_no")
    is_admin = request.session.get("is_admin")
    if not reg_no:
        raise HTTPException(status_code=401, detail={"error": "not authenticated"})
    if not is_admin:
        raise HTTPException(status_code=403, detail={"error": "admin only"})
    return reg_no
"""

files["api/routes/auth.py"] = """from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os
from ..db import get_db, User
from ..utils import generate_recovery_code, check_rate_limit, get_password_hash, verify_password
import api.workspace_manager as workspace_manager

router = APIRouter()
ADMIN_REG_NOS = set(r.strip() for r in os.environ.get("ADMIN_REG_NOS", "").split(",") if r.strip())

class AuthRequest(BaseModel):
    reg_no: str
    password: str

class ForgotPasswordRequest(BaseModel):
    reg_no: str
    recovery_code: str
    new_password: str

def start_workspace_safely(reg_no):
    try:
        workspace_manager.ensure_workspace(reg_no)
        workspace_manager.ensure_git_remote(reg_no)
    except Exception:
        pass

@router.post("/register")
def register(req: AuthRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, 5, 300)
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail={"error": "password must be at least 6 characters"})
    if not workspace_manager.is_safe_reg_no(req.reg_no):
        raise HTTPException(status_code=400, detail={"error": "reg_no may only contain letters, numbers, - and _"})
    
    if db.query(User).filter(User.reg_no == req.reg_no).first():
        raise HTTPException(status_code=409, detail={"error": "account already exists"})
        
    is_admin = req.reg_no in ADMIN_REG_NOS
    recovery_code = generate_recovery_code()
    
    user = User(
        reg_no=req.reg_no,
        password_hash=get_password_hash(req.password),
        is_admin=is_admin,
        recovery_code_hash=get_password_hash(recovery_code)
    )
    db.add(user)
    db.commit()
    
    request.session["reg_no"] = req.reg_no
    request.session["is_admin"] = is_admin
    start_workspace_safely(req.reg_no)
    
    return {
        "ok": True, "reg_no": req.reg_no, "is_admin": is_admin,
        "recovery_code": recovery_code,
        "terminal_path": f"/terminal/{req.reg_no}/"
    }

@router.post("/login")
def login(req: AuthRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, 8, 300)
    user = db.query(User).filter(User.reg_no == req.reg_no).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"error": "invalid registration number or password"})
    
    request.session["reg_no"] = user.reg_no
    request.session["is_admin"] = user.is_admin
    start_workspace_safely(user.reg_no)
    
    return {
        "ok": True, "reg_no": user.reg_no, "is_admin": user.is_admin,
        "terminal_path": f"/terminal/{user.reg_no}/"
    }

@router.post("/logout")
def logout(request: Request):
    reg_no = request.session.get("reg_no")
    request.session.clear()
    if reg_no:
        try:
            workspace_manager.remove_workspace(reg_no)
        except Exception:
            pass
    return {"ok": True}

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, 5, 300)
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail={"error": "new password must be at least 6 characters"})
    
    user = db.query(User).filter(User.reg_no == req.reg_no).first()
    if not user or not user.recovery_code_hash or not verify_password(req.recovery_code.upper(), user.recovery_code_hash):
        raise HTTPException(status_code=401, detail={"error": "invalid registration number or recovery code"})
        
    new_recovery_code = generate_recovery_code()
    user.password_hash = get_password_hash(req.new_password)
    user.recovery_code_hash = get_password_hash(new_recovery_code)
    db.commit()
    return {"ok": True, "new_recovery_code": new_recovery_code}

@router.get("/me")
def me(request: Request):
    reg_no = request.session.get("reg_no")
    if not reg_no:
        raise HTTPException(status_code=401, detail={"authenticated": False})
    return {
        "authenticated": True,
        "reg_no": reg_no,
        "is_admin": request.session.get("is_admin", False),
        "terminal_path": f"/terminal/{reg_no}/"
    }
"""

files["api/routes/tasks.py"] = """from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import json
import os
from ..db import get_db, Progress
from ..deps import get_current_user
from ..utils import touch_last_seen
from ..validators import VALIDATORS
import api.workspace_manager as workspace_manager

router = APIRouter()

TASKS_PATH = os.environ.get("TASKS_PATH", "/app/tasks/tasks.json")
try:
    with open(TASKS_PATH) as f:
        TASKS = {t["id"]: t for t in json.load(f)}
except FileNotFoundError:
    TASKS = {}

@router.get("/")
def list_tasks(user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    touch_last_seen(db, user_id)
    done_records = db.query(Progress.task_id).filter(Progress.user_id == user_id).all()
    done = {r[0] for r in done_records}
    
    out = []
    for t in sorted(TASKS.values(), key=lambda x: x.get("order", 0)):
        out.append({
            **t,
            "completed": t["id"] in done,
            "unlocked": t.get("prereq") is None or t["prereq"] in done
        })
    return out

@router.post("/{task_id}/check")
def check_task(task_id: str, user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"error": "unknown task"})
    if not workspace_manager.workspace_container_exists(user_id):
        raise HTTPException(status_code=503, detail={"error": "your terminal is not running — please reload the page to reconnect"})
    
    validator = VALIDATORS.get(task.get("check"))
    if not validator:
        raise HTTPException(status_code=500, detail={"error": "no validator"})
        
    passed = validator(user_id, task.get("check_args", {}))
    if passed:
        existing = db.query(Progress).filter(Progress.user_id == user_id, Progress.task_id == task_id).first()
        if not existing:
            db.add(Progress(user_id=user_id, task_id=task_id))
            db.commit()
            
    return {"task_id": task_id, "passed": passed}
"""

files["api/routes/admin.py"] = """from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os
from ..db import get_db, User, Progress
from ..deps import get_admin_user
from ..utils import generate_recovery_code, get_password_hash
import api.workspace_manager as workspace_manager

router = APIRouter()

TASKS_PATH = os.environ.get("TASKS_PATH", "/app/tasks/tasks.json")
try:
    import json
    with open(TASKS_PATH) as f:
        TASKS = json.load(f)
except:
    TASKS = []

class AdminResetPasswordReq(BaseModel):
    new_password: str

@router.get("/users")
def admin_students(admin_user: str = Depends(get_admin_user), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at).all()
    total_tasks = len(TASKS)
    out = []
    for u in users:
        done = db.query(Progress).filter(Progress.user_id == u.reg_no).order_by(Progress.completed_at).all()
        last_activity = done[-1].completed_at if done else None
        out.append({
            "reg_no": u.reg_no, "is_admin": u.is_admin, "created_at": u.created_at,
            "completed_count": len(done), "total_tasks": total_tasks,
            "last_activity": last_activity, "completed_tasks": [d.task_id for d in done],
            "last_seen": u.last_seen
        })
    return out

@router.delete("/users/{reg_no}")
def admin_delete_student(reg_no: str, request: Request, admin_user: str = Depends(get_admin_user), db: Session = Depends(get_db)):
    if reg_no == request.session.get("reg_no"):
        raise HTTPException(status_code=400, detail={"error": "you cannot delete your own account while signed in"})
        
    user = db.query(User).filter(User.reg_no == reg_no).first()
    if not user:
        raise HTTPException(status_code=404, detail={"error": "no such student"})
        
    db.delete(user)
    db.query(Progress).filter(Progress.user_id == reg_no).delete()
    db.commit()
    
    try:
        workspace_manager.remove_workspace(reg_no)
    except Exception:
        pass
    return {"ok": True, "deleted": reg_no}

@router.post("/users/{reg_no}/reset-password")
def admin_reset_password(reg_no: str, req: AdminResetPasswordReq, admin_user: str = Depends(get_admin_user), db: Session = Depends(get_db)):
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail={"error": "password must be at least 6 characters"})
        
    user = db.query(User).filter(User.reg_no == reg_no).first()
    if not user:
        raise HTTPException(status_code=404, detail={"error": "no such student"})
        
    new_recovery_code = generate_recovery_code()
    user.password_hash = get_password_hash(req.new_password)
    user.recovery_code_hash = get_password_hash(new_recovery_code)
    db.commit()
    return {"ok": True, "reg_no": reg_no, "new_recovery_code": new_recovery_code}
"""

files["api/main.py"] = """from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime
import os
import threading
import time

from .db import get_db, User
from .routes import auth, tasks, admin
import api.workspace_manager as workspace_manager
from .utils import touch_last_seen

app = FastAPI(title="learn-git API")

secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")
secure_cookie = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

app.add_middleware(SessionMiddleware, secret_key=secret_key, https_only=secure_cookie, same_site="lax")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("CORS_ORIGIN", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.get("/api/internal/authorize-terminal")
def authorize_terminal(request: Request):
    target_reg_no = request.headers.get("X-Reg-No", "")
    reg_no = request.session.get("reg_no")
    is_admin = request.session.get("is_admin")
    
    if not reg_no:
        return Response(status_code=401)
    if reg_no == target_reg_no or is_admin:
        from .db import SessionLocal
        db = SessionLocal()
        touch_last_seen(db, target_reg_no)
        db.close()
        return Response(status_code=200)
    return Response(status_code=403)

# ---- Idle reaper ----
IDLE_WORKSPACE_HOURS = float(os.environ.get("IDLE_WORKSPACE_HOURS", "24"))
REAPER_INTERVAL_SECONDS = 3600

def _idle_reaper_loop():
    while True:
        time.sleep(REAPER_INTERVAL_SECONDS)
        try:
            from .db import SessionLocal
            db = SessionLocal()
            users = db.query(User.reg_no, User.last_seen).all()
            db.close()
            last_seen_map = {u[0]: u[1] for u in users}
            workspace_manager.reap_idle_workspaces(last_seen_map, IDLE_WORKSPACE_HOURS)
        except Exception as e:
            pass

threading.Thread(target=_idle_reaper_loop, daemon=True).start()
"""

files["api/alembic.ini"] = """[alembic]
script_location = api/alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = sqlite:////dbdata/progress.db

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""

files["api/alembic/env.py"] = """from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os

from api.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
db_path = os.environ.get("DB_PATH", "/dbdata/progress.db")
config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""

files["api/alembic/script.py.mako"] = """\"\"\"${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

\"\"\"
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
"""

import shutil

# Make sure alembic directories exist
os.makedirs("api/alembic/versions", exist_ok=True)

# Write all files
for path, content in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

# Clean up old files
to_remove = ["api/app.py"]
for r in to_remove:
    if os.path.exists(r):
        os.remove(r)
print("Migration script completed.")
