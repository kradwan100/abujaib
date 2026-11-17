"""جمع الأخبار: RSS للمواقع، Reddit، ويوتيوب."""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

import config

log = logging.getLogger("sources")
UA = {"User-Agent": "Mozilla/5.0 (gta6-money-coach personal bot)"}


@dataclass
class Item:
    source: str
    title: str
    url: str
    summary: str
    published: float  # unix time

    def line(self, i: int) -> str:
        s = self.summary.replace("\n", " ")[:280]
        return f"[{i}] ({self.source}) {self.title}\n{s}\n{self.url}"


def _about_gta(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in config.GTA_KEYWORDS)


def _clean(html: str) -> str:
    import re

    return re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ").strip()


async def _fetch_feed(client: httpx.AsyncClient, name: str, url: str, gta_only: bool) -> list[Item]:
    try:
        r = await client.get(url, headers=UA, timeout=20, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("feed %s failed: %s", name, e)
        return []
    parsed = feedparser.parse(r.content)
    items = []
    for e in parsed.entries[:40]:
        title = e.get("title", "")
        summary = _clean(e.get("summary", ""))
        if gta_only and not _about_gta(f"{title} {summary}"):
            continue
        ts = e.get("published_parsed") or e.get("updated_parsed")
        published = time.mktime(ts) if ts else time.time()
        items.append(Item(name, title, e.get("link", ""), summary, published))
    return items


async def youtube(query: str, hours: int = 24, max_results: int = 8) -> list[Item]:
    if not config.YOUTUBE_API_KEY:
        return []
    after = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": after,
        "maxResults": max_results,
        "key": config.YOUTUBE_API_KEY,
    }
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("youtube failed: %s", e)
        return []
    out = []
    for v in data.get("items", []):
        sn = v.get("snippet", {})
        vid = v.get("id", {}).get("videoId")
        if not vid:
            continue
        out.append(
            Item(
                f"YouTube · {sn.get('channelTitle', '')}",
                sn.get("title", ""),
                f"https://www.youtube.com/watch?v={vid}",
                sn.get("description", ""),
                time.time(),
            )
        )
    return out


async def collect(hours: int = 26, include_youtube: bool = True, yt_query: str = "GTA 6 money") -> list[Item]:
    """كل الجديد من آخر X ساعة."""
    cutoff = time.time() - hours * 3600
    async with httpx.AsyncClient() as c:
        tasks = [_fetch_feed(c, n, u, True) for n, u in config.RSS_FEEDS + config.EXTRA_FEEDS]
        tasks += [_fetch_feed(c, n, u, False) for n, u in config.REDDIT_FEEDS]
        results = await asyncio.gather(*tasks)
    items = [i for group in results for i in group if i.published >= cutoff]
    if include_youtube:
        items += await youtube(yt_query, hours=hours)

    # حذف التكرار
    seen, unique = set(), []
    for i in items:
        if i.url and i.url not in seen:
            seen.add(i.url)
            unique.append(i)
    return unique


def looks_like_glitch(item: Item) -> bool:
    t = f"{item.title} {item.summary}".lower()
    return any(k in t for k in config.GLITCH_KEYWORDS)
