from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from backend.models.database import get_db, Schedule, TargetAccount
from backend.models.schemas import ScheduleCreate, ScheduleOut
from backend.core.scheduler import (
    register_target_jobs, unregister_target_jobs, get_job_statuses,
    start_scheduler, stop_scheduler,
)

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/status")
def scheduler_status():
    return get_job_statuses()


@router.post("/start")
def start():
    start_scheduler()
    return {"ok": True, "message": "Scheduler started"}


@router.post("/stop")
def stop():
    stop_scheduler()
    return {"ok": True, "message": "Scheduler stopped"}


@router.get("/schedules", response_model=List[ScheduleOut])
def list_schedules(target_id: int = None, db: Session = Depends(get_db)):
    q = db.query(Schedule)
    if target_id:
        q = q.filter_by(target_account_id=target_id)
    return q.all()


@router.post("/schedules", response_model=ScheduleOut)
def create_schedule(data: ScheduleCreate, db: Session = Depends(get_db)):
    target = db.query(TargetAccount).get(data.target_account_id)
    if not target:
        raise HTTPException(404, "Target account not found")

    existing = db.query(Schedule).filter_by(
        target_account_id=data.target_account_id, is_active=True
    ).first()
    if existing:
        raise HTTPException(400, "Active schedule already exists. Update the existing one.")

    schedule = Schedule(**data.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    register_target_jobs(data.target_account_id)
    return schedule


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, data: ScheduleCreate, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).get(schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    for field, value in data.model_dump().items():
        setattr(schedule, field, value)
    schedule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(schedule)

    # Re-register jobs with new settings
    register_target_jobs(schedule.target_account_id)
    return schedule


@router.patch("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).get(schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    schedule.is_active = not schedule.is_active
    schedule.updated_at = datetime.utcnow()
    db.commit()

    if schedule.is_active:
        register_target_jobs(schedule.target_account_id)
    else:
        unregister_target_jobs(schedule.target_account_id)

    return {"ok": True, "is_active": schedule.is_active}


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).get(schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    unregister_target_jobs(schedule.target_account_id)
    db.delete(schedule)
    db.commit()
    return {"ok": True}
