from fastapi import APIRouter, Depends, Request, HTTPException
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
    
    start_workspace_safely(reg_no)
    
    return {
        "authenticated": True,
        "reg_no": reg_no,
        "is_admin": request.session.get("is_admin", False),
        "terminal_path": f"/terminal/{reg_no}/"
    }


@router.post("/reset-workspace")
def reset_workspace(reg_no: str = Depends(get_current_user)):
    try:
        workspace_manager.reset_workspace_volume(reg_no)
        # Also restart their container so they get a fresh terminal
        workspace_manager.remove_workspace(reg_no)
        workspace_manager.ensure_workspace(reg_no)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})
