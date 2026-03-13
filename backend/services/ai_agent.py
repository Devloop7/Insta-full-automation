"""
AI Agent — autonomously likes and comments on Instagram content
using MiniMax to generate niche-aware, human-like comments.

Strategy:
  - Find content via source account feeds OR hashtag search
  - Like posts that match the niche
  - Comment with AI-generated niche-relevant text
  - Respect rate limits to avoid bans
"""
import logging
import random
from datetime import datetime, date
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models.database import (
    AgentLog, AgentAction, BotLog,
    TargetAccount, SourceAccount, Schedule
)
from backend.services.instagram import get_instagram_client
from backend.services.minimax import get_minimax_client

logger = logging.getLogger("instabot.agent")


def _count_today_actions(db: Session, target_id: int, action: AgentAction) -> int:
    """Count how many times this action was done today for a target."""
    today = date.today()
    return (
        db.query(AgentLog)
        .filter(
            AgentLog.target_account_id == target_id,
            AgentLog.action == action,
            AgentLog.created_at >= datetime(today.year, today.month, today.day),
        )
        .count()
    )


def _log_action(
    db: Session,
    target_id: int,
    action: AgentAction,
    target_username: str,
    target_media_id: str,
    comment_text: str = "",
    success: bool = True,
    error: str = "",
):
    db.add(AgentLog(
        target_account_id=target_id,
        action=action,
        target_username=target_username,
        target_media_id=target_media_id,
        comment_text=comment_text,
        success=success,
        error_msg=error,
    ))
    db.add(BotLog(
        level="INFO" if success else "WARNING",
        category="agent",
        message=f"{action.value} on @{target_username}/{target_media_id} → {'✓' if success else '✗'}",
        details=comment_text or error,
    ))
    db.commit()


class InstagramAgent:
    """
    Autonomous engagement agent for one target account.
    Uses the target account's credentials to like/comment.
    """

    def __init__(self, target: TargetAccount, schedule: Schedule):
        self.target = target
        self.schedule = schedule
        self.ai = get_minimax_client()

    def _client(self):
        return get_instagram_client(
            self.target.username,
            self.target.password,
            self.target.session_file,
        )

    def _get_target_medias(self) -> List[dict]:
        """
        Collect media to engage with:
        1. Posts from source accounts (same niche)
        2. Hashtag-based discovery
        """
        client = self._client()
        medias: List[dict] = []

        # From source accounts
        for src in self.target.source_accounts:
            if src.is_active:
                m = client.get_similar_account_medias(src.username, amount=8)
                medias.extend(m)

        # From niche hashtags
        keywords = [k.strip() for k in self.target.niche_keywords.split(",") if k.strip()]
        hashtags_to_try = keywords[:3]  # limit API calls

        if not hashtags_to_try and self.target.niche:
            hashtags_to_try = [self.target.niche.replace(" ", "")]

        for tag in hashtags_to_try:
            m = client.get_hashtag_medias(tag, amount=10)
            medias.extend(m)

        # Shuffle and deduplicate
        seen = set()
        unique = []
        for m in medias:
            if m["media_id"] not in seen:
                seen.add(m["media_id"])
                unique.append(m)

        random.shuffle(unique)
        return unique

    def run_like_session(self, db: Session, max_likes: int) -> int:
        """Like up to max_likes posts. Returns number liked."""
        today_likes = _count_today_actions(db, self.target.id, AgentAction.LIKE)
        if today_likes >= settings_likes_limit():
            logger.info(f"@{self.target.username}: daily like limit reached")
            return 0

        remaining = min(max_likes, settings_likes_limit() - today_likes)
        if remaining <= 0:
            return 0

        medias = self._get_target_medias()
        client = self._client()
        liked = 0

        for media in medias:
            if liked >= remaining:
                break
            # Skip already-liked (basic check via agent log)
            already = (
                db.query(AgentLog)
                .filter_by(
                    target_account_id=self.target.id,
                    action=AgentAction.LIKE,
                    target_media_id=media["media_id"]
                )
                .first()
            )
            if already:
                continue

            success = client.like_media(media["media_id"])
            username = media.get("username", "unknown")
            _log_action(db, self.target.id, AgentAction.LIKE, username, media["media_id"], success=success)

            if success:
                liked += 1

        logger.info(f"@{self.target.username}: liked {liked} posts")
        return liked

    def run_comment_session(self, db: Session, max_comments: int) -> int:
        """Comment on up to max_comments posts. Returns number commented."""
        today_comments = _count_today_actions(db, self.target.id, AgentAction.COMMENT)
        if today_comments >= settings_comments_limit():
            logger.info(f"@{self.target.username}: daily comment limit reached")
            return 0

        remaining = min(max_comments, settings_comments_limit() - today_comments)
        if remaining <= 0:
            return 0

        medias = self._get_target_medias()
        # Prefer medias with captions for better AI comments
        medias_with_caption = [m for m in medias if m.get("caption")]
        medias_without = [m for m in medias if not m.get("caption")]
        ordered = medias_with_caption + medias_without

        client = self._client()
        commented = 0
        styles = ["natural", "question", "compliment", "emoji_heavy"]

        for media in ordered:
            if commented >= remaining:
                break

            # Don't comment twice on same media
            already = (
                db.query(AgentLog)
                .filter_by(
                    target_account_id=self.target.id,
                    action=AgentAction.COMMENT,
                    target_media_id=media["media_id"]
                )
                .first()
            )
            if already:
                continue

            # Generate AI comment
            style = random.choice(styles)
            comment_text = self.ai.generate_comment(
                niche=self.target.niche,
                niche_description=self.target.niche_description,
                niche_keywords=self.target.niche_keywords,
                caption=media.get("caption", ""),
                comment_style=style,
            )

            if not comment_text:
                continue

            success = client.comment_media(media["media_id"], comment_text)
            username = media.get("username", "unknown")
            _log_action(
                db, self.target.id, AgentAction.COMMENT,
                username, media["media_id"],
                comment_text=comment_text,
                success=success,
            )

            if success:
                commented += 1

        logger.info(f"@{self.target.username}: commented on {commented} posts")
        return commented

    def run(self, db: Session) -> dict:
        """Full agent run: likes + comments."""
        results = {"likes": 0, "comments": 0}

        if self.schedule.agent_like_enabled:
            results["likes"] = self.run_like_session(db, self.schedule.agent_max_likes_per_run)

        if self.schedule.agent_comment_enabled:
            results["comments"] = self.run_comment_session(db, self.schedule.agent_max_comments_per_run)

        logger.info(f"Agent run for @{self.target.username}: {results}")
        return results


def settings_likes_limit() -> int:
    from backend.core.config import settings
    return settings.MAX_LIKES_PER_HOUR * 24  # daily

def settings_comments_limit() -> int:
    from backend.core.config import settings
    return settings.MAX_COMMENTS_PER_HOUR * 24  # daily


def run_agent_for_target(db: Session, target: TargetAccount) -> dict:
    """Entry point: find active schedule and run agent."""
    schedule = (
        db.query(Schedule)
        .filter_by(target_account_id=target.id, is_active=True)
        .first()
    )
    if not schedule:
        return {"error": "No active schedule found"}
    if not schedule.agent_enabled:
        return {"skipped": "Agent disabled in schedule"}

    agent = InstagramAgent(target, schedule)
    return agent.run(db)
