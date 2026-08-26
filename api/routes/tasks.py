from fastapi import APIRouter, Depends, HTTPException, Request
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
