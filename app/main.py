"""
IG → WordPress Auto-Poster – FastAPI entrypoint.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.scheduler import start_scheduler, stop_scheduler, sync_posts
from app.services import instagram
from app.utils.logger import get_logger

logger = get_logger("ig2wp.main")


# ---------------------------------------------------------------------------
# Lifespan – start & stop the scheduler with the app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage scheduler lifecycle alongside the FastAPI app."""
    logger.info("Starting IG → WP Auto-Poster …")
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Shutting down IG → WP Auto-Poster.")


app = FastAPI(
    title="IG → WP Auto-Poster",
    description="Sync Instagram posts to WordPress automatically.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Simple health check."""
    return {"status": "ok"}


@app.get("/sync")
async def trigger_sync():
    """Manually trigger the IG → WP sync process."""
    logger.info("Manual sync triggered via /sync endpoint.")
    try:
        result = await sync_posts()
        return {"status": "completed", **result}
    except Exception as exc:
        logger.error("Sync failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc)},
        )


@app.get("/posts")
async def preview_posts(limit: int = 10):
    """Preview latest IG posts without syncing to WordPress.

    Args:
        limit: Number of posts to fetch (query param, default 10).
    """
    try:
        posts = await instagram.fetch_recent_posts(limit=limit)
        return {"count": len(posts), "posts": posts}
    except Exception as exc:
        logger.error("Failed to fetch IG posts: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"status": "error", "detail": str(exc)},
        )
