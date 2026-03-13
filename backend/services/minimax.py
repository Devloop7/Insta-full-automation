"""
MiniMax API client — generates niche-aware, human-like Instagram comments.
Uses the MiniMax chat completion API.
"""
import logging
import random
import httpx
from typing import Optional

from backend.core.config import settings

logger = logging.getLogger("instabot.minimax")

MINIMAX_API_BASE = "https://api.minimax.chat/v1"


class MinimaxClient:
    def __init__(self, api_key: str = None, group_id: str = None):
        self.api_key = api_key or settings.MINIMAX_API_KEY
        self.group_id = group_id or settings.MINIMAX_GROUP_ID
        self.model = settings.MINIMAX_MODEL

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_url(self, path: str) -> str:
        return f"{MINIMAX_API_BASE}{path}?GroupId={self.group_id}"

    def chat(self, system_prompt: str, user_message: str, temperature: float = 0.9) -> Optional[str]:
        """Send a chat completion request. Returns the assistant reply text."""
        if not self.api_key:
            logger.warning("MiniMax API key not set — returning dummy comment")
            return self._fallback_comment()

        payload = {
            "model": self.model,
            "tokens_to_generate": 150,
            "temperature": temperature,
            "messages": [
                {"sender_type": "USER", "text": user_message}
            ],
            "bot_setting": [
                {
                    "bot_name": "InstaCommentBot",
                    "content": system_prompt
                }
            ]
        }

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    self._build_url("/text/chatcompletion"),
                    headers=self._headers(),
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                reply = data.get("reply") or data.get("choices", [{}])[0].get("messages", [{}])[0].get("text", "")
                return reply.strip() if reply else None
        except httpx.HTTPStatusError as e:
            logger.error(f"MiniMax HTTP error: {e.response.status_code} — {e.response.text}")
            return self._fallback_comment()
        except Exception as e:
            logger.error(f"MiniMax request error: {e}")
            return self._fallback_comment()

    def generate_comment(
        self,
        niche: str,
        niche_description: str,
        niche_keywords: str,
        caption: str,
        comment_style: str = "natural"
    ) -> str:
        """
        Generate a genuine, niche-relevant Instagram comment.
        comment_style: "natural" | "question" | "compliment" | "emoji_heavy"
        """
        style_instructions = {
            "natural": "Write a natural, genuine comment like a real person in this niche would write.",
            "question": "Write an engaging question that invites the creator to reply.",
            "compliment": "Write a sincere compliment specific to this content.",
            "emoji_heavy": "Write a short enthusiastic comment with relevant emojis (2-4 emojis).",
        }

        system_prompt = f"""You are an authentic Instagram user deeply interested in the {niche} niche.
Your personality: enthusiastic, genuine, knowledgeable about {niche}.
Niche context: {niche_description or f'Content related to {niche}'}.
Key topics you care about: {niche_keywords or niche}.

RULES:
- Write ONLY the comment text, nothing else
- Keep it under 150 characters
- Sound human and specific to the content
- Never use generic phrases like "great post!" or "nice content"
- Don't use hashtags in comments
- Vary your tone naturally
- {style_instructions.get(comment_style, style_instructions['natural'])}"""

        user_message = f"Write a comment for this Instagram post with caption: \"{caption[:200]}\""

        comment = self.chat(system_prompt, user_message, temperature=0.95)
        if not comment:
            return self._fallback_comment()

        # Clean up: remove quotes if wrapped
        comment = comment.strip('"\'').strip()
        return comment

    def generate_caption(
        self,
        niche: str,
        niche_description: str,
        niche_keywords: str,
        original_caption: str,
        include_hashtags: bool = True,
        hashtag_count: int = 20
    ) -> str:
        """Generate or rewrite a caption for a content piece."""
        system_prompt = f"""You are a social media expert specializing in the {niche} niche.
You write engaging Instagram captions that drive engagement and growth.
Niche: {niche_description or niche}
Keywords: {niche_keywords or niche}

RULES:
- Write the caption text first (2-4 sentences max)
- If asked to include hashtags, add {hashtag_count} relevant hashtags at the end after two line breaks
- Make captions feel authentic, not corporate
- Include a call-to-action when appropriate
- Do NOT include quotation marks around the caption"""

        user_message = f"Write an Instagram caption for this content. Original caption for reference: \"{original_caption[:300]}\""
        if include_hashtags:
            user_message += f"\nInclude {hashtag_count} hashtags relevant to #{niche.replace(' ', '')}."

        caption = self.chat(system_prompt, user_message, temperature=0.85)
        return caption or original_caption

    def _fallback_comment(self) -> str:
        """Use when API key is missing or API fails."""
        fallbacks = [
            "This is exactly what I needed to see today 🔥",
            "The details here are incredible, well done!",
            "Love this perspective, keep it up!",
            "This is next level, seriously impressive 👏",
            "Been waiting for content like this!",
            "You always deliver quality 💯",
            "The effort put into this is obvious 🙌",
            "This deserves way more attention!",
        ]
        return random.choice(fallbacks)


# Singleton
_minimax = None

def get_minimax_client() -> MinimaxClient:
    global _minimax
    if _minimax is None:
        _minimax = MinimaxClient()
    return _minimax
