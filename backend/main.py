"""
InstaBot — FastAPI backend entry point.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.core.config import settings
from backend.models.database import create_tables
from backend.core.scheduler import start_scheduler, stop_scheduler
from backend.routers import accounts, content, agent, logs
from backend.routers.scheduler_router import router as scheduler_router

# ── Logging setup ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.LOGS_DIR / "bot.log"),
    ],
)
logger = logging.getLogger("instabot")


# ── Lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== InstaBot starting up ===")
    create_tables()
    start_scheduler()
    yield
    logger.info("=== InstaBot shutting down ===")
    stop_scheduler()


# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(accounts.router)
app.include_router(content.router)
app.include_router(agent.router)
app.include_router(scheduler_router)
app.include_router(logs.router)


# ── Dashboard stats endpoint ───────────────────────────────────────────────
@app.get("/api/dashboard")
def dashboard_stats():
    from backend.models.database import SessionLocal, ContentItem, ContentStatus, AgentLog, AgentAction, TargetAccount, SourceAccount
    from datetime import date, datetime
    db = SessionLocal()
    try:
        today = date.today()
        today_start = datetime(today.year, today.month, today.day)

        last_post = (
            db.query(ContentItem)
            .filter_by(status=ContentStatus.UPLOADED)
            .order_by(ContentItem.uploaded_at.desc())
            .first()
        )
        last_scrape_src = (
            db.query(SourceAccount)
            .order_by(SourceAccount.last_scraped.desc())
            .first()
        )

        return {
            "total_uploaded": db.query(ContentItem).filter_by(status=ContentStatus.UPLOADED).count(),
            "total_pending": db.query(ContentItem).filter_by(status=ContentStatus.PENDING).count(),
            "total_queued": db.query(ContentItem).filter_by(status=ContentStatus.QUEUED).count(),
            "total_failed": db.query(ContentItem).filter_by(status=ContentStatus.FAILED).count(),
            "likes_today": db.query(AgentLog).filter(
                AgentLog.action == AgentAction.LIKE,
                AgentLog.created_at >= today_start,
                AgentLog.success == True,
            ).count(),
            "comments_today": db.query(AgentLog).filter(
                AgentLog.action == AgentAction.COMMENT,
                AgentLog.created_at >= today_start,
                AgentLog.success == True,
            ).count(),
            "source_accounts_count": db.query(SourceAccount).filter_by(is_active=True).count(),
            "target_accounts_count": db.query(TargetAccount).filter_by(is_active=True).count(),
            "last_post_at": last_post.uploaded_at.isoformat() if last_post and last_post.uploaded_at else None,
            "last_scrape_at": last_scrape_src.last_scraped.isoformat() if last_scrape_src and last_scrape_src.last_scraped else None,
        }
    finally:
        db.close()


# ── Serve frontend ─────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

    @app.get("/", response_class=FileResponse)
    def serve_dashboard():
        return str(FRONTEND_DIR / "index.html")

    @app.get("/{path:path}", response_class=FileResponse)
    def serve_spa(path: str):
        target = FRONTEND_DIR / path
        if target.exists() and target.is_file():
            return str(target)
        return str(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
