"""
Scheduler - runs the IG -> WP sync job on a configurable interval.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.utils.logger import get_logger
from app.services import instagram, wordpress
from app import database

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

    for post in ig_posts:
        permalink = post.get("permalink", "")

        # Skip already-synced posts (checked against local SQLite DB)
        try:
            if await database.is_already_synced(permalink):
                result["skipped"] += 1
                continue
        except Exception as exc:
            logger.error("DB lookup failed for %s: %s", permalink, exc)
            result["errors"] += 1
            result["details"].append(f"DB lookup error: {exc}")
            continue

        try:
            # Prepare content
            caption = post.get("caption", "")
            title = _extract_title(caption)
            content = _format_content(caption, permalink)

            # Upload featured image
            media_url = post.get("media_url", "")
            featured_id = 0
            if media_url:
                featured_id = await wordpress.upload_media(
                    media_url,
                    filename=f"ig_{post.get('id', 'unknown')}.jpg",
                )

            # Create WP post
            wp_data = await wordpress.create_post(
                title=title,
                content=content,
                featured_media_id=featured_id,
                ig_permalink=permalink,
            )

            # Record in local SQLite DB
            await database.record_sync(
                ig_shortcode=post.get("id", ""),
                ig_permalink=permalink,
                wp_post_id=wp_data.get("id", 0),
                title=title,
            )

            result["synced"] += 1
            logger.info("[OK] Synced IG post %s -> WordPress.", post["id"])

        except Exception as exc:
            result["errors"] += 1
            result["details"].append(f"Post {post.get('id')}: {exc}")
            logger.error("[FAIL] Failed to sync IG post %s: %s", post.get("id"), exc)

    logger.info(
        "Sync complete - synced: %d, skipped: %d, errors: %d.",
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
        return first_line[:max_length].rsplit(" ", 1)[0] + "..."
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
    interval = settings.sync_interval_minutes

    scheduler.add_job(
        sync_posts,
        trigger=IntervalTrigger(minutes=interval),
        id="ig_wp_sync",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    scheduler.start()

    if interval >= 60:
        logger.info("Scheduler started - syncing every %.1f hour(s).", interval / 60)
    else:
        logger.info("Scheduler started - syncing every %d minute(s).", interval)


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
