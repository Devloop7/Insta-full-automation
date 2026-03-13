from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from backend.models.database import ContentType, ContentStatus, AgentAction


# ── Target Account ─────────────────────────────────────────────────────────

class TargetAccountCreate(BaseModel):
    username: str
    password: str
    niche: str = "general"
    niche_keywords: str = ""
    niche_description: str = ""

class TargetAccountUpdate(BaseModel):
    password: Optional[str] = None
    niche: Optional[str] = None
    niche_keywords: Optional[str] = None
    niche_description: Optional[str] = None
    is_active: Optional[bool] = None

class TargetAccountOut(BaseModel):
    id: int
    username: str
    niche: str
    niche_keywords: str
    niche_description: str
    is_active: bool
    followers_count: int
    following_count: int
    posts_count: int
    last_sync: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Source Account ─────────────────────────────────────────────────────────

class SourceAccountCreate(BaseModel):
    username: str
    target_account_id: int
    scrape_reels: bool = True
    scrape_posts: bool = True
    scrape_stories: bool = False
    max_items_per_scrape: int = Field(default=10, ge=1, le=50)

class SourceAccountUpdate(BaseModel):
    scrape_reels: Optional[bool] = None
    scrape_posts: Optional[bool] = None
    scrape_stories: Optional[bool] = None
    max_items_per_scrape: Optional[int] = None
    is_active: Optional[bool] = None

class SourceAccountOut(BaseModel):
    id: int
    username: str
    target_account_id: int
    scrape_reels: bool
    scrape_posts: bool
    scrape_stories: bool
    max_items_per_scrape: int
    is_active: bool
    last_scraped: Optional[datetime]
    total_scraped: int
    created_at: datetime

    class Config:
        from_attributes = True


# ── Content ────────────────────────────────────────────────────────────────

class ContentItemOut(BaseModel):
    id: int
    content_type: ContentType
    status: ContentStatus
    caption: str
    original_caption: str
    hashtags: str
    scheduled_at: Optional[datetime]
    uploaded_at: Optional[datetime]
    error_msg: str
    retry_count: int
    created_at: datetime
    source_account_id: Optional[int]
    target_account_id: Optional[int]

    class Config:
        from_attributes = True

class ContentQueueAction(BaseModel):
    action: str  # "approve", "skip", "reschedule"
    scheduled_at: Optional[datetime] = None
    caption: Optional[str] = None
    hashtags: Optional[str] = None


# ── Schedule ───────────────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    target_account_id: int
    name: str = "Default Schedule"
    scrape_interval_hours: int = Field(default=6, ge=1, le=24)
    scrape_enabled: bool = True
    post_times: str = "09:00,13:00,18:00,21:00"
    post_enabled: bool = True
    max_posts_per_day: int = Field(default=4, ge=1, le=12)
    agent_enabled: bool = True
    agent_interval_minutes: int = Field(default=30, ge=10, le=240)
    agent_like_enabled: bool = True
    agent_comment_enabled: bool = True
    agent_max_likes_per_run: int = Field(default=10, ge=1, le=50)
    agent_max_comments_per_run: int = Field(default=3, ge=1, le=15)

class ScheduleOut(BaseModel):
    id: int
    target_account_id: int
    name: str
    is_active: bool
    scrape_interval_hours: int
    scrape_enabled: bool
    post_times: str
    post_enabled: bool
    max_posts_per_day: int
    agent_enabled: bool
    agent_interval_minutes: int
    agent_like_enabled: bool
    agent_comment_enabled: bool
    agent_max_likes_per_run: int
    agent_max_comments_per_run: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Agent Log ──────────────────────────────────────────────────────────────

class AgentLogOut(BaseModel):
    id: int
    action: AgentAction
    target_username: str
    comment_text: str
    success: bool
    error_msg: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Bot Log ────────────────────────────────────────────────────────────────

class BotLogOut(BaseModel):
    id: int
    level: str
    category: str
    message: str
    details: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Dashboard Stats ────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_uploaded: int
    total_pending: int
    total_queued: int
    total_failed: int
    likes_today: int
    comments_today: int
    source_accounts_count: int
    target_accounts_count: int
    last_post_at: Optional[datetime]
    last_scrape_at: Optional[datetime]


# ── Scrape Trigger ─────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    target_account_id: int
    source_account_ids: Optional[List[int]] = None  # None = all active


class AgentRunRequest(BaseModel):
    target_account_id: int
    like_count: int = Field(default=5, ge=1, le=50)
    comment_count: int = Field(default=2, ge=0, le=10)
    hashtags: Optional[List[str]] = None   # search by hashtag if provided
