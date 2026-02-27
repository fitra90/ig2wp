"""
SQLite storage – track scraped & synced Instagram posts locally.

Uses aiosqlite for non-blocking async access.  The DB file is stored
at ``data/ig2wp.db`` and created automatically on first run.
"""

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger("ig2wp.database")

_DB_DIR = Path("data")
_DB_PATH = _DB_DIR / "ig2wp.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS synced_posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ig_shortcode    TEXT    NOT NULL,
    ig_permalink    TEXT    NOT NULL UNIQUE,
    wp_post_id      INTEGER NOT NULL,
    title           TEXT    NOT NULL DEFAULT '',
    synced_at       TEXT    NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create the data directory and ``synced_posts`` table if needed."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute(_CREATE_TABLE_SQL)
        await db.commit()

    logger.info("SQLite database ready at %s.", _DB_PATH)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

async def is_already_synced(ig_permalink: str) -> bool:
    """Check whether an IG permalink has already been synced.

    Args:
        ig_permalink: The Instagram post permalink.

    Returns:
        ``True`` if the post exists in the database.
    """
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT 1 FROM synced_posts WHERE ig_permalink = ? LIMIT 1",
            (ig_permalink,),
        )
        row = await cursor.fetchone()
    return row is not None


async def record_sync(
    ig_shortcode: str,
    ig_permalink: str,
    wp_post_id: int,
    title: str = "",
) -> None:
    """Record a successfully synced post.

    Args:
        ig_shortcode: Instagram post shortcode.
        ig_permalink: Full Instagram permalink URL.
        wp_post_id: WordPress post ID returned after creation.
        title: Post title sent to WordPress.
    """
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO synced_posts
                (ig_shortcode, ig_permalink, wp_post_id, title, synced_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ig_shortcode, ig_permalink, wp_post_id, title, now),
        )
        await db.commit()

    logger.info("Recorded sync: %s -> WP #%d.", ig_permalink, wp_post_id)


async def get_sync_history(limit: int = 20) -> list[dict]:
    """Return the most recent synced posts.

    Args:
        limit: Maximum rows to return.

    Returns:
        A list of dicts with post data.
    """
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM synced_posts ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()

    return [dict(row) for row in rows]
