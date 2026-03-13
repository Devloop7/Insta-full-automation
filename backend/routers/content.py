from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from backend.models.database import get_db, ContentItem, ContentStatus, TargetAccount
from backend.models.schemas import ContentItemOut, ContentQueueAction, ScrapeRequest
from backend.services.content_pipeline import (
    scrape_source_account, download_pending_items,
    generate_captions_for_downloaded, post_next_queued_item,
    run_full_pipeline,
)

router = APIRouter(prefix="/api/content", tags=["content"])


@router.get("/queue", response_model=List[ContentItemOut])
def get_queue(
    target_id: int = None,
    status: Optional[ContentStatus] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(ContentItem)
    if target_id:
        q = q.filter_by(target_account_id=target_id)
    if status:
        q = q.filter_by(status=status)
    q = q.order_by(ContentItem.created_at.desc())
    return q.offset(offset).limit(limit).all()


@router.get("/queue/{item_id}", response_model=ContentItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ContentItem).get(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@router.patch("/queue/{item_id}", response_model=ContentItemOut)
def update_item(item_id: int, action: ContentQueueAction, db: Session = Depends(get_db)):
    item = db.query(ContentItem).get(item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    if action.action == "approve":
        item.status = ContentStatus.QUEUED
    elif action.action == "skip":
        item.status = ContentStatus.SKIPPED
    elif action.action == "reschedule":
        item.status = ContentStatus.QUEUED
        item.scheduled_at = action.scheduled_at
    else:
        raise HTTPException(400, f"Unknown action: {action.action}")

    if action.caption is not None:
        item.caption = action.caption
    if action.hashtags is not None:
        item.hashtags = action.hashtags

    db.commit()
    db.refresh(item)
    return item


@router.delete("/queue/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ContentItem).get(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/scrape")
def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Manually trigger scraping for a target account."""
    target = db.query(TargetAccount).get(req.target_account_id)
    if not target:
        raise HTTPException(404, "Target account not found")

    sources = [s for s in target.source_accounts if s.is_active]
    if req.source_account_ids:
        sources = [s for s in sources if s.id in req.source_account_ids]

    if not sources:
        raise HTTPException(400, "No active source accounts found")

    def _run():
        from backend.models.database import SessionLocal
        db2 = SessionLocal()
        try:
            t = db2.query(TargetAccount).get(req.target_account_id)
            for source in db2.query(TargetAccount).get(req.target_account_id).source_accounts:
                if source.is_active:
                    if not req.source_account_ids or source.id in req.source_account_ids:
                        scrape_source_account(db2, source, t)
        finally:
            db2.close()

    background_tasks.add_task(_run)
    return {"ok": True, "message": f"Scraping {len(sources)} source(s) in background"}


@router.post("/download")
def trigger_download(target_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Manually trigger download of pending items."""
    target = db.query(TargetAccount).get(target_id)
    if not target:
        raise HTTPException(404, "Target account not found")

    def _run():
        from backend.models.database import SessionLocal
        db2 = SessionLocal()
        try:
            t = db2.query(TargetAccount).get(target_id)
            download_pending_items(db2, t)
            generate_captions_for_downloaded(db2, t)
        finally:
            db2.close()

    background_tasks.add_task(_run)
    return {"ok": True, "message": "Download + caption generation started in background"}


@router.post("/post-now")
def post_now(target_id: int, db: Session = Depends(get_db)):
    """Immediately post the next queued item."""
    target = db.query(TargetAccount).get(target_id)
    if not target:
        raise HTTPException(404, "Target account not found")

    item = post_next_queued_item(db, target)
    if not item:
        raise HTTPException(404, "No queued items ready to post")
    return {"ok": True, "item_id": item.id, "status": item.status}


@router.post("/pipeline")
def run_pipeline(target_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Run full pipeline (scrape → download → caption → post) in background."""
    target = db.query(TargetAccount).get(target_id)
    if not target:
        raise HTTPException(404, "Target account not found")

    def _run():
        from backend.models.database import SessionLocal
        db2 = SessionLocal()
        try:
            t = db2.query(TargetAccount).get(target_id)
            run_full_pipeline(db2, t)
        finally:
            db2.close()

    background_tasks.add_task(_run)
    return {"ok": True, "message": "Full pipeline running in background"}


@router.get("/stats")
def content_stats(target_id: int = None, db: Session = Depends(get_db)):
    q = db.query(ContentItem)
    if target_id:
        q = q.filter_by(target_account_id=target_id)

    return {
        "total": q.count(),
        "pending": q.filter(ContentItem.status == ContentStatus.PENDING).count(),
        "downloaded": q.filter(ContentItem.status == ContentStatus.DOWNLOADED).count(),
        "queued": q.filter(ContentItem.status == ContentStatus.QUEUED).count(),
        "uploaded": q.filter(ContentItem.status == ContentStatus.UPLOADED).count(),
        "failed": q.filter(ContentItem.status == ContentStatus.FAILED).count(),
        "skipped": q.filter(ContentItem.status == ContentStatus.SKIPPED).count(),
    }
