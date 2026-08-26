from fastapi import APIRouter, Depends, HTTPException, Request
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
