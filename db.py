"""قاعدة البيانات (SQLite): ملفك في اللعبة، طرق الفلوس، الذاكرة، والأشياء اللي شافها البوت."""

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager

from config import DB_PATH

PROFILE_FIELDS = {
    "cash": "الفلوس الحالية",
    "story_progress": "وين وصلت في القصة",
    "goal": "الهدف الحالي",
    "goal_amount": "مبلغ الهدف",
    "unlocked": "أشياء فتحتها (سيارات/أسلحة/مناطق)",
    "notes": "ملاحظات عن أسلوب لعبك",
    "daily_time": "وقت التقرير اليومي",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (key TEXT PRIMARY KEY, value TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS money_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    est_per_hour TEXT,
    difficulty TEXT,
    unlock TEXT,
    how TEXT,
    status TEXT DEFAULT 'شغال',
    source TEXT,
    updated REAL
);
CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS seen (hash TEXT PRIMARY KEY, kind TEXT, title TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, text TEXT, ts REAL);
"""


@contextmanager
def conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


# ---------- الملف الشخصي في اللعبة ----------
def set_profile(key: str, value) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO profile(key,value,updated) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
            (key, str(value), time.time()),
        )
        c.execute("INSERT INTO log(kind,text,ts) VALUES(?,?,?)", ("profile", f"{key}={value}", time.time()))


def get_profile() -> dict:
    with conn() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM profile")}


def profile_text() -> str:
    p = get_profile()
    lines = [f"- {label}: {p[k]}" for k, label in PROFILE_FIELDS.items() if p.get(k) and k != "daily_time"]
    return "\n".join(lines) if lines else "- ما فيه معلومات للحين (اللاعب في البداية)"


def reset_profile() -> None:
    with conn() as c:
        c.execute("DELETE FROM profile WHERE key != 'daily_time'")


# ---------- طرق الفلوس ----------
def upsert_method(name: str, **fields) -> None:
    allowed = {"est_per_hour", "difficulty", "unlock", "how", "status", "source"}
    data = {k: v for k, v in fields.items() if k in allowed and v not in (None, "")}
    with conn() as c:
        row = c.execute("SELECT id FROM money_methods WHERE name=?", (name,)).fetchone()
        if row:
            if data:
                sets = ", ".join(f"{k}=?" for k in data)
                c.execute(f"UPDATE money_methods SET {sets}, updated=? WHERE id=?", (*data.values(), time.time(), row["id"]))
        else:
            cols = ["name", *data.keys(), "updated"]
            c.execute(
                f"INSERT INTO money_methods({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                (name, *data.values(), time.time()),
            )


def list_methods(include_dead: bool = False) -> list[dict]:
    q = "SELECT * FROM money_methods"
    if not include_dead:
        q += " WHERE status NOT LIKE '%انصلح%' AND status NOT LIKE '%ما يشتغل%'"
    q += " ORDER BY updated DESC"
    with conn() as c:
        return [dict(r) for r in c.execute(q)]


def methods_text() -> str:
    rows = list_methods()
    if not rows:
        return "- القائمة فاضية للحين"
    out = []
    for r in rows[:25]:
        out.append(
            f"- {r['name']} | الدخل: {r['est_per_hour'] or '؟'} | الصعوبة: {r['difficulty'] or '؟'} "
            f"| يفتح: {r['unlock'] or '؟'} | الحالة: {r['status']}"
        )
    return "\n".join(out)


# ---------- ذاكرة المحادثة ----------
def add_history(role: str, content: str, keep: int) -> None:
    with conn() as c:
        c.execute("INSERT INTO history(role,content,ts) VALUES(?,?,?)", (role, content, time.time()))
        c.execute("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT ?)", (keep,))


def get_history() -> list[dict]:
    with conn() as c:
        rows = [dict(r) for r in c.execute("SELECT role,content FROM history ORDER BY id")]
    # لازم تبدأ برسالة من المستخدم
    while rows and rows[0]["role"] != "user":
        rows.pop(0)
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def clear_history() -> None:
    with conn() as c:
        c.execute("DELETE FROM history")


# ---------- الأشياء اللي شافها البوت (عشان ما يكرر) ----------
def _h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def is_seen(key: str) -> bool:
    with conn() as c:
        return c.execute("SELECT 1 FROM seen WHERE hash=?", (_h(key),)).fetchone() is not None


def mark_seen(key: str, kind: str, title: str = "") -> None:
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO seen(hash,kind,title,ts) VALUES(?,?,?,?)", (_h(key), kind, title, time.time()))


def recent_seen_titles(kind: str, limit: int = 20) -> list[str]:
    with conn() as c:
        return [r["title"] for r in c.execute("SELECT title FROM seen WHERE kind=? ORDER BY ts DESC LIMIT ?", (kind, limit))]


def log(kind: str, data) -> None:
    with conn() as c:
        c.execute("INSERT INTO log(kind,text,ts) VALUES(?,?,?)", (kind, json.dumps(data, ensure_ascii=False), time.time()))
