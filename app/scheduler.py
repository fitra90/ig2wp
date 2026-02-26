"""
Scheduler – runs the IG → WP sync job on a configurable interval.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.utils.logger import get_logger
from app.services import instagram, wordpress

logger = get_logger("ig2wp.scheduler")

scheduler = AsyncIOScheduler()


# ---------------------------------------------------------------------------
# Core sync logic
# ---------------------------------------------------------------------------

async def sync_posts() -> dict:
    """Fetch new IG posts and publish them to WordPress.

    Returns:
        A summary dict with ``synced``, ``skipped``, and ``errors`` counts.
    """
    result = {"synced": 0, "skipped": 0, "errors": 0, "details": []}

    try:
        ig_posts = await instagram.fetch_recent_posts(limit=20)
    except Exception as exc:
        logger.error("Failed to fetch IG posts: %s", exc)
        result["errors"] += 1
        result["details"].append(f"IG fetch error: {exc}")
        return result

    try:
        existing = await wordpress.get_existing_ig_permalinks()
    except Exception as exc:
        logger.error("Failed to get existing WP posts: %s", exc)
        result["errors"] += 1
        result["details"].append(f"WP fetch error: {exc}")
        return result

    for post in ig_posts:
        permalink = post.get("permalink", "")

        # Skip already-published posts
        if permalink in existing:
            result["skipped"] += 1
            continue

        try:
            # Prepare content
            caption = post.get("caption", "")
            title = _extract_title(caption)
            content = _format_content(caption, permalink)

            # Upload featured image
            media_url = await instagram.get_post_media_url(post)
            featured_id = 0
            if media_url:
                featured_id = await wordpress.upload_media(
                    media_url,
                    filename=f"ig_{post['id']}.jpg",
                )

            # Create WP post
            await wordpress.create_post(
                title=title,
                content=content,
                featured_media_id=featured_id,
                ig_permalink=permalink,
            )

            result["synced"] += 1
            logger.info("✓ Synced IG post %s → WordPress.", post["id"])

        except Exception as exc:
            result["errors"] += 1
            result["details"].append(f"Post {post.get('id')}: {exc}")
            logger.error("✗ Failed to sync IG post %s: %s", post.get("id"), exc)

    logger.info(
        "Sync complete — synced: %d, skipped: %d, errors: %d.",
        result["synced"],
        result["skipped"],
        result["errors"],
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_title(caption: str, max_length: int = 80) -> str:
    """Derive a post title from the first line of an IG caption."""
    first_line = caption.split("\n", 1)[0].strip()
    if len(first_line) > max_length:
        return first_line[:max_length].rsplit(" ", 1)[0] + "…"
    return first_line or "Instagram Post"


def _format_content(caption: str, permalink: str) -> str:
    """Turn an IG caption into WordPress HTML content."""
    # Convert newlines to <br> tags for readable formatting
    html_caption = caption.replace("\n", "<br>\n")
    parts = [html_caption]

    if permalink:
        parts.append(
            f'<p><a href="{permalink}" target="_blank" rel="noopener">'
            f"View original post on Instagram</a></p>"
        )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    """Start the APScheduler background job."""
    scheduler.add_job(
        sync_posts,
        trigger=IntervalTrigger(minutes=settings.sync_interval_minutes),
        id="ig_wp_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started – syncing every %d minute(s).",
        settings.sync_interval_minutes,
    )


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
