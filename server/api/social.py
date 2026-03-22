"""
Social media learning endpoints.

RSS feed management
-------------------
  POST   /social/rss          – subscribe to a new RSS/Atom feed
  GET    /social/rss          – list all subscribed feeds
  DELETE /social/rss/{id}     – unsubscribe from a feed
  POST   /social/rss/poll     – manually trigger an immediate poll of all feeds

Generic social media webhook
----------------------------
  POST   /social/webhook      – receive a social media post from any platform
                                (Twitter, Discord, WeChat, Weibo, …)
                                and store it as AI knowledge immediately.
"""
import asyncio
import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.social_learner import (
    ingest_feed,
    ingest_social_post,
    poll_all_feeds,
    validate_feed_url,
)
from models import RSSFeed, get_session
from models.schemas import RSSFeedIn, RSSFeedOut, SocialWebhookIn

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/social", tags=["social"])


# ── RSS feed management ───────────────────────────────────────────────────────

@router.post("/rss", response_model=RSSFeedOut, status_code=201)
async def add_feed(
    body: RSSFeedIn,
    session: AsyncSession = Depends(get_session),
):
    """
    Subscribe to a new RSS/Atom feed.

    The feed URL is validated against SSRF attacks before being stored.
    A background poll is triggered immediately so the first batch of items
    is ingested without waiting for the next scheduled poll.
    """
    validate_feed_url(body.url)

    # Check for duplicates
    result = await session.execute(
        select(RSSFeed).where(RSSFeed.url == body.url)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="A feed with this URL is already subscribed."
        )

    feed = RSSFeed(name=body.name, url=body.url)
    session.add(feed)
    await session.commit()
    await session.refresh(feed)

    # Immediately ingest in background so results appear quickly
    asyncio.create_task(_initial_ingest(feed.id))

    return RSSFeedOut(
        id=feed.id,
        name=feed.name,
        url=feed.url,
        active=feed.active,
        last_polled_at=feed.last_polled_at,
        item_count=feed.item_count,
        created_at=feed.created_at,
    )


async def _initial_ingest(feed_id: int) -> None:
    """Ingest a newly added feed immediately in the background."""
    from models import async_session

    try:
        async with async_session() as session:
            result = await session.execute(select(RSSFeed).where(RSSFeed.id == feed_id))
            feed = result.scalar_one_or_none()
            if feed:
                await ingest_feed(session, feed)
    except Exception as exc:
        logger.exception("Initial feed ingest failed for feed_id=%d: %s", feed_id, exc)


@router.get("/rss", response_model=List[RSSFeedOut])
async def list_feeds(session: AsyncSession = Depends(get_session)):
    """Return all subscribed RSS feeds."""
    result = await session.execute(
        select(RSSFeed).order_by(RSSFeed.created_at.desc())
    )
    feeds = result.scalars().all()
    return [
        RSSFeedOut(
            id=f.id,
            name=f.name,
            url=f.url,
            active=f.active,
            last_polled_at=f.last_polled_at,
            item_count=f.item_count,
            created_at=f.created_at,
        )
        for f in feeds
    ]


@router.delete("/rss/{feed_id}", status_code=204)
async def delete_feed(
    feed_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Unsubscribe from a feed. Past knowledge items are retained."""
    result = await session.execute(select(RSSFeed).where(RSSFeed.id == feed_id))
    feed = result.scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=404, detail="Feed not found.")
    await session.delete(feed)
    await session.commit()


@router.post("/rss/poll")
async def poll_feeds(
    background_tasks: BackgroundTasks,
):
    """
    Manually trigger an immediate poll of all active feeds.

    Returns immediately; the actual ingestion runs in the background.
    """
    background_tasks.add_task(poll_all_feeds)
    return {"message": "RSS poll triggered in background."}


# ── Generic social media webhook ──────────────────────────────────────────────

@router.post("/webhook")
async def social_webhook(
    body: SocialWebhookIn,
    background_tasks: BackgroundTasks,
):
    """
    Receive a social media post from any external platform.

    Platforms can forward content to this endpoint via their webhook/bot
    integrations (Twitter API, Discord bot, Weibo Open Platform, etc.).
    The post is stored as AI knowledge immediately.

    Expected payload::

        {
          "source": "twitter",
          "topic": "artificial intelligence",
          "content": "OpenAI releases GPT-5...",
          "author": "user123",
          "url": "https://twitter.com/..."
        }
    """
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content must not be empty.")

    background_tasks.add_task(
        ingest_social_post,
        body.source,
        body.content,
        body.topic,
        body.author,
    )
    return {"message": "Social post queued for learning."}
