# -*- coding: utf-8 -*-
"""القوائم المشتركة + الاشتراك الإجباري."""
import time

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup
from telegram.error import BadRequest

import db
from config import ADMIN_IDS, CHANNEL, CHANNEL_URL, OWNER_TG, OWNER_WA, logger


def is_admin(uid):
    return uid in ADMIN_IDS


def back_markup(target, label="🔙 رجوع"):
    return Markup([[Btn(label, callback_data=target)]])


async def show(q, text, markup=None):
    try:
        await q.edit_message_text(text, reply_markup=markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


def main_menu(uid):
    rows = [
        [Btn("📄 الملخصات", callback_data="sm")],
        [Btn("📝 الاختبارات", callback_data="qm")],
        [Btn("📊 نتائجي", callback_data="me")],
        [Btn("📑 طلب تقرير", callback_data="rp")],
        [Btn("📞 تواصل معنا", callback_data="ct")],
    ]
    if is_admin(uid):
        rows.append([Btn("⚙️ لوحة الأدمن", callback_data="ad")])
    return Markup(rows)


def subjects_markup(prefix, count_key=None, back="m"):
    rows = []
    for s in db.subjects_with_counts():
        label = f"{s['name']} ({s[count_key]})" if count_key else s["name"]
        rows.append([Btn(label, callback_data=f"{prefix}:{s['id']}")])
    rows.append([Btn("🔙 رجوع", callback_data=back)])
    return Markup(rows)


def contact_buttons():
    return [
        [Btn("✈️ تلقرام", url=f"https://t.me/{OWNER_TG}")],
        [Btn("🟢 واتساب", url=f"https://wa.me/{OWNER_WA}")],
    ]


async def summaries_list(q, sid):
    subj = db.get_subject(sid)
    if not subj:
        return await show(q, "⚠️ المادة غير موجودة.", back_markup("sm"))
    items = db.summaries(sid)
    if not items:
        return await show(
            q, f"⚠️ ما في ملخصات مضافة بعد لمادة {subj['name']}.", back_markup("sm")
        )
    rows = [[Btn(f"📄 {it['title']}", callback_data=f"sd:{it['id']}")] for it in items]
    rows.append([Btn("🔙 رجوع للمواد", callback_data="sm")])
    await show(q, f"📄 ملخصات {subj['name']}:", Markup(rows))


async def send_summary(q, sum_id):
    it = db.get_summary(sum_id)
    if not it:
        return await q.message.reply_text("⚠️ هذا الملخص انحذف.")
    if it["file_id"]:
        await q.message.reply_document(it["file_id"], caption=f"📄 {it['title']}")
    else:
        await q.message.reply_text(f"📄 {it['title']}\n{it['url']}")


# ---------- الاشتراك الإجباري ----------
SUB_TEXT = (
    "⚠️ لازم تشترك بالقناة أول عشان تستخدم البوت:\n"
    f"{CHANNEL_URL}\n\n"
    "بعد ما تشترك اضغط «اشتركت، تحقق»."
)


def sub_markup():
    return Markup(
        [
            [Btn("📢 اشترك بالقناة", url=CHANNEL_URL)],
            [Btn("✅ اشتركت، تحقق", callback_data="chk")],
        ]
    )


async def is_subscribed(context, uid, force=False):
    if not CHANNEL or is_admin(uid):
        return True
    now = time.time()
    if not force and context.user_data.get("sub_until", 0) > now:
        return True
    try:
        m = await context.bot.get_chat_member(CHANNEL, uid)
    except Exception:
        # غالباً البوت مو أدمن بالقناة. نسمح للطالب عشان ما ينقفل الكل.
        logger.exception("ما قدرت أتحقق من الاشتراك. تأكد إن البوت أدمن بالقناة %s", CHANNEL)
        return True
    ok = m.status in ("member", "administrator", "creator") or (
        m.status == "restricted" and getattr(m, "is_member", False)
    )
    if ok:
        context.user_data["sub_until"] = now + 600  # نخزّن النتيجة 10 دقايق
    return ok
