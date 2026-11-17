"""تقرير الفلوس اليومي."""

import logging

import brain
import config
import db
import prompts
import sources

log = logging.getLogger("daily")


async def build_report() -> str:
    items = await sources.collect(hours=26, yt_query="GTA 6 money")
    fresh = [i for i in items if not db.is_seen("news:" + i.url)]
    for i in fresh:
        db.mark_seen("news:" + i.url, "news", i.title)

    listing = "\n\n".join(i.line(n) for n, i in enumerate(fresh[:30])) or "(ما وصل شي جديد من المصادر اليوم)"
    last = db.get_profile().get("last_report", "")
    user_msg = (
        f"{prompts.DAILY_TASK}\n\n"
        f"آخر تقرير أرسلته (لا تكرره):\n{last[:900] or '(هذا أول تقرير)'}\n\n"
        f"الجديد من المصادر:\n{listing}"
    )
    text, urls = await brain.run(
        [{"role": "user", "content": user_msg}],
        config.SMART_MODEL,
        prompts.system_prompt(),
        config.MAX_SEARCHES_REPORT,
        max_tokens=1800,
    )
    if not text:
        text = "💰 تقرير الفلوس — ما قدرت أجهز التقرير اليوم، بحاول بكرة."
    db.set_profile("last_report", text)
    db.log("daily_report", {"items": len(fresh)})
    return brain.with_sources(text, urls, limit=4)
