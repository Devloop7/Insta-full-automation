"""
APScheduler-based automation engine.
Each target account gets its own scrape + post + agent jobs.
"""
import logging
from datetime import datetime
from typing import Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore

from backend.models.database import SessionLocal, TargetAccount, Schedule

logger = logging.getLogger("instabot.scheduler")

scheduler = BackgroundScheduler(
    jobstores={"default": MemoryJobStore()},
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    timezone="UTC",
)

_job_status: Dict[str, Any] = {}   # job_id → last run info


# ── Job functions ──────────────────────────────────────────────────────────

def _scrape_job(target_account_id: int):
    """Scheduled scrape job."""
    from backend.services.content_pipeline import scrape_source_account
    db = SessionLocal()
    try:
        target = db.query(TargetAccount).get(target_account_id)
        if not target or not target.is_active:
            return
        for source in target.source_accounts:
            if source.is_active:
                scrape_source_account(db, source, target)
        _job_status[f"scrape_{target_account_id}"] = {
            "last_run": datetime.utcnow().isoformat(),
            "status": "ok",
        }
    except Exception as e:
        logger.error(f"Scrape job error (target {target_account_id}): {e}")
        _job_status[f"scrape_{target_account_id}"] = {
            "last_run": datetime.utcnow().isoformat(),
            "status": "error",
            "error": str(e),
        }
    finally:
        db.close()


def _download_caption_job(target_account_id: int):
    """Download + caption generation job."""
    from backend.services.content_pipeline import (
        download_pending_items, generate_captions_for_downloaded
    )
    db = SessionLocal()
    try:
        target = db.query(TargetAccount).get(target_account_id)
        if not target or not target.is_active:
            return
        download_pending_items(db, target)
        generate_captions_for_downloaded(db, target)
        _job_status[f"download_{target_account_id}"] = {
            "last_run": datetime.utcnow().isoformat(),
            "status": "ok",
        }
    except Exception as e:
        logger.error(f"Download/caption job error (target {target_account_id}): {e}")
    finally:
        db.close()


def _post_job(target_account_id: int, hour: int, minute: int):
    """Post job — triggered at scheduled times."""
    from backend.services.content_pipeline import post_queued_items
    db = SessionLocal()
    try:
        target = db.query(TargetAccount).get(target_account_id)
        if not target or not target.is_active:
            return
        schedule = db.query(Schedule).filter_by(
            target_account_id=target_account_id, is_active=True
        ).first()
        if not schedule or not schedule.post_enabled:
            return
        posted = post_queued_items(db, target, max_posts=1)
        _job_status[f"post_{target_account_id}_{hour}:{minute:02d}"] = {
            "last_run": datetime.utcnow().isoformat(),
            "posted": posted,
            "status": "ok",
        }
    except Exception as e:
        logger.error(f"Post job error (target {target_account_id}): {e}")
    finally:
        db.close()


def _agent_job(target_account_id: int):
    """AI agent engagement job."""
    from backend.services.ai_agent import run_agent_for_target
    db = SessionLocal()
    try:
        target = db.query(TargetAccount).get(target_account_id)
        if not target or not target.is_active:
            return
        result = run_agent_for_target(db, target)
        _job_status[f"agent_{target_account_id}"] = {
            "last_run": datetime.utcnow().isoformat(),
            "result": result,
            "status": "ok",
        }
    except Exception as e:
        logger.error(f"Agent job error (target {target_account_id}): {e}")
        _job_status[f"agent_{target_account_id}"] = {
            "last_run": datetime.utcnow().isoformat(),
            "status": "error",
            "error": str(e),
        }
    finally:
        db.close()


# ── Schedule management ────────────────────────────────────────────────────

def register_target_jobs(target_account_id: int):
    """Register all scheduler jobs for a target account."""
    db = SessionLocal()
    try:
        target = db.query(TargetAccount).get(target_account_id)
        if not target:
            return
        schedule = db.query(Schedule).filter_by(
            target_account_id=target_account_id, is_active=True
        ).first()
        if not schedule:
            return

        _remove_target_jobs(target_account_id)

        # Scrape job
        if schedule.scrape_enabled:
            scheduler.add_job(
                _scrape_job,
                trigger=IntervalTrigger(hours=schedule.scrape_interval_hours),
                args=[target_account_id],
                id=f"scrape_{target_account_id}",
                replace_existing=True,
            )
            # Download + caption after scrape (15 min lag)
            scheduler.add_job(
                _download_caption_job,
                trigger=IntervalTrigger(hours=schedule.scrape_interval_hours, start_date=None),
                args=[target_account_id],
                id=f"download_{target_account_id}",
                replace_existing=True,
            )

        # Post jobs (one per scheduled time)
        if schedule.post_enabled:
            for time_str in schedule.post_times.split(","):
                time_str = time_str.strip()
                if ":" not in time_str:
                    continue
                hour, minute = map(int, time_str.split(":"))
                job_id = f"post_{target_account_id}_{hour}:{minute:02d}"
                scheduler.add_job(
                    _post_job,
                    trigger=CronTrigger(hour=hour, minute=minute),
                    args=[target_account_id, hour, minute],
                    id=job_id,
                    replace_existing=True,
                )

        # Agent job
        if schedule.agent_enabled:
            scheduler.add_job(
                _agent_job,
                trigger=IntervalTrigger(minutes=schedule.agent_interval_minutes),
                args=[target_account_id],
                id=f"agent_{target_account_id}",
                replace_existing=True,
            )

        logger.info(f"Registered jobs for target account {target_account_id} (@{target.username})")

    finally:
        db.close()


def _remove_target_jobs(target_account_id: int):
    """Remove all scheduler jobs for a target account."""
    prefixes = [f"scrape_{target_account_id}", f"download_{target_account_id}",
                f"agent_{target_account_id}"]

    for job in scheduler.get_jobs():
        if any(job.id.startswith(p) for p in prefixes) or \
           job.id.startswith(f"post_{target_account_id}_"):
            try:
                scheduler.remove_job(job.id)
            except Exception:
                pass


def unregister_target_jobs(target_account_id: int):
    _remove_target_jobs(target_account_id)
    logger.info(f"Unregistered jobs for target account {target_account_id}")


def load_all_schedules():
    """Called on startup — register jobs for all active targets with active schedules."""
    db = SessionLocal()
    try:
        targets = db.query(TargetAccount).filter_by(is_active=True).all()
        for target in targets:
            has_schedule = db.query(Schedule).filter_by(
                target_account_id=target.id, is_active=True
            ).first()
            if has_schedule:
                register_target_jobs(target.id)
        logger.info(f"Loaded schedules for {len(targets)} target accounts")
    finally:
        db.close()


def get_job_statuses() -> dict:
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "last_status": _job_status.get(job.id),
        })
    return {
        "running": scheduler.running,
        "jobs": jobs,
        "job_count": len(jobs),
    }


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        load_all_schedules()
        logger.info("Scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
