from fastapi import FastAPI, Request, Response
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
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


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
