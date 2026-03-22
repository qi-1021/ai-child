"""
Social media learning pipeline.

The AI child can subscribe to RSS/Atom feeds and learn from them
continuously — just like a child reading the news each morning.

Architecture
------------
  1. Admin adds feed URLs via  POST /social/rss
  2. Background task polls feeds every ``rss_poll_interval_minutes``.
  3. Each new item is:
       a. Fetched and parsed (stdlib xml.etree — no extra dependency).
       b. Optionally summarised by the LLM into a compact knowledge string.
       c. Stored as a KnowledgeItem with source="social" and confidence=60.
       d. Embedded for semantic search (background task).
  4. Knowledge from social feeds is treated with lower confidence than
     user-taught facts, reflecting that social media content may be
     incomplete or unverified.

Social media webhook
--------------------
  External platforms (Twitter/X, Discord, WeChat, Weibo, …) can push
  posts directly to  POST /social/webhook  using the generic payload format.
  The AI stores each post as a social knowledge item immediately.

SSRF protection
---------------
  Feed URLs are validated before the first HTTP request:
    - http:// and https:// only
    - Hostname must resolve to a publicly routable IP
    - Private, loopback, link-local, and reserved ranges are rejected
"""

import hashlib
import ipaddress
import logging
import socket
import xml.etree.ElementTree as ET
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm_provider import get_active_model, get_llm_client
from ai.memory import add_knowledge
from ai.vector_store import store_embedding
from config import settings
from models import RSSFeed, RSSItem, async_session

logger = logging.getLogger(__name__)

# XML namespaces used by Atom feeds
_ATOM_NS = "http://www.w3.org/2005/Atom"

# Confidence level assigned to socially-sourced knowledge
_SOCIAL_CONFIDENCE = 60


# ── SSRF protection ───────────────────────────────────────────────────────────

def validate_feed_url(url: str) -> None:
    """
    Validate an RSS feed URL against SSRF attacks.

    Raises ``HTTPException(400)`` when the URL fails any policy check:
      - Must be http:// or https://
      - Hostname must resolve to a public (non-private/loopback/reserved) IP

    Note: http:// is allowed (many RSS endpoints do not use TLS), but
    requests are made without following redirects to reduce risk.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="Feed URL must start with http:// or https://",
        )
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: missing hostname.")
    try:
        resolved_ip = socket.getaddrinfo(hostname, None)[0][4][0]
        ip_obj = ipaddress.ip_address(resolved_ip)
    except (socket.gaierror, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not resolve hostname: {hostname}",
        ) from exc
    if (
        ip_obj.is_loopback
        or ip_obj.is_private
        or ip_obj.is_link_local
        or ip_obj.is_reserved
        or ip_obj.is_multicast
    ):
        raise HTTPException(
            status_code=400,
            detail="Feed URL resolves to a private or reserved address.",
        )


# ── RSS / Atom parsing ────────────────────────────────────────────────────────

def _item_guid(item_el: ET.Element, ns: str) -> str:
    """
    Derive a stable unique identifier for an RSS/Atom item.

    Checks (in order): explicit guid/id, link, then falls back to a hash
    of the title text so there is always a value.
    """
    # Atom: <id>
    id_el = item_el.find(f"{{{ns}}}id") if ns else None
    if id_el is not None and id_el.text:
        return id_el.text.strip()
    # RSS: <guid>
    guid_el = item_el.find("guid")
    if guid_el is not None and guid_el.text:
        return guid_el.text.strip()
    # <link>
    link_el = item_el.find(f"{{{ns}}}link") if ns else item_el.find("link")
    if link_el is not None and link_el.text:
        return link_el.text.strip()
    # Atom link element (href attribute)
    if ns:
        link_el = item_el.find(f"{{{ns}}}link")
        if link_el is not None:
            href = link_el.get("href", "")
            if href:
                return href.strip()
    # Fallback: hash of title
    title_el = item_el.find(f"{{{ns}}}title") if ns else item_el.find("title")
    title = (title_el.text or "") if title_el is not None else ""
    return hashlib.sha256(title.encode()).hexdigest()


def _item_text(item_el: ET.Element, ns: str) -> tuple[str, str]:
    """
    Return (title, body) for an RSS/Atom item element.

    Body is the best available text: content → summary/description → title.
    """
    def _txt(tag: str, atom_ns: str = "") -> str:
        full_tag = f"{{{atom_ns}}}{tag}" if atom_ns else tag
        el = item_el.find(full_tag)
        return (el.text or "").strip() if el is not None else ""

    if ns:
        # Atom
        title = _txt("title", ns)
        body = _txt("content", ns) or _txt("summary", ns) or title
    else:
        # RSS
        title = _txt("title")
        body = _txt("description") or _txt("content:encoded") or title

    # Truncate very long bodies
    return title, body[:2000]


def parse_feed(xml_text: str) -> list[dict]:
    """
    Parse an RSS 2.0 or Atom 1.0 feed and return a list of item dicts.

    Each dict has: guid, title, body (truncated to 2000 chars).
    Returns an empty list on any parse error.
    """
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Feed XML parse error: %s", exc)
        return items

    tag = root.tag
    if tag == f"{{{_ATOM_NS}}}feed":
        # Atom
        ns = _ATOM_NS
        entries = root.findall(f"{{{ns}}}entry")
        for entry in entries:
            guid = _item_guid(entry, ns)
            title, body = _item_text(entry, ns)
            items.append({"guid": guid, "title": title, "body": body})
    else:
        # RSS 2.0 (root is <rss> or <rdf:RDF>)
        channel = root.find("channel")
        entries = channel.findall("item") if channel is not None else root.findall("item")
        for entry in entries:
            guid = _item_guid(entry, "")
            title, body = _item_text(entry, "")
            items.append({"guid": guid, "title": title, "body": body})

    return items


# ── LLM summarisation ─────────────────────────────────────────────────────────

async def _summarise(title: str, body: str, feed_name: str) -> str:
    """
    Ask the LLM to distil an article into a single concise fact sentence.

    Falls back to the raw body (truncated) on any error or when summarisation
    is disabled.
    """
    if not settings.rss_summarise_enabled:
        return f"{title}: {body[:500]}" if title else body[:500]

    prompt = (
        f"The following is an article from '{feed_name}'.\n\n"
        f"Title: {title}\n"
        f"Content: {body[:1200]}\n\n"
        f"Summarise the key factual information in one or two concise sentences. "
        f"Do not include opinions or speculation. "
        f"Write in third person. Return only the summary, no extra text."
    )
    try:
        client = get_llm_client()
        resp = await client.chat.completions.create(
            model=get_active_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=160,
            temperature=0.2,
        )
        summary = (resp.choices[0].message.content or "").strip()
        return summary or body[:500]
    except Exception as exc:
        logger.warning("Social learner: LLM summarisation failed: %s", exc)
        return f"{title}: {body[:500]}" if title else body[:500]


# ── Feed ingestion ────────────────────────────────────────────────────────────

async def _fetch_feed_xml(url: str) -> Optional[str]:
    """Fetch the raw XML text of an RSS/Atom feed. Returns None on failure."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=15,
            headers={"User-Agent": "AI-Child-RSS/1.0"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("Social learner: failed to fetch feed %s: %s", url, exc)
        return None


async def ingest_feed(session: AsyncSession, feed: RSSFeed) -> int:
    """
    Fetch and process one RSS/Atom feed.

    Returns the count of new items ingested. Already-seen items (tracked by
    guid in the rss_items table) are silently skipped.
    """
    xml_text = await _fetch_feed_xml(feed.url)
    if xml_text is None:
        return 0

    items = parse_feed(xml_text)
    if not items:
        return 0

    # Load already-ingested guids for this feed
    result = await session.execute(
        select(RSSItem.guid).where(RSSItem.feed_id == feed.id)
    )
    seen_guids = {row[0] for row in result.all()}

    new_count = 0
    for item in items:
        guid = item["guid"]
        if guid in seen_guids:
            continue

        title = item["title"]
        body = item["body"]
        if not body.strip():
            continue

        # Summarise and store as knowledge
        summary = await _summarise(title, body, feed.name)
        topic = f"[{feed.name}] {title}"[:200]
        knowledge_item = await add_knowledge(
            session,
            topic=topic,
            content=summary,
            source="social",
            confidence=_SOCIAL_CONFIDENCE,
        )
        # Embed asynchronously (fire and forget — the caller's session stays open)
        asyncio.create_task(store_embedding(session, knowledge_item))

        # Record the guid so we never ingest this item again
        session.add(RSSItem(feed_id=feed.id, guid=guid))
        seen_guids.add(guid)
        new_count += 1

        logger.debug("Social learner: ingested '%s' from %s", title[:60], feed.name)

    if new_count:
        feed.item_count = (feed.item_count or 0) + new_count
        feed.last_polled_at = datetime.now(timezone.utc)
        await session.commit()
        logger.info(
            "Social learner: %d new items from '%s'", new_count, feed.name
        )

    return new_count


async def ingest_social_post(
    source: str,
    content: str,
    topic: Optional[str] = None,
    author: Optional[str] = None,
) -> None:
    """
    Store a single social media post (received via webhook) as knowledge.

    Opens its own DB session so it can be called from a background task.
    """
    topic_str = topic or source
    display_topic = f"[{source}] {topic_str}"[:200]
    author_prefix = f"From @{author}: " if author else ""
    async with async_session() as session:
        await add_knowledge(
            session,
            topic=display_topic,
            content=f"{author_prefix}{content[:1000]}",
            source="social",
            confidence=_SOCIAL_CONFIDENCE,
        )
        await session.commit()


# ── Polling scheduler ─────────────────────────────────────────────────────────

async def poll_all_feeds() -> int:
    """
    Poll all active RSS feeds and learn from any new items.

    Opens its own DB session. Returns the total number of new items ingested.
    """
    if not settings.social_learning_enabled:
        return 0

    total = 0
    async with async_session() as session:
        result = await session.execute(
            select(RSSFeed).where(RSSFeed.active == True)
        )
        feeds = result.scalars().all()
        for feed in feeds:
            try:
                count = await ingest_feed(session, feed)
                total += count
            except Exception as exc:
                logger.exception(
                    "Social learner: error polling feed '%s': %s", feed.name, exc
                )

    return total


async def rss_poll_scheduler() -> None:
    """
    Asyncio background task: polls all RSS feeds on a configurable interval.

    Does nothing if social_learning_enabled is False.
    """
    if not settings.social_learning_enabled:
        logger.info("RSS poll scheduler disabled — skipping.")
        return

    interval = settings.rss_poll_interval_minutes * 60
    logger.info(
        "RSS poll scheduler started (interval=%d min).",
        settings.rss_poll_interval_minutes,
    )
    while True:
        await asyncio.sleep(interval)
        try:
            total = await poll_all_feeds()
            if total:
                logger.info("RSS poll complete: %d new items ingested.", total)
        except Exception as exc:
            logger.exception("RSS poll scheduler error: %s", exc)
