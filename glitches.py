"""مراقب القلتشات وطرق الفلوس الجديدة."""

import json
import logging
import re

import brain
import config
import db
import prompts
import sources

log = logging.getLogger("glitches")


def _parse_candidates(text: str) -> list[int]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        return [int(c["index"]) for c in data.get("candidates", []) if "index" in c]
    except (ValueError, KeyError, TypeError):
        return []


async def check() -> str | None:
    """يرجع نص تنبيه لو فيه قلتش/طريقة جديدة مؤكدة، وإلا None."""
    items = await sources.collect(
        hours=config.GLITCH_INTERVAL_HOURS + 2, yt_query="GTA 6 money glitch"
    )
    fresh = [i for i in items if sources.looks_like_glitch(i) and not db.is_seen("glitch:" + i.url)]
    for i in fresh:
        db.mark_seen("glitch:" + i.url, "glitch", i.title)
    if not fresh:
        return None

    fresh = fresh[:25]
    listing = "\n\n".join(i.line(n) for n, i in enumerate(fresh))

    # فلترة رخيصة بـ Haiku بدون بحث
    filt, _ = await brain.run(
        [{"role": "user", "content": f"{prompts.GLITCH_FILTER}\n\n{listing}"}],
        config.TEXT_MODEL,
        "أنت فلتر دقيق. رد بـ JSON فقط.",
        max_searches=0,
        max_tokens=400,
        use_tools=False,
    )
    idx = [n for n in _parse_candidates(filt) if 0 <= n < len(fresh)]
    if not idx:
        return None

    # تأكيد بـ Sonnet مع البحث
    picked = "\n\n".join(fresh[n].line(n) for n in idx)
    known = "\n".join(db.recent_seen_titles("alert", 10)) or "(ما فيه)"
    text, urls = await brain.run(
        [{"role": "user", "content": f"{prompts.GLITCH_VERIFY}\n\nتنبيهات أرسلتها قبل (لا تكررها):\n{known}\n\nالعناصر:\n{picked}"}],
        config.SMART_MODEL,
        prompts.system_prompt(),
        config.MAX_SEARCHES_CHAT,
        max_tokens=1000,
    )
    if not text or text.strip().upper().startswith("SKIP"):
        return None
    db.mark_seen("alert:" + text[:120], "alert", text.split("\n", 1)[0][:120])
    return brain.with_sources(text, urls)
