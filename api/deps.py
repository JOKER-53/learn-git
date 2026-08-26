from fastapi import Depends, Request, HTTPException
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
