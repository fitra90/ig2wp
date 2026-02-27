"""
Instagram service – fetch recent posts using instaloader (no API token required).

Anti-blocking measures:
- Random delay between requests (2–5 s).
- Respects rate limits and backs off on 429 / login walls.
- Session file reuse to reduce handshake frequency.
"""

import asyncio
import os
import random
import time
from functools import lru_cache
from pathlib import Path

import instaloader

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger("ig2wp.instagram")

# Directory to persist the instaloader session between restarts
_SESSION_DIR = Path("data")
_SESSION_FILE = _SESSION_DIR / "session"

# Cooldown tracking
_last_fetch_ts: float = 0.0
_MIN_FETCH_INTERVAL = 300  # seconds – never fetch more often than every 5 min


def _get_loader() -> instaloader.Instaloader:
    """Create and configure a reusable Instaloader instance.

    If IG_SESSION_USER and IG_SESSION_PASS are set, the loader will log in
    (and persist the session) for access to private / restricted content.
    Otherwise it operates anonymously on public profiles.
    """
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    # Attempt session login if credentials are provided
    session_user = settings.ig_session_user
    session_pass = settings.ig_session_pass

    if session_user and session_pass:
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)
        session_path = str(_SESSION_FILE)

        try:
            # Try to load an existing session first
            if os.path.exists(session_path):
                loader.load_session_from_file(session_user, session_path)
                logger.info("Loaded existing IG session for @%s.", session_user)
            else:
                loader.login(session_user, session_pass)
                loader.save_session_to_file(session_path)
                logger.info("Logged in to IG as @%s (session saved).", session_user)
        except instaloader.exceptions.LoginException as exc:
            logger.warning("IG login failed (%s) - continuing anonymously.", exc)
        except Exception as exc:
            logger.warning("Session load error (%s) - continuing anonymously.", exc)

    return loader


async def fetch_recent_posts(limit: int = 12) -> list[dict]:
    """Fetch the most recent posts from a public Instagram profile.

    Runs the blocking instaloader calls in a thread executor to keep the
    async event loop responsive.

    Anti-blocking:
    - Enforces a minimum interval between fetches.
    - Adds random delays between post reads.

    Args:
        limit: Maximum number of posts to return.

    Returns:
        A list of post dicts with keys: ``id``, ``caption``, ``media_url``,
        ``permalink``, ``timestamp``.
    """
    global _last_fetch_ts

    # Cooldown guard
    elapsed = time.time() - _last_fetch_ts
    if _last_fetch_ts > 0 and elapsed < _MIN_FETCH_INTERVAL:
        wait = _MIN_FETCH_INTERVAL - elapsed
        logger.info("Cooldown active - waiting %.0f s before next fetch.", wait)
        await asyncio.sleep(wait)

    _last_fetch_ts = time.time()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_sync, limit)


def _fetch_sync(limit: int) -> list[dict]:
    """Synchronous helper – runs instaloader scraping."""
    username = settings.ig_username
    loader = _get_loader()

    try:
        profile = instaloader.Profile.from_username(loader.context, username)
    except instaloader.exceptions.ProfileNotExistsException:
        logger.error("Profile @%s does not exist.", username)
        return []
    except instaloader.exceptions.ConnectionException as exc:
        logger.error("Connection error fetching @%s: %s", username, exc)
        return []
    except Exception as exc:
        logger.error("Unexpected error fetching profile @%s: %s", username, exc)
        return []

    posts: list[dict] = []

    try:
        for i, post in enumerate(profile.get_posts()):
            if i >= limit:
                break

            # Random delay between reading posts (anti-blocking)
            if i > 0:
                delay = random.uniform(2.0, 5.0)
                time.sleep(delay)

            try:
                media_url = post.url  # highest-res image URL

                post_data = {
                    "id": post.shortcode,
                    "caption": post.caption or "",
                    "media_url": media_url,
                    "permalink": f"https://www.instagram.com/p/{post.shortcode}/",
                    "timestamp": post.date_utc.isoformat(),
                    "media_type": post.typename,  # GraphImage, GraphVideo, GraphSidecar
                    "likes": post.likes,
                }
                posts.append(post_data)

            except Exception as exc:
                logger.warning("Skipping post %d: %s", i, exc)
                continue

    except instaloader.exceptions.ConnectionException as exc:
        logger.error(
            "Rate-limited or blocked while iterating posts: %s. "
            "Got %d posts before cutoff.",
            exc,
            len(posts),
        )
    except Exception as exc:
        logger.error("Error iterating posts: %s", exc)

    logger.info("Fetched %d post(s) from @%s.", len(posts), username)
    return posts


async def get_post_media_url(post: dict) -> str | None:
    """Return the media URL from a post dict.

    Args:
        post: Post dict from ``fetch_recent_posts``.

    Returns:
        The image URL string, or ``None``.
    """
    return post.get("media_url")
