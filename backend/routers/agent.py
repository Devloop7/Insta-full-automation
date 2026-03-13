from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from backend.models.database import get_db, AgentLog, TargetAccount, AgentAction
from backend.models.schemas import AgentLogOut, AgentRunRequest

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/run")
def run_agent(req: AgentRunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Manually trigger an agent session for a target account."""
    target = db.query(TargetAccount).get(req.target_account_id)
    if not target:
        raise HTTPException(404, "Target account not found")

    def _run():
        from backend.models.database import SessionLocal, Schedule
        from backend.services.ai_agent import InstagramAgent
        db2 = SessionLocal()
        try:
            t = db2.query(TargetAccount).get(req.target_account_id)
            schedule = db2.query(Schedule).filter_by(
                target_account_id=req.target_account_id, is_active=True
            ).first()
            if not schedule:
                from backend.models.database import Schedule
                # Create a temp schedule object for manual run
                class TempSchedule:
                    agent_like_enabled = True
                    agent_comment_enabled = True
                    agent_max_likes_per_run = req.like_count
                    agent_max_comments_per_run = req.comment_count
                schedule = TempSchedule()
            else:
                schedule.agent_max_likes_per_run = req.like_count
                schedule.agent_max_comments_per_run = req.comment_count

            agent = InstagramAgent(t, schedule)
            agent.run(db2)
        finally:
            db2.close()

    background_tasks.add_task(_run)
    return {"ok": True, "message": f"Agent running for @{target.username} in background"}


@router.get("/logs", response_model=List[AgentLogOut])
def get_logs(
    target_id: int = None,
    action: Optional[AgentAction] = None,
    limit: int = 100,
    offset: int = 0,
    today_only: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(AgentLog)
    if target_id:
        q = q.filter_by(target_account_id=target_id)
    if action:
        q = q.filter_by(action=action)
    if today_only:
        today = date.today()
        q = q.filter(AgentLog.created_at >= datetime(today.year, today.month, today.day))
    q = q.order_by(AgentLog.created_at.desc())
    return q.offset(offset).limit(limit).all()


@router.get("/stats")
def agent_stats(target_id: int = None, db: Session = Depends(get_db)):
    """Daily and total stats for the agent."""
    today = date.today()
    today_start = datetime(today.year, today.month, today.day)

    q_all = db.query(AgentLog)
    q_today = db.query(AgentLog).filter(AgentLog.created_at >= today_start)

    if target_id:
        q_all = q_all.filter_by(target_account_id=target_id)
        q_today = q_today.filter_by(target_account_id=target_id)

    def count_action(q, action):
        return q.filter_by(action=action).count()

    return {
        "total": {
            "likes": count_action(q_all, AgentAction.LIKE),
            "comments": count_action(q_all, AgentAction.COMMENT),
            "follows": count_action(q_all, AgentAction.FOLLOW),
        },
        "today": {
            "likes": count_action(q_today, AgentAction.LIKE),
            "comments": count_action(q_today, AgentAction.COMMENT),
            "follows": count_action(q_today, AgentAction.FOLLOW),
        },
    }
