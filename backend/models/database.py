from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime,
    Float, Text, Enum as SAEnum, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import enum
from backend.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Enums ──────────────────────────────────────────────────────────────────

class ContentType(str, enum.Enum):
    REEL = "reel"
    POST = "post"
    STORY = "story"

class ContentStatus(str, enum.Enum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    QUEUED = "queued"
    UPLOADED = "uploaded"
    FAILED = "failed"
    SKIPPED = "skipped"

class JobStatus(str, enum.Enum):
    RUNNING = "running"
    IDLE = "idle"
    PAUSED = "paused"
    ERROR = "error"

class AgentAction(str, enum.Enum):
    LIKE = "like"
    COMMENT = "comment"
    FOLLOW = "follow"


# ── Models ─────────────────────────────────────────────────────────────────

class TargetAccount(Base):
    """The account we post TO."""
    __tablename__ = "target_accounts"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    niche = Column(String, default="general")
    niche_keywords = Column(Text, default="")          # comma-separated
    niche_description = Column(Text, default="")       # free-form for AI context
    is_active = Column(Boolean, default=True)
    session_file = Column(String, default="")          # path to instagrapi session
    followers_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    posts_count = Column(Integer, default=0)
    last_sync = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    source_accounts = relationship("SourceAccount", back_populates="target_account")
    content_items = relationship("ContentItem", back_populates="target_account")
    agent_logs = relationship("AgentLog", back_populates="target_account")
    schedules = relationship("Schedule", back_populates="target_account")


class SourceAccount(Base):
    """Accounts we SCRAPE content from."""
    __tablename__ = "source_accounts"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    target_account_id = Column(Integer, ForeignKey("target_accounts.id"))
    scrape_reels = Column(Boolean, default=True)
    scrape_posts = Column(Boolean, default=True)
    scrape_stories = Column(Boolean, default=False)
    max_items_per_scrape = Column(Integer, default=10)
    is_active = Column(Boolean, default=True)
    last_scraped = Column(DateTime, nullable=True)
    total_scraped = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    target_account = relationship("TargetAccount", back_populates="source_accounts")
    content_items = relationship("ContentItem", back_populates="source_account")


class ContentItem(Base):
    """A piece of content in the pipeline."""
    __tablename__ = "content_items"

    id = Column(Integer, primary_key=True)
    source_account_id = Column(Integer, ForeignKey("source_accounts.id"))
    target_account_id = Column(Integer, ForeignKey("target_accounts.id"))
    instagram_media_id = Column(String, unique=True, nullable=True)
    content_type = Column(SAEnum(ContentType), nullable=False)
    status = Column(SAEnum(ContentStatus), default=ContentStatus.PENDING)
    original_url = Column(Text, default="")
    local_path = Column(Text, default="")
    caption = Column(Text, default="")
    original_caption = Column(Text, default="")
    hashtags = Column(Text, default="")
    thumbnail_path = Column(Text, default="")
    duration = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    uploaded_at = Column(DateTime, nullable=True)
    error_msg = Column(Text, default="")
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    source_account = relationship("SourceAccount", back_populates="content_items")
    target_account = relationship("TargetAccount", back_populates="content_items")


class Schedule(Base):
    """Posting schedule config per target account."""
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)
    target_account_id = Column(Integer, ForeignKey("target_accounts.id"))
    name = Column(String, default="Default Schedule")
    is_active = Column(Boolean, default=True)

    # Scraping
    scrape_interval_hours = Column(Integer, default=6)
    scrape_enabled = Column(Boolean, default=True)

    # Posting
    post_times = Column(Text, default="09:00,13:00,18:00,21:00")  # comma-separated HH:MM
    post_enabled = Column(Boolean, default=True)
    max_posts_per_day = Column(Integer, default=4)

    # Agent
    agent_enabled = Column(Boolean, default=True)
    agent_interval_minutes = Column(Integer, default=30)
    agent_like_enabled = Column(Boolean, default=True)
    agent_comment_enabled = Column(Boolean, default=True)
    agent_max_likes_per_run = Column(Integer, default=10)
    agent_max_comments_per_run = Column(Integer, default=3)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    target_account = relationship("TargetAccount", back_populates="schedules")


class AgentLog(Base):
    """Log of every AI agent action."""
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True)
    target_account_id = Column(Integer, ForeignKey("target_accounts.id"))
    action = Column(SAEnum(AgentAction), nullable=False)
    target_username = Column(String, default="")
    target_media_id = Column(String, default="")
    comment_text = Column(Text, default="")
    success = Column(Boolean, default=True)
    error_msg = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    target_account = relationship("TargetAccount", back_populates="agent_logs")


class BotLog(Base):
    """General bot activity log."""
    __tablename__ = "bot_logs"

    id = Column(Integer, primary_key=True)
    level = Column(String, default="INFO")   # INFO, WARNING, ERROR
    category = Column(String, default="general")
    message = Column(Text, nullable=False)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


def create_tables():
    Base.metadata.create_all(bind=engine)
