"""عقل البوت: يكلم Claude، يبحث في الويب، ويحدّث ملفك وطرق الفلوس بنفسه."""

import logging

from anthropic import AsyncAnthropic

import config
import db
import prompts

log = logging.getLogger("brain")
client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY or "missing")

CLIENT_TOOLS = [
    {
        "name": "update_profile",
        "description": "سجل معلومة عن خالد في اللعبة لما يذكرها: فلوسه، وين وصل في القصة، هدفه، شي فتحه، أو ملاحظة عن أسلوب لعبه. أرسل بس الحقول اللي تغيرت.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cash": {"type": "string", "description": "الفلوس الحالية، مثل 45000"},
                "story_progress": {"type": "string", "description": "آخر مهمة خلصها أو المرحلة"},
                "goal": {"type": "string", "description": "وش يبي يشتري أو يوصل له"},
                "goal_amount": {"type": "string", "description": "كم يحتاج للهدف"},
                "unlocked": {"type": "string", "description": "أشياء فتحها (سيارات، أسلحة، مناطق، أنشطة)"},
                "notes": {"type": "string", "description": "ملاحظة عن أسلوبه أو مستواه"},
            },
        },
    },
    {
        "name": "save_money_method",
        "description": "سجل أو حدّث طريقة فلوس في GTA 6 بعد ما تتأكد منها (أو غيّر حالتها لو انصلحت).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "اسم قصير ثابت للطريقة"},
                "est_per_hour": {"type": "string", "description": "الدخل التقريبي بالساعة أو للمرة"},
                "difficulty": {"type": "string", "enum": ["سهل", "متوسط", "صعب"]},
                "unlock": {"type": "string", "description": "متى تفتح في القصة"},
                "how": {"type": "string", "description": "الخطوات باختصار"},
                "status": {"type": "string", "description": "شغال / غير مؤكد / انصلح"},
                "source": {"type": "string", "description": "رابط المصدر"},
            },
            "required": ["name"],
        },
    },
]


def _run_client_tool(name: str, args: dict) -> str:
    if name == "update_profile":
        changed = []
        for k, v in args.items():
            if k in db.PROFILE_FIELDS and v not in (None, ""):
                db.set_profile(k, v)
                changed.append(k)
        return f"تم التحديث: {', '.join(changed) or 'ما فيه تغيير'}"
    if name == "save_money_method":
        args = dict(args)
        method = args.pop("name", "").strip()
        if not method:
            return "الاسم مطلوب"
        db.upsert_method(method, **args)
        return f"تم حفظ الطريقة: {method}"
    return "أداة غير معروفة"


def _dump(blocks) -> list:
    return [b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else b for b in blocks]


def _extract(content) -> tuple[str, list[str]]:
    parts, urls = [], []
    for b in content:
        if getattr(b, "type", None) != "text":
            continue
        parts.append(b.text)
        for c in getattr(b, "citations", None) or []:
            url = getattr(c, "url", None)
            if url and url not in urls:
                urls.append(url)
    return "".join(parts).strip(), urls


async def run(
    messages: list,
    model: str,
    system: str,
    max_searches: int,
    max_tokens: int = 1500,
    use_tools: bool = True,
) -> tuple[str, list[str]]:
    """حلقة Claude: بحث في الويب + أدوات البوت، لين يطلع رد نهائي."""
    tools = [{"type": config.WEB_SEARCH_TOOL, "name": "web_search", "max_uses": max_searches}] if max_searches else []
    if use_tools:
        tools += CLIENT_TOOLS
    messages = list(messages)
    all_urls: list[str] = []
    text = ""

    for _ in range(8):
        kwargs = dict(model=model, max_tokens=max_tokens, system=system, messages=messages)
        if tools:
            kwargs["tools"] = tools
        resp = await client.messages.create(**kwargs)

        part, urls = _extract(resp.content)
        if part:
            text = part
        all_urls += [u for u in urls if u not in all_urls]

        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": _dump(resp.content)})
            continue
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": _dump(resp.content)})
            results = []
            for b in resp.content:
                if getattr(b, "type", None) == "tool_use":
                    try:
                        out = _run_client_tool(b.name, b.input or {})
                    except Exception as e:  # noqa: BLE001
                        log.exception("tool failed")
                        out = f"خطأ: {e}"
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            messages.append({"role": "user", "content": results})
            continue
        break

    return text, all_urls


def with_sources(text: str, urls: list[str], limit: int = 3) -> str:
    if not urls:
        return text
    return text + "\n\n🔗 المصادر:\n" + "\n".join(f"- {u}" for u in urls[:limit])


async def chat(text: str, image_b64: str | None = None, media_type: str = "image/jpeg") -> str:
    """رد على رسالة خالد (نص أو صورة)."""
    if image_b64:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
            {"type": "text", "text": text},
        ]
        model, note = config.SMART_MODEL, f"[أرسلت صورة من الشاشة] {text}"
    else:
        content = [{"type": "text", "text": text}]
        model, note = config.TEXT_MODEL, text

    messages = db.get_history() + [{"role": "user", "content": content}]
    answer, urls = await run(messages, model, prompts.system_prompt(), config.MAX_SEARCHES_CHAT)
    if not answer:
        answer = "ما قدرت أطلع رد هالمرة 😅 جرّب تعيد السؤال بصياغة ثانية."

    db.add_history("user", note, config.HISTORY_MESSAGES)
    db.add_history("assistant", answer, config.HISTORY_MESSAGES)
    return with_sources(answer, urls)


async def session_plan(minutes: int) -> str:
    q = (
        f"عندي {minutes} دقيقة ألعب الحين. اعطني خطة فلوس مرتبة بالدقائق لمرحلتي، "
        "وش أسوي أول وبعدها، وكم أتوقع أطلع في النهاية."
    )
    return await chat(q)
