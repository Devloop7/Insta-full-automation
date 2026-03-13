import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings:
    # App
    APP_NAME: str = "InstaBot Dashboard"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")

    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/data/bot.db"

    # Paths
    DOWNLOADS_DIR: Path = BASE_DIR / "downloads"
    LOGS_DIR: Path = BASE_DIR / "logs"
    SESSION_DIR: Path = BASE_DIR / "sessions"

    # MiniMax AI
    MINIMAX_API_KEY: str = os.getenv("MINIMAX_API_KEY", "")
    MINIMAX_GROUP_ID: str = os.getenv("MINIMAX_GROUP_ID", "")
    MINIMAX_MODEL: str = os.getenv("MINIMAX_MODEL", "abab6.5s-chat")

    # Instagram defaults
    INSTAGRAM_DELAY_MIN: int = int(os.getenv("INSTAGRAM_DELAY_MIN", "30"))   # seconds between actions
    INSTAGRAM_DELAY_MAX: int = int(os.getenv("INSTAGRAM_DELAY_MAX", "120"))  # seconds between actions
    MAX_LIKES_PER_HOUR: int = int(os.getenv("MAX_LIKES_PER_HOUR", "30"))
    MAX_COMMENTS_PER_HOUR: int = int(os.getenv("MAX_COMMENTS_PER_HOUR", "10"))
    MAX_POSTS_PER_DAY: int = int(os.getenv("MAX_POSTS_PER_DAY", "6"))

settings = Settings()

# Ensure dirs exist
for d in [settings.DOWNLOADS_DIR, settings.LOGS_DIR, settings.SESSION_DIR, BASE_DIR / "data"]:
    d.mkdir(parents=True, exist_ok=True)
