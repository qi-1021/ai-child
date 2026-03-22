"""
Tests for the social media / RSS learning pipeline (ai/social_learner.py)
and REST endpoints (api/social.py).
"""
import ipaddress
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models import RSSFeed, RSSItem


# ── URL validation ────────────────────────────────────────────────────────────

def test_validate_feed_url_accepts_http():
    from ai.social_learner import validate_feed_url
    # Public http URL must not raise
    with patch("ai.social_learner.socket.getaddrinfo") as mock_ga:
        mock_ga.return_value = [(None, None, None, None, ("93.184.216.34", 0))]
        # Should not raise
        validate_feed_url("http://example.com/feed.xml")


def test_validate_feed_url_accepts_https():
    from ai.social_learner import validate_feed_url
    with patch("ai.social_learner.socket.getaddrinfo") as mock_ga:
        mock_ga.return_value = [(None, None, None, None, ("93.184.216.34", 0))]
        validate_feed_url("https://example.com/feed.xml")


def test_validate_feed_url_rejects_ftp():
    from ai.social_learner import validate_feed_url
    with pytest.raises(HTTPException) as exc_info:
        validate_feed_url("ftp://example.com/feed.xml")
    assert exc_info.value.status_code == 400


def test_validate_feed_url_rejects_localhost():
    from ai.social_learner import validate_feed_url
    with patch("ai.social_learner.socket.getaddrinfo") as mock_ga:
        mock_ga.return_value = [(None, None, None, None, ("127.0.0.1", 0))]
        with pytest.raises(HTTPException) as exc_info:
            validate_feed_url("http://localhost/feed.xml")
    assert exc_info.value.status_code == 400


def test_validate_feed_url_rejects_private_ip():
    from ai.social_learner import validate_feed_url
    with patch("ai.social_learner.socket.getaddrinfo") as mock_ga:
        mock_ga.return_value = [(None, None, None, None, ("192.168.1.1", 0))]
        with pytest.raises(HTTPException):
            validate_feed_url("http://internal-server.local/feed")


def test_validate_feed_url_rejects_unresolvable():
    from ai.social_learner import validate_feed_url
    with patch("ai.social_learner.socket.getaddrinfo", side_effect=socket.gaierror):
        with pytest.raises(HTTPException) as exc_info:
            validate_feed_url("http://this-domain-does-not-exist-xyz.invalid/feed")
    assert exc_info.value.status_code == 400


def test_validate_feed_url_rejects_missing_hostname():
    from ai.social_learner import validate_feed_url
    with pytest.raises(HTTPException):
        validate_feed_url("http:///feed.xml")


# ── RSS parsing ───────────────────────────────────────────────────────────────

RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>http://example.com</link>
    <item>
      <title>Article One</title>
      <link>http://example.com/1</link>
      <description>First article content here.</description>
      <guid>http://example.com/1</guid>
    </item>
    <item>
      <title>Article Two</title>
      <link>http://example.com/2</link>
      <description>Second article content.</description>
    </item>
  </channel>
</rss>"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Test</title>
  <entry>
    <id>urn:uuid:1234</id>
    <title>Atom Article</title>
    <summary>Atom summary text.</summary>
    <link href="http://example.com/atom/1"/>
  </entry>
</feed>"""

BROKEN_XML = "<this is not < valid xml"


def test_parse_rss_feed():
    from ai.social_learner import parse_feed
    items = parse_feed(RSS_SAMPLE)
    assert len(items) == 2
    assert items[0]["title"] == "Article One"
    assert items[0]["guid"] == "http://example.com/1"
    assert "First article" in items[0]["body"]
    assert items[1]["title"] == "Article Two"


def test_parse_atom_feed():
    from ai.social_learner import parse_feed
    items = parse_feed(ATOM_SAMPLE)
    assert len(items) == 1
    assert items[0]["guid"] == "urn:uuid:1234"
    assert items[0]["title"] == "Atom Article"
    assert "Atom summary" in items[0]["body"]


def test_parse_broken_xml_returns_empty():
    from ai.social_learner import parse_feed
    items = parse_feed(BROKEN_XML)
    assert items == []


def test_parse_feed_fallback_guid_on_missing():
    """If guid and link are absent, a sha256 hash of title is used."""
    xml = """<rss version="2.0"><channel>
      <item><title>Unique Title</title><description>body</description></item>
    </channel></rss>"""
    from ai.social_learner import parse_feed
    items = parse_feed(xml)
    assert len(items) == 1
    assert len(items[0]["guid"]) == 64  # sha256 hex digest


# ── Summarisation ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summarise_uses_llm():
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Concise summary."))]
    mock_llm = MagicMock()
    mock_llm.chat = MagicMock()
    mock_llm.chat.completions = MagicMock()
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_resp)

    with (
        patch("ai.social_learner.get_llm_client", return_value=mock_llm),
        patch("ai.social_learner.get_active_model", return_value="gpt-4o"),
        patch("ai.social_learner.settings") as ms,
    ):
        ms.rss_summarise_enabled = True
        from ai.social_learner import _summarise
        result = await _summarise("Test Title", "Long article body.", "Test Feed")
    assert result == "Concise summary."


@pytest.mark.asyncio
async def test_summarise_disabled_returns_raw():
    with patch("ai.social_learner.settings") as ms:
        ms.rss_summarise_enabled = False
        from ai.social_learner import _summarise
        result = await _summarise("Title", "Body text.", "Feed")
    assert "Title" in result
    assert "Body text." in result


# ── Feed ingestion ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_feed_new_items(session):
    """New RSS items get stored as knowledge; duplicates are skipped."""
    feed = RSSFeed(name="Test", url="http://example.com/feed.xml")
    session.add(feed)
    await session.commit()
    await session.refresh(feed)

    with (
        patch("ai.social_learner._fetch_feed_xml", new=AsyncMock(return_value=RSS_SAMPLE)),
        patch("ai.social_learner._summarise", new=AsyncMock(return_value="Summarised.")),
        patch("ai.social_learner.add_knowledge", new=AsyncMock(return_value=MagicMock(id=1, topic="t", content="c"))),
        patch("ai.social_learner.store_embedding", new=AsyncMock()),
        patch("ai.social_learner.asyncio.create_task", return_value=None),
    ):
        from ai.social_learner import ingest_feed
        count = await ingest_feed(session, feed)

    assert count == 2  # two items in RSS_SAMPLE


@pytest.mark.asyncio
async def test_ingest_feed_skips_duplicates(session):
    """Items already in rss_items table are not re-ingested."""
    feed = RSSFeed(name="Test", url="http://example.com/feed.xml")
    session.add(feed)
    await session.commit()
    await session.refresh(feed)

    # Pre-populate both guids
    session.add(RSSItem(feed_id=feed.id, guid="http://example.com/1"))
    session.add(RSSItem(feed_id=feed.id, guid="http://example.com/2"))
    await session.commit()

    with (
        patch("ai.social_learner._fetch_feed_xml", new=AsyncMock(return_value=RSS_SAMPLE)),
        patch("ai.social_learner.add_knowledge", new=AsyncMock()) as mock_add,
    ):
        from ai.social_learner import ingest_feed
        count = await ingest_feed(session, feed)

    assert count == 0
    mock_add.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_feed_returns_zero_on_fetch_failure(session):
    feed = RSSFeed(name="Broken", url="http://broken.example.com/feed.xml")
    session.add(feed)
    await session.commit()
    await session.refresh(feed)

    with patch("ai.social_learner._fetch_feed_xml", new=AsyncMock(return_value=None)):
        from ai.social_learner import ingest_feed
        count = await ingest_feed(session, feed)
    assert count == 0


# ── Social post webhook ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_social_post():
    with (
        patch("ai.social_learner.async_session") as mock_ctx,
        patch("ai.social_learner.add_knowledge", new=AsyncMock()) as mock_add,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()
        mock_ctx.return_value = mock_session

        from ai.social_learner import ingest_social_post
        await ingest_social_post("twitter", "GPT-5 is announced.", topic="AI", author="user1")

    mock_add.assert_awaited_once()
    call_kwargs = mock_add.call_args
    assert "twitter" in call_kwargs.kwargs.get("topic", "") or "twitter" in str(call_kwargs.args)
    assert call_kwargs.kwargs.get("source") == "social"


# ── poll_all_feeds ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_poll_all_feeds_disabled():
    with patch("ai.social_learner.settings") as ms:
        ms.social_learning_enabled = False
        from ai.social_learner import poll_all_feeds
        total = await poll_all_feeds()
    assert total == 0
