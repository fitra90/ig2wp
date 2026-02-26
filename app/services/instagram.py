"""
Instagram Graph API service – fetch recent posts from a business/creator account.
"""

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger("ig2wp.instagram")

IG_GRAPH_URL = "https://graph.instagram.com"


async def fetch_recent_posts(limit: int = 10) -> list[dict]:
    """Fetch the most recent Instagram posts.

    Args:
        limit: Maximum number of posts to retrieve (default 10).

    Returns:
        A list of post dicts containing id, caption, media_url, etc.

    Raises:
        httpx.HTTPStatusError: If the Graph API returns a non-2xx status.
    """
    fields = "id,caption,media_type,media_url,timestamp,permalink"
    url = f"{IG_GRAPH_URL}/{settings.ig_user_id}/media"

    params = {
        "fields": fields,
        "limit": limit,
        "access_token": settings.ig_access_token,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    posts = data.get("data", [])

    # Keep only IMAGE and CAROUSEL_ALBUM (they have usable media_url)
    supported = {"IMAGE", "CAROUSEL_ALBUM"}
    filtered = [p for p in posts if p.get("media_type") in supported]

    logger.info("Fetched %d posts from Instagram (%d supported).", len(posts), len(filtered))
    return filtered


async def get_post_media_url(post: dict) -> str | None:
    """Extract the best media URL for a given post.

    For CAROUSEL_ALBUM posts the first child image is used.

    Args:
        post: A single post dict from ``fetch_recent_posts``.

    Returns:
        The media URL string, or ``None`` if unavailable.
    """
    if post.get("media_type") == "CAROUSEL_ALBUM":
        # Fetch children to get first image
        url = f"{IG_GRAPH_URL}/{post['id']}/children"
        params = {
            "fields": "id,media_type,media_url",
            "access_token": settings.ig_access_token,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            children = resp.json().get("data", [])

        for child in children:
            if child.get("media_type") == "IMAGE":
                return child.get("media_url")

    return post.get("media_url")
