"""
Instagram service — wraps instagrapi with session management,
safe delays, and download/upload helpers.
"""
import random
import time
import os
import logging
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, TwoFactorRequired, ChallengeRequired,
    ClientError, MediaNotFound, UserNotFound
)

from backend.core.config import settings

logger = logging.getLogger("instabot.instagram")


def _safe_delay(min_s: int = None, max_s: int = None):
    """Random human-like delay."""
    lo = min_s or settings.INSTAGRAM_DELAY_MIN
    hi = max_s or settings.INSTAGRAM_DELAY_MAX
    t = random.uniform(lo, hi)
    logger.debug(f"Sleeping {t:.1f}s")
    time.sleep(t)


class InstagramClient:
    """
    One InstagramClient instance per target account.
    Stores session to disk so we don't re-login every time.
    """

    def __init__(self, username: str, password: str, session_file: str = ""):
        self.username = username
        self.password = password
        self.session_file = session_file or str(
            settings.SESSION_DIR / f"{username}.json"
        )
        self._client: Optional[Client] = None

    # ── Login / Session ────────────────────────────────────────────────────

    def login(self) -> bool:
        cl = Client()
        cl.delay_range = [
            settings.INSTAGRAM_DELAY_MIN,
            settings.INSTAGRAM_DELAY_MAX
        ]
        # Try loading existing session first
        if os.path.exists(self.session_file):
            try:
                cl.load_settings(self.session_file)
                cl.login(self.username, self.password)
                cl.dump_settings(self.session_file)
                self._client = cl
                logger.info(f"Restored session for @{self.username}")
                return True
            except Exception as e:
                logger.warning(f"Session restore failed for @{self.username}: {e}")

        # Fresh login
        try:
            cl.login(self.username, self.password)
            cl.dump_settings(self.session_file)
            self._client = cl
            logger.info(f"Fresh login success for @{self.username}")
            return True
        except TwoFactorRequired:
            raise ValueError("2FA required — disable 2FA or handle manually.")
        except ChallengeRequired:
            raise ValueError("Instagram challenge required — solve in-app first.")
        except Exception as e:
            logger.error(f"Login failed for @{self.username}: {e}")
            raise

    def ensure_logged_in(self):
        if self._client is None:
            self.login()

    @property
    def cl(self) -> Client:
        self.ensure_logged_in()
        return self._client

    def get_account_info(self) -> dict:
        try:
            info = self.cl.account_info()
            return {
                "followers_count": info.follower_count,
                "following_count": info.following_count,
                "posts_count": info.media_count,
            }
        except Exception as e:
            logger.error(f"get_account_info failed: {e}")
            return {}

    # ── Scraping ───────────────────────────────────────────────────────────

    def get_user_id(self, username: str) -> Optional[int]:
        try:
            return self.cl.user_id_from_username(username)
        except UserNotFound:
            logger.warning(f"User not found: @{username}")
            return None
        except Exception as e:
            logger.error(f"get_user_id({username}) error: {e}")
            return None

    def scrape_user_reels(self, username: str, amount: int = 10) -> List[dict]:
        """Returns list of media info dicts."""
        uid = self.get_user_id(username)
        if not uid:
            return []
        try:
            medias = self.cl.user_clips(uid, amount=amount)
            return [self._media_to_dict(m) for m in medias]
        except Exception as e:
            logger.error(f"scrape_user_reels({username}) error: {e}")
            return []

    def scrape_user_posts(self, username: str, amount: int = 10) -> List[dict]:
        uid = self.get_user_id(username)
        if not uid:
            return []
        try:
            medias = self.cl.user_medias(uid, amount=amount)
            return [self._media_to_dict(m) for m in medias]
        except Exception as e:
            logger.error(f"scrape_user_posts({username}) error: {e}")
            return []

    def scrape_user_stories(self, username: str) -> List[dict]:
        uid = self.get_user_id(username)
        if not uid:
            return []
        try:
            stories = self.cl.user_stories(uid)
            return [self._story_to_dict(s) for s in stories]
        except Exception as e:
            logger.error(f"scrape_user_stories({username}) error: {e}")
            return []

    def _media_to_dict(self, m) -> dict:
        return {
            "media_id": str(m.id),
            "media_type": m.media_type,   # 1=photo, 2=video, 8=album
            "product_type": getattr(m, "product_type", ""),
            "caption": m.caption_text or "",
            "thumbnail_url": str(m.thumbnail_url) if m.thumbnail_url else "",
            "video_url": str(m.video_url) if getattr(m, "video_url", None) else "",
            "resources": [
                {"url": str(r.video_url or r.thumbnail_url), "type": "video" if r.video_url else "photo"}
                for r in (m.resources or [])
            ],
            "duration": getattr(m, "video_duration", None),
            "width": m.width,
            "height": m.height,
            "like_count": m.like_count,
            "taken_at": m.taken_at.isoformat() if m.taken_at else "",
        }

    def _story_to_dict(self, s) -> dict:
        return {
            "media_id": str(s.id),
            "media_type": s.media_type,
            "caption": s.caption_text or "",
            "video_url": str(s.video_url) if getattr(s, "video_url", None) else "",
            "thumbnail_url": str(s.thumbnail_url) if s.thumbnail_url else "",
            "duration": getattr(s, "video_duration", None),
            "width": s.width,
            "height": s.height,
            "taken_at": s.taken_at.isoformat() if s.taken_at else "",
        }

    # ── Download ───────────────────────────────────────────────────────────

    def download_media(self, media_dict: dict, dest_dir: Path) -> Optional[Path]:
        """Download a media item. Returns local path or None."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        media_id = media_dict["media_id"]
        try:
            media = self.cl.media_info(media_id)
            path = self.cl.video_download(media_id, folder=dest_dir) \
                if media.media_type == 2 \
                else self.cl.photo_download(media_id, folder=dest_dir)
            logger.info(f"Downloaded {media_id} → {path}")
            return path
        except MediaNotFound:
            logger.warning(f"Media {media_id} not found / private")
            return None
        except Exception as e:
            logger.error(f"download_media({media_id}) error: {e}")
            return None

    # ── Upload ─────────────────────────────────────────────────────────────

    def upload_reel(self, video_path: str, caption: str) -> Optional[str]:
        """Upload as Reel. Returns media id or None."""
        try:
            _safe_delay(10, 20)
            m = self.cl.clip_upload(Path(video_path), caption=caption)
            logger.info(f"Uploaded reel: {m.id}")
            return str(m.id)
        except Exception as e:
            logger.error(f"upload_reel error: {e}")
            return None

    def upload_photo(self, photo_path: str, caption: str) -> Optional[str]:
        try:
            _safe_delay(10, 20)
            m = self.cl.photo_upload(Path(photo_path), caption=caption)
            logger.info(f"Uploaded photo: {m.id}")
            return str(m.id)
        except Exception as e:
            logger.error(f"upload_photo error: {e}")
            return None

    def upload_story_video(self, video_path: str) -> Optional[str]:
        try:
            _safe_delay(5, 15)
            m = self.cl.video_upload_to_story(Path(video_path))
            logger.info(f"Uploaded story video: {m.id}")
            return str(m.id)
        except Exception as e:
            logger.error(f"upload_story_video error: {e}")
            return None

    def upload_story_photo(self, photo_path: str) -> Optional[str]:
        try:
            _safe_delay(5, 15)
            m = self.cl.photo_upload_to_story(Path(photo_path))
            logger.info(f"Uploaded story photo: {m.id}")
            return str(m.id)
        except Exception as e:
            logger.error(f"upload_story_photo error: {e}")
            return None

    # ── Engagement ─────────────────────────────────────────────────────────

    def like_media(self, media_id: str) -> bool:
        try:
            _safe_delay(5, 15)
            result = self.cl.media_like(media_id)
            logger.info(f"Liked media {media_id}: {result}")
            return result
        except Exception as e:
            logger.error(f"like_media({media_id}) error: {e}")
            return False

    def comment_media(self, media_id: str, text: str) -> bool:
        try:
            _safe_delay(10, 25)
            c = self.cl.media_comment(media_id, text)
            logger.info(f"Commented on {media_id}: {text[:40]}")
            return c is not None
        except Exception as e:
            logger.error(f"comment_media({media_id}) error: {e}")
            return False

    def get_hashtag_medias(self, hashtag: str, amount: int = 20) -> List[dict]:
        """Get top medias for a hashtag."""
        try:
            tag = hashtag.lstrip("#")
            medias = self.cl.hashtag_medias_top(tag, amount=amount)
            return [self._media_to_dict(m) for m in medias]
        except Exception as e:
            logger.error(f"get_hashtag_medias({hashtag}) error: {e}")
            return []

    def get_similar_account_medias(self, username: str, amount: int = 10) -> List[dict]:
        """Get recent medias from an account (for agent engagement)."""
        uid = self.get_user_id(username)
        if not uid:
            return []
        try:
            medias = self.cl.user_medias(uid, amount=amount)
            return [self._media_to_dict(m) for m in medias]
        except Exception as e:
            logger.error(f"get_similar_account_medias({username}) error: {e}")
            return []

    def follow_user(self, username: str) -> bool:
        uid = self.get_user_id(username)
        if not uid:
            return False
        try:
            _safe_delay(5, 15)
            result = self.cl.user_follow(uid)
            logger.info(f"Followed @{username}: {result}")
            return result
        except Exception as e:
            logger.error(f"follow_user({username}) error: {e}")
            return False


# ── Client cache (one instance per username) ───────────────────────────────

_client_cache: dict[str, InstagramClient] = {}

def get_instagram_client(username: str, password: str, session_file: str = "") -> InstagramClient:
    if username not in _client_cache:
        client = InstagramClient(username, password, session_file)
        _client_cache[username] = client
    return _client_cache[username]

def clear_client_cache(username: str = None):
    if username:
        _client_cache.pop(username, None)
    else:
        _client_cache.clear()
