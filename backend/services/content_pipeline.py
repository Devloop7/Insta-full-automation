"""
Content pipeline:
  1. Scrape → creates ContentItem rows with PENDING status
  2. Download → downloads media, status → DOWNLOADED
  3. Caption generation → rewrite with AI
  4. Queue → status → QUEUED (scheduled for posting)
  5. Post → upload to target account, status → UPLOADED
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.database import (
    ContentItem, ContentType, ContentStatus,
    SourceAccount, TargetAccount, BotLog
)
from backend.services.instagram import get_instagram_client
from backend.services.minimax import get_minimax_client

logger = logging.getLogger("instabot.pipeline")


def _log(db: Session, level: str, category: str, message: str, details: str = ""):
    db.add(BotLog(level=level, category=category, message=message, details=details))
    db.commit()


# ── Step 1: Scrape ─────────────────────────────────────────────────────────

def scrape_source_account(
    db: Session,
    source: SourceAccount,
    target: TargetAccount
) -> int:
    """Scrape content from a source account. Returns number of new items found."""
    client = get_instagram_client(target.username, target.password, target.session_file)

    new_items = 0

    def _already_exists(media_id: str) -> bool:
        return db.query(ContentItem).filter_by(instagram_media_id=media_id).first() is not None

    def _create_item(media: dict, ctype: ContentType):
        nonlocal new_items
        if _already_exists(media["media_id"]):
            return
        item = ContentItem(
            source_account_id=source.id,
            target_account_id=target.id,
            instagram_media_id=media["media_id"],
            content_type=ctype,
            status=ContentStatus.PENDING,
            original_caption=media.get("caption", ""),
            caption=media.get("caption", ""),
            original_url=media.get("video_url") or media.get("thumbnail_url", ""),
            duration=media.get("duration"),
            width=media.get("width"),
            height=media.get("height"),
        )
        db.add(item)
        new_items += 1

    try:
        if source.scrape_reels:
            reels = client.scrape_user_reels(source.username, source.max_items_per_scrape)
            for r in reels:
                _create_item(r, ContentType.REEL)
            logger.info(f"Scraped {len(reels)} reels from @{source.username}")

        if source.scrape_posts:
            posts = client.scrape_user_posts(source.username, source.max_items_per_scrape)
            for p in posts:
                # Skip videos as reels if already scraped
                if p.get("product_type") == "clips":
                    continue
                _create_item(p, ContentType.POST)
            logger.info(f"Scraped {len(posts)} posts from @{source.username}")

        if source.scrape_stories:
            stories = client.scrape_user_stories(source.username)
            for s in stories:
                _create_item(s, ContentType.STORY)
            logger.info(f"Scraped {len(stories)} stories from @{source.username}")

        source.last_scraped = datetime.utcnow()
        source.total_scraped += new_items
        db.commit()
        _log(db, "INFO", "scrape", f"Scraped @{source.username}: +{new_items} new items")

    except Exception as e:
        logger.error(f"scrape_source_account failed for @{source.username}: {e}")
        _log(db, "ERROR", "scrape", f"Scrape failed for @{source.username}", str(e))

    return new_items


# ── Step 2: Download ───────────────────────────────────────────────────────

def download_pending_items(
    db: Session,
    target: TargetAccount,
    limit: int = 20
) -> int:
    """Download PENDING content items. Returns count downloaded."""
    items = (
        db.query(ContentItem)
        .filter_by(target_account_id=target.id, status=ContentStatus.PENDING)
        .limit(limit)
        .all()
    )

    client = get_instagram_client(target.username, target.password, target.session_file)
    downloaded = 0

    for item in items:
        dest_dir = settings.DOWNLOADS_DIR / str(target.id) / str(item.id)
        media_dict = {
            "media_id": item.instagram_media_id,
            "media_type": 2 if item.content_type in (ContentType.REEL,) else 1,
        }

        path = client.download_media(media_dict, dest_dir)
        if path:
            item.local_path = str(path)
            item.status = ContentStatus.DOWNLOADED
            downloaded += 1
        else:
            item.status = ContentStatus.FAILED
            item.error_msg = "Download failed"

        db.commit()

    _log(db, "INFO", "download", f"Downloaded {downloaded}/{len(items)} items for @{target.username}")
    return downloaded


# ── Step 3: AI Caption ─────────────────────────────────────────────────────

def generate_captions_for_downloaded(
    db: Session,
    target: TargetAccount,
    limit: int = 20
) -> int:
    """Generate AI captions for DOWNLOADED items. Returns count processed."""
    items = (
        db.query(ContentItem)
        .filter_by(target_account_id=target.id, status=ContentStatus.DOWNLOADED)
        .limit(limit)
        .all()
    )

    ai = get_minimax_client()
    processed = 0

    for item in items:
        try:
            caption = ai.generate_caption(
                niche=target.niche,
                niche_description=target.niche_description,
                niche_keywords=target.niche_keywords,
                original_caption=item.original_caption,
                include_hashtags=True,
                hashtag_count=20,
            )
            item.caption = caption
            item.status = ContentStatus.QUEUED
            processed += 1
        except Exception as e:
            logger.error(f"Caption generation failed for item {item.id}: {e}")
            item.status = ContentStatus.QUEUED   # still queue with original caption

        db.commit()

    _log(db, "INFO", "caption", f"Generated captions for {processed}/{len(items)} items")
    return processed


# ── Step 4: Post ───────────────────────────────────────────────────────────

def post_next_queued_item(
    db: Session,
    target: TargetAccount
) -> Optional[ContentItem]:
    """Post the next QUEUED item. Returns the item or None."""
    item = (
        db.query(ContentItem)
        .filter(
            ContentItem.target_account_id == target.id,
            ContentItem.status == ContentStatus.QUEUED,
        )
        .filter(
            (ContentItem.scheduled_at == None) |
            (ContentItem.scheduled_at <= datetime.utcnow())
        )
        .order_by(ContentItem.scheduled_at.asc().nullsfirst(), ContentItem.created_at.asc())
        .first()
    )

    if not item:
        return None

    if not item.local_path or not Path(item.local_path).exists():
        item.status = ContentStatus.FAILED
        item.error_msg = "Local file missing"
        db.commit()
        _log(db, "ERROR", "post", f"File missing for item {item.id}")
        return None

    client = get_instagram_client(target.username, target.password, target.session_file)

    media_id = None
    try:
        if item.content_type == ContentType.REEL:
            media_id = client.upload_reel(item.local_path, item.caption)
        elif item.content_type == ContentType.POST:
            # Determine if video or photo by extension
            ext = Path(item.local_path).suffix.lower()
            if ext in (".mp4", ".mov", ".avi"):
                media_id = client.upload_reel(item.local_path, item.caption)
            else:
                media_id = client.upload_photo(item.local_path, item.caption)
        elif item.content_type == ContentType.STORY:
            ext = Path(item.local_path).suffix.lower()
            if ext in (".mp4", ".mov"):
                media_id = client.upload_story_video(item.local_path)
            else:
                media_id = client.upload_story_photo(item.local_path)

        if media_id:
            item.status = ContentStatus.UPLOADED
            item.uploaded_at = datetime.utcnow()
            item.error_msg = ""
            _log(db, "INFO", "post", f"Posted {item.content_type} for @{target.username}", f"media_id={media_id}")
        else:
            item.retry_count += 1
            if item.retry_count >= 3:
                item.status = ContentStatus.FAILED
                item.error_msg = "Upload returned None after 3 retries"
            _log(db, "WARNING", "post", f"Upload returned None for item {item.id}")

    except Exception as e:
        item.retry_count += 1
        item.error_msg = str(e)
        if item.retry_count >= 3:
            item.status = ContentStatus.FAILED
        logger.error(f"post item {item.id} error: {e}")
        _log(db, "ERROR", "post", f"Post failed for item {item.id}", str(e))

    db.commit()

    # Clean up local file after successful upload
    if item.status == ContentStatus.UPLOADED and item.local_path:
        try:
            p = Path(item.local_path)
            if p.exists():
                shutil.rmtree(p.parent, ignore_errors=True)
        except Exception:
            pass

    return item


def post_queued_items(
    db: Session,
    target: TargetAccount,
    max_posts: int = 1
) -> int:
    """Post up to max_posts queued items. Returns number posted."""
    posted = 0
    for _ in range(max_posts):
        item = post_next_queued_item(db, target)
        if item and item.status == ContentStatus.UPLOADED:
            posted += 1
        else:
            break
    return posted


# ── Full pipeline run ──────────────────────────────────────────────────────

def run_full_pipeline(db: Session, target: TargetAccount):
    """Scrape → Download → Caption → Post in one call."""
    # 1. Scrape all active source accounts
    sources = [s for s in target.source_accounts if s.is_active]
    for source in sources:
        scrape_source_account(db, source, target)

    # 2. Download
    download_pending_items(db, target)

    # 3. Caption
    generate_captions_for_downloaded(db, target)

    # 4. Post (1 at a time per pipeline run, respecting schedule)
    post_queued_items(db, target, max_posts=1)
