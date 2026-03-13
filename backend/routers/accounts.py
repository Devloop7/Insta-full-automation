from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from backend.models.database import get_db, TargetAccount, SourceAccount
from backend.models.schemas import (
    TargetAccountCreate, TargetAccountUpdate, TargetAccountOut,
    SourceAccountCreate, SourceAccountUpdate, SourceAccountOut,
)
from backend.services.instagram import get_instagram_client, clear_client_cache

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# ── Target accounts ────────────────────────────────────────────────────────

@router.get("/targets", response_model=List[TargetAccountOut])
def list_targets(db: Session = Depends(get_db)):
    return db.query(TargetAccount).all()


@router.post("/targets", response_model=TargetAccountOut)
def create_target(data: TargetAccountCreate, db: Session = Depends(get_db)):
    existing = db.query(TargetAccount).filter_by(username=data.username).first()
    if existing:
        raise HTTPException(400, f"Account @{data.username} already exists")
    account = TargetAccount(**data.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/targets/{account_id}", response_model=TargetAccountOut)
def get_target(account_id: int, db: Session = Depends(get_db)):
    account = db.query(TargetAccount).get(account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    return account


@router.patch("/targets/{account_id}", response_model=TargetAccountOut)
def update_target(account_id: int, data: TargetAccountUpdate, db: Session = Depends(get_db)):
    account = db.query(TargetAccount).get(account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    # Clear cached client if password changed
    if data.password:
        clear_client_cache(account.username)
    return account


@router.delete("/targets/{account_id}")
def delete_target(account_id: int, db: Session = Depends(get_db)):
    account = db.query(TargetAccount).get(account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    clear_client_cache(account.username)
    db.delete(account)
    db.commit()
    return {"ok": True}


@router.post("/targets/{account_id}/login")
def test_login(account_id: int, db: Session = Depends(get_db)):
    """Test Instagram login and sync account stats."""
    account = db.query(TargetAccount).get(account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    try:
        clear_client_cache(account.username)
        client = get_instagram_client(account.username, account.password, account.session_file)
        client.login()
        info = client.get_account_info()
        if info:
            account.followers_count = info.get("followers_count", 0)
            account.following_count = info.get("following_count", 0)
            account.posts_count = info.get("posts_count", 0)
            account.last_sync = datetime.utcnow()
            db.commit()
        return {"ok": True, "info": info}
    except Exception as e:
        raise HTTPException(400, f"Login failed: {e}")


@router.post("/targets/{account_id}/sync")
def sync_stats(account_id: int, db: Session = Depends(get_db)):
    """Refresh follower/post counts."""
    account = db.query(TargetAccount).get(account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    try:
        client = get_instagram_client(account.username, account.password, account.session_file)
        info = client.get_account_info()
        if info:
            account.followers_count = info.get("followers_count", 0)
            account.following_count = info.get("following_count", 0)
            account.posts_count = info.get("posts_count", 0)
            account.last_sync = datetime.utcnow()
            db.commit()
        return {"ok": True, "info": info}
    except Exception as e:
        raise HTTPException(400, f"Sync failed: {e}")


# ── Source accounts ────────────────────────────────────────────────────────

@router.get("/sources", response_model=List[SourceAccountOut])
def list_sources(target_id: int = None, db: Session = Depends(get_db)):
    q = db.query(SourceAccount)
    if target_id:
        q = q.filter_by(target_account_id=target_id)
    return q.all()


@router.post("/sources", response_model=SourceAccountOut)
def create_source(data: SourceAccountCreate, db: Session = Depends(get_db)):
    target = db.query(TargetAccount).get(data.target_account_id)
    if not target:
        raise HTTPException(404, "Target account not found")
    existing = db.query(SourceAccount).filter_by(
        username=data.username,
        target_account_id=data.target_account_id
    ).first()
    if existing:
        raise HTTPException(400, f"@{data.username} already added as source for this account")
    source = SourceAccount(**data.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.patch("/sources/{source_id}", response_model=SourceAccountOut)
def update_source(source_id: int, data: SourceAccountUpdate, db: Session = Depends(get_db)):
    source = db.query(SourceAccount).get(source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(source, field, value)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.query(SourceAccount).get(source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    db.delete(source)
    db.commit()
    return {"ok": True}
