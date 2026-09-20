# -*- coding: utf-8 -*-
"""رسائل الأدمن: إضافة مادة أو ملخص أو أسئلة."""
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup

import db
from ui import back_markup


def parse_summary(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    url = next((l for l in lines if l.lower().startswith("http")), None)
    title = next((l for l in lines if l != url), "ملخص")
    return title[:60], url


def again_markup(label, data):
    return Markup(
        [[Btn(label, callback_data=data)], [Btn("⚙️ لوحة الأدمن", callback_data="ad")]]
    )


async def handle_admin_message(update, context, aw):
    msg = update.message
    kind = aw["type"]

    if kind == "subject":
        name = (msg.text or "").strip()
        if not name:
            return await msg.reply_text("أرسل اسم المادة كنص.")
        context.user_data.pop("await")
        panel = back_markup("ad", "⚙️ لوحة الأدمن")
        if db.add_subject(name):
            return await msg.reply_text(f"✅ انضافت مادة «{name}».", reply_markup=panel)
        return await msg.reply_text("⚠️ هذي المادة موجودة من قبل.", reply_markup=panel)

    if kind == "summary":
        if msg.document:
            title = (msg.caption or msg.document.file_name or "ملخص").strip()[:60]
            db.add_summary(aw["sid"], title, file_id=msg.document.file_id)
        else:
            title, url = parse_summary(msg.text or "")
            if not url:
                return await msg.reply_text("⚠️ ما لقيت رابط يبدأ بـ http. جرّب مرة ثانية.")
            db.add_summary(aw["sid"], title, url=url)
        context.user_data.pop("await")
        return await msg.reply_text(
            f"✅ انضاف الملخص «{title}».",
            reply_markup=again_markup("➕ ملخص ثاني لنفس المادة", f"ak:sum:{aw['sid']}"),
        )

    if kind == "questions":
        if not msg.text:
            return await msg.reply_text("أرسل الأسئلة كنص.")
        good, errors = db.parse_questions(msg.text)
        parts = []
        if good:
            db.add_questions(aw["sid"], good)
            context.user_data.pop("await")
            parts.append(f"✅ انضافت {len(good)} سؤال.")
        if errors:
            parts.append("⚠️ ما انضافت هذي:\n" + "\n".join(errors))
        if not good:
            parts.append("صحّحها وأرسلها مرة ثانية، أو /cancel للإلغاء.")
            return await msg.reply_text("\n\n".join(parts))
        await msg.reply_text(
            "\n\n".join(parts),
            reply_markup=again_markup("➕ أسئلة أخرى لنفس المادة", f"ak:q:{aw['sid']}"),
        )
