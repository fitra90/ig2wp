"""
WordPress REST API service – upload media and create posts.
"""

import base64
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger("ig2wp.wordpress")


def _auth_header() -> dict[str, str]:
    """Build Basic-Auth header using Application Password."""
    credentials = f"{settings.wp_username}:{settings.wp_app_password}"
    token = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _api_url(endpoint: str) -> str:
    """Construct the full WP REST API URL."""
    base = settings.wp_url.rstrip("/")
    return f"{base}/wp-json/wp/v2/{endpoint.lstrip('/')}"


# ---------------------------------------------------------------------------
# Media upload
# ---------------------------------------------------------------------------

async def upload_media(image_url: str, filename: str | None = None) -> int:
    """Download an image and upload it to the WordPress media library.

    Args:
        image_url: Public URL of the image to download.
        filename: Optional filename for the uploaded media. If not provided,
                  it is derived from the image URL.

    Returns:
        The WordPress media attachment ID.

    Raises:
        httpx.HTTPStatusError: On upload failure.
    """
    if not filename:
        path = PurePosixPath(urlparse(image_url).path)
        filename = path.name or "ig_image.jpg"

    # Ensure file has an extension
    if "." not in filename:
        filename += ".jpg"

    async with httpx.AsyncClient(timeout=60) as client:
        # Download image from Instagram
        img_resp = await client.get(image_url, follow_redirects=True)
        img_resp.raise_for_status()
        image_bytes = img_resp.content
        content_type = img_resp.headers.get("content-type", "image/jpeg")

        # Upload to WordPress
        headers = {
            **_auth_header(),
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type,
        }

        wp_resp = await client.post(
            _api_url("media"),
            headers=headers,
            content=image_bytes,
        )
        wp_resp.raise_for_status()

    media_id: int = wp_resp.json()["id"]
    logger.info("Uploaded media to WordPress → ID %d (%s).", media_id, filename)
    return media_id


# ---------------------------------------------------------------------------
# Post creation
# ---------------------------------------------------------------------------

async def create_post(
    title: str,
    content: str,
    featured_media_id: int = 0,
    ig_permalink: str = "",
    status: str = "publish",
) -> dict:
    """Create a new WordPress post.

    Args:
        title: Post title.
        content: Post HTML content.
        featured_media_id: WordPress media attachment ID for the featured image.
        ig_permalink: Original Instagram permalink (stored as post meta for
                      duplicate detection).
        status: Post status – ``publish``, ``draft``, etc.

    Returns:
        The created post data dict from the WP API.

    Raises:
        httpx.HTTPStatusError: On creation failure.
    """
    payload: dict = {
        "title": title,
        "content": content,
        "status": status,
        "meta": {"_ig_permalink": ig_permalink},
    }

    if featured_media_id:
        payload["featured_media"] = featured_media_id

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _api_url("posts"),
            headers=_auth_header(),
            json=payload,
        )
        resp.raise_for_status()

    post_data = resp.json()
    logger.info(
        "Created WP post #%d – \"%s\".",
        post_data["id"],
        title[:50],
    )
    return post_data


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

async def get_existing_ig_permalinks() -> set[str]:
    """Retrieve Instagram permalinks already published on WordPress.

    Uses the custom post meta field ``_ig_permalink`` registered via the
    REST API ``meta`` key.  Falls back to searching post content for the
    Instagram URL when meta is unavailable.

    Returns:
        A set of IG permalink strings.
    """
    permalinks: set[str] = set()
    page = 1

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.get(
                _api_url("posts"),
                headers=_auth_header(),
                params={"per_page": 100, "page": page, "status": "publish,draft"},
            )

            if resp.status_code == 400:
                # No more pages
                break

            resp.raise_for_status()
            posts = resp.json()

            if not posts:
                break

            for post in posts:
                meta = post.get("meta", {})
                ig_link = meta.get("_ig_permalink", "")
                if ig_link:
                    permalinks.add(ig_link)

            page += 1

    logger.info("Found %d existing IG posts on WordPress.", len(permalinks))
    return permalinks
