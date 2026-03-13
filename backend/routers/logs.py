from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.models.database import get_db, BotLog
from backend.models.schemas import BotLogOut

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=List[BotLogOut])
def get_logs(
    level: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(BotLog)
    if level:
        q = q.filter_by(level=level.upper())
    if category:
        q = q.filter_by(category=category)
    q = q.order_by(BotLog.created_at.desc())
    return q.offset(offset).limit(limit).all()


@router.delete("")
def clear_logs(category: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(BotLog)
    if category:
        q = q.filter_by(category=category)
    count = q.count()
    q.delete()
    db.commit()
    return {"ok": True, "deleted": count}
