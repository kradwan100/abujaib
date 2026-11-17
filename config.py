"""الإعدادات — كلها من متغيرات البيئة."""

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# البوت لك بروحك: رقمك في تيليجرام (اعرفه بأمر /myid)
OWNER_ID = _int("OWNER_ID", 0)

# الموديلات: Haiku للأسئلة النصية (رخيص)، Sonnet للصور والتقارير (أذكى)
TEXT_MODEL = os.getenv("TEXT_MODEL", "claude-haiku-5-5")
SMART_MODEL = os.getenv("SMART_MODEL", "claude-sonnet-5-5")

# أداة البحث في الويب
WEB_SEARCH_TOOL = os.getenv("WEB_SEARCH_TOOL", "web_search_20250305")
MAX_SEARCHES_CHAT = _int("MAX_SEARCHES_CHAT", 3)
MAX_SEARCHES_REPORT = _int("MAX_SEARCHES_REPORT", 4)

# الوقت والجدولة
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh")
DEFAULT_DAILY_TIME = os.getenv("DAILY_TIME", "20:00")  # وقت التقرير اليومي
GLITCH_INTERVAL_HOURS = _int("GLITCH_INTERVAL_HOURS", 4)

# الذاكرة
HISTORY_MESSAGES = _int("HISTORY_MESSAGES", 12)
DB_PATH = os.getenv("DB_PATH", "data/bot.db")

# يوتيوب (اختياري — مفتاح مجاني من Google Cloud)
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# مصادر RSS — أي رابط يفشل يتجاهله البوت ويكمل
RSS_FEEDS = [
    ("IGN", "https://feeds.feedburner.com/ign/games-all"),
    ("GameSpot", "https://www.gamespot.com/feeds/news/"),
    ("Polygon", "https://www.polygon.com/rss/index.xml"),
    ("GamesRadar", "https://www.gamesradar.com/rss/"),
    ("Eurogamer", "https://www.eurogamer.net/feed"),
    ("Push Square", "https://www.pushsquare.com/feeds/latest"),
    ("Pure Xbox", "https://www.purexbox.com/feeds/latest"),
]
REDDIT_FEEDS = [
    ("r/GTA6", "https://www.reddit.com/r/GTA6/top/.rss?t=day"),
    ("r/GTA6 new", "https://www.reddit.com/r/GTA6/new/.rss"),
]
EXTRA_FEEDS = [
    (name.strip(), url.strip())
    for item in os.getenv("EXTRA_FEEDS", "").split(";")
    if "|" in item
    for name, url in [item.split("|", 1)]
]

GTA_KEYWORDS = ("gta 6", "gta vi", "gta6", "grand theft auto vi", "grand theft auto 6")
GLITCH_KEYWORDS = ("glitch", "exploit", "money", "cash", "unlimited", "infinite", "dupe", "quick money", "fast money")
