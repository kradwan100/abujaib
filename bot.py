"""مدرب الفلوس GTA 6 — بوت تيليجرام شخصي.

الأوامر:
  /start        ترحيب وشرح
  /plan 60      خطة فلوس لجلسة لعب (بالدقائق)
  /cash 45000   تحدث فلوسك
  /goal ...     هدفك (مثلاً: /goal 250000 عشان المهمة الجاية)
  /progress ... وين وصلت في القصة
  /status       ملفك في اللعبة
  /methods      طرق الفلوس المسجلة
  /report       تقرير الفلوس اليومي الحين
  /time 20:00   وقت التقرير اليومي
  /reset        مسح المحادثة (ملفك يبقى)
  /myid         رقمك في تيليجرام
"""

import base64
import logging
import re
from datetime import time as dtime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import brain
import config
import daily
import db
import glitches

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

TZ = ZoneInfo(config.TIMEZONE)
LIMIT = 4000


# ---------- أدوات ----------
def owner_only(fn):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id != config.OWNER_ID:
            return  # البوت لك بروحك — يتجاهل أي أحد ثاني
        return await fn(update, context)

    return wrapper


def split(text: str) -> list[str]:
    out = []
    while len(text) > LIMIT:
        cut = text.rfind("\n", 0, LIMIT)
        cut = cut if cut > LIMIT // 2 else LIMIT
        out.append(text[:cut])
        text = text[cut:].lstrip()
    return out + ([text] if text else [])


async def send(context: ContextTypes.DEFAULT_TYPE, text: str):
    for chunk in split(text):
        await context.bot.send_message(config.OWNER_ID, chunk, disable_web_page_preview=True)


async def typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)


async def safe(update, context, coro, fail_msg="صار خطأ، جرّب بعد شوي 🙏"):
    await typing(update, context)
    try:
        text = await coro
    except Exception:
        log.exception("handler failed")
        text = fail_msg
    await send(context, text)


# ---------- الأوامر ----------
@owner_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "هلا خالد 💰 أنا مدرب الفلوس حقك في GTA 6.\n\n"
        "كلمني عادي، مثلاً:\n"
        "- وش أسرع طريقة فلوس في البداية؟\n"
        "- معي 20 ألف وخلصت مهمة كذا، وش أسوي؟\n"
        "- 📸 صوّر الشاشة وأرسلها لي\n\n"
        "أوامر سريعة:\n"
        "/plan 60 خطة فلوس لساعة لعب\n"
        "/cash 45000 تحدث فلوسك\n"
        "/goal 250000 عشان المهمة الجاية\n"
        "/progress خلصت المهمة الثالثة\n"
        "/status ملفك  ·  /methods طرق الفلوس\n"
        "/report التقرير اليومي الحين  ·  /time 20:00 وقته\n"
        "/reset مسح المحادثة\n\n"
        "كل يوم بأرسل لك تقرير فلوس، وأي قلتش فلوس جديد ينتشر بنبهك عليه على طول ⚡"
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"رقمك: {update.effective_user.id}")


@owner_only
async def cash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = " ".join(context.args).strip()
    if not amount:
        await update.message.reply_text("اكتب المبلغ، مثل: /cash 45000")
        return
    db.set_profile("cash", amount)
    await update.message.reply_text(f"تمام، سجلت فلوسك: {amount} 💵")


@owner_only
async def goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("اكتب هدفك، مثل: /goal 250000 عشان المهمة الجاية")
        return
    m = re.match(r"^([\d,\.]+[kKmM]?)\s*(.*)$", text)
    if m:
        db.set_profile("goal_amount", m.group(1))
        if m.group(2):
            db.set_profile("goal", m.group(2))
    else:
        db.set_profile("goal", text)
    await safe(update, context, brain.chat(f"هدفي الجديد: {text}. كيف أوصله بأسرع وقت؟ وكم جلسة تقريباً؟"))


@owner_only
async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("قل لي وين وصلت، مثل: /progress خلصت المهمة الثالثة")
        return
    db.set_profile("story_progress", text)
    await update.message.reply_text("سجلتها 👌 وما راح أحرق عليك شي بعدها.")


@owner_only
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = db.get_profile()
    await update.message.reply_text(
        "📋 ملفك في اللعبة:\n" + db.profile_text() + f"\n- وقت التقرير اليومي: {p.get('daily_time', config.DEFAULT_DAILY_TIME)}"
    )


@owner_only
async def methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.list_methods()
    if not rows:
        await update.message.reply_text("لسا ما سجلت طرق فلوس. بتتعبى مع الأيام من التقارير وأسئلتك 💪")
        return
    lines = ["💰 طرق الفلوس المسجلة:\n"]
    for r in rows[:20]:
        lines.append(f"• {r['name']} — {r['est_per_hour'] or '؟'} | {r['difficulty'] or '؟'} | {r['status']}")
        if r.get("unlock"):
            lines.append(f"   يفتح: {r['unlock']}")
    await send(context, "\n".join(lines))


@owner_only
async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        minutes = int(context.args[0]) if context.args else 60
    except ValueError:
        minutes = 60
    await safe(update, context, brain.session_plan(minutes))


@owner_only
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لحظات أجمع لك آخر الأخبار ⏳")
    await safe(update, context, daily.build_report(), "ما قدرت أجهز التقرير الحين، جرّب بعد شوي.")


@owner_only
async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = context.args[0] if context.args else ""
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", value):
        await update.message.reply_text("اكتب الوقت كذا: /time 20:00")
        return
    db.set_profile("daily_time", value)
    schedule_daily(context.application, value)
    await update.message.reply_text(f"تمام، التقرير اليومي بيوصلك الساعة {value} ⏰")


@owner_only
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.clear_history()
    await update.message.reply_text("مسحت المحادثة 👌 (ملفك وطرق الفلوس باقية)")


# ---------- الرسائل ----------
@owner_only
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe(update, context, brain.chat(update.message.text))


@owner_only
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo:
        file = await msg.photo[-1].get_file()
        media_type = "image/jpeg"
    else:  # صورة مرسلة كملف
        file = await msg.document.get_file()
        media_type = msg.document.mime_type or "image/jpeg"
    data = bytes(await file.download_as_bytearray())
    b64 = base64.standard_b64encode(data).decode()
    question = msg.caption or "هذي صورة من شاشة GTA 6. وش يظهر فيها، ووش أسوي الحين عشان أجيب فلوس أو أكمل؟"
    await safe(update, context, brain.chat(question, b64, media_type), "ما قدرت أقرأ الصورة، أرسلها مرة ثانية 📸")


# ---------- المهام المجدولة ----------
async def job_daily(context: ContextTypes.DEFAULT_TYPE):
    try:
        await send(context, await daily.build_report())
    except Exception:
        log.exception("daily report failed")


async def job_glitches(context: ContextTypes.DEFAULT_TYPE):
    try:
        alert = await glitches.check()
        if alert:
            await send(context, alert)
    except Exception:
        log.exception("glitch check failed")


def schedule_daily(app: Application, hhmm: str):
    for j in app.job_queue.get_jobs_by_name("daily"):
        j.schedule_removal()
    h, m = map(int, hhmm.split(":"))
    app.job_queue.run_daily(job_daily, dtime(h, m, tzinfo=TZ), name="daily")
    log.info("daily report scheduled at %s %s", hhmm, config.TIMEZONE)


async def post_init(app: Application):
    schedule_daily(app, db.get_profile().get("daily_time", config.DEFAULT_DAILY_TIME))
    app.job_queue.run_repeating(
        job_glitches, interval=config.GLITCH_INTERVAL_HOURS * 3600, first=120, name="glitches"
    )


def main():
    missing = [n for n, v in [("TELEGRAM_BOT_TOKEN", config.TELEGRAM_TOKEN), ("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY)] if not v]
    if missing:
        raise SystemExit(f"ناقص: {', '.join(missing)}")
    if not config.OWNER_ID:
        log.warning("OWNER_ID مو محدد — شغّل البوت وأرسل /myid ثم حط الرقم في OWNER_ID")

    db.init()
    app = Application.builder().token(config.TELEGRAM_TOKEN).post_init(post_init).build()
    for name, fn in [
        ("start", start), ("myid", myid), ("cash", cash), ("goal", goal), ("progress", progress),
        ("status", status), ("methods", methods), ("plan", plan), ("report", report),
        ("time", set_time), ("reset", reset),
    ]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("GTA 6 money coach running (text=%s, smart=%s)", config.TEXT_MODEL, config.SMART_MODEL)
    app.run_polling()


if __name__ == "__main__":
    main()
