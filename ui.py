# -*- coding: utf-8 -*-

"""القوائم المشتركة + الاشتراك الإجباري."""

import time

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup
from telegram import WebAppInfo

from telegram.error import BadRequest

import db

from config import (
    ADMIN_IDS,
    CHANNEL,
    CHANNEL_URL,
    OWNER_TG,
    OWNER_WA,
    logger,
)


def is_admin(uid):
    return uid in ADMIN_IDS


def back_markup(target, label="🔙 رجوع"):
    return Markup(
        [
            [
                Btn(
                    label,
                    callback_data=target,
                    style="primary",
                )
            ]
        ]
    )


async def show(q, text, markup=None):
    try:
        await q.edit_message_text(
            text,
            reply_markup=markup
        )

    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


# ============================================================
# القائمة الرئيسية
# ============================================================

def main_menu(uid):

    rows = [

        # الملخصات + الاختبارات
        [
            Btn(
                "📄 الملخصات",
                callback_data="sm",
                style="primary",
            ),

            Btn(
                "📝 الاختبارات",
                callback_data="qm",
                style="success",
            ),
        ],

        # النتائج + الجدول
        [
            Btn(
                "📊 نتائجي",
                callback_data="me",
                style="primary",
            ),

            Btn(
                "📅 الجدول الأسبوعي",
                callback_data="sc",
                style="primary",
            ),
        ],

        # تحدي الذكاء الاصطناعي
        [
            Btn(
                "🧠 تحدي قواعد اللغة العربية",
                callback_data="aichallenge",
                style="success",
            )
        ],

        # واجهة قطوف الأكلم
        [
            Btn(
                "🌐 فتح قطوف الأكلم",
                web_app=WebAppInfo(
                    url="https://telegrambot-production-4013.up.railway.app"
                ),
                style="primary",
            )
        ],

        # التقرير + التواصل
        [
            Btn(
                "📑 طلب تقرير",
                callback_data="rp",
                style="success",
            ),

            Btn(
                "📞 تواصل معنا",
                callback_data="ct",
                style="primary",
            ),
        ],

    ]

    if is_admin(uid):
        rows.append(
            [
                Btn(
                    "⚙️ لوحة الأدمن",
                    callback_data="ad",
                    style="danger",
                )
            ]
        )

    return Markup(rows)


# ============================================================
# أزرار الذكاء الاصطناعي
# ============================================================

def ai_markup():

    rows = [

        [
            Btn(
                "📌 إعراب مفصل",
                callback_data="ai:grammar",
                style="primary",
            ),

            Btn(
                "🎨 تحليل بلاغي",
                callback_data="ai:rhetoric",
                style="success",
            ),
        ],

        [
            Btn(
                "⚖️ الصرف والبنية",
                callback_data="ai:morphology",
                style="primary",
            ),

            Btn(
                "📖 معجم المفردات",
                callback_data="ai:dictionary",
                style="success",
            ),
        ],

        [
            Btn(
                "📝 شرح النص",
                callback_data="ai:explain",
                style="primary",
            ),

            Btn(
                "🪶 عروض وقافية",
                callback_data="ai:prosody",
                style="success",
            ),
        ],

        [
            Btn(
                "👤 الشاعر والعصر",
                callback_data="ai:poet",
                style="primary",
            ),
        ],

    ]

    return Markup(rows)


# ============================================================
# المواد
# ============================================================

def subjects_markup(prefix, count_key=None, back="m"):

    buttons = []

    for s in db.subjects_with_counts():

        label = (
            f"{s['name']} ({s[count_key]})"
            if count_key
            else s["name"]
        )

        buttons.append(
            Btn(
                label,
                callback_data=f"{prefix}:{s['id']}",
                style="primary",
            )
        )

    rows = [
        buttons[i:i + 2]
        for i in range(0, len(buttons), 2)
    ]

    rows.append(
        [
            Btn(
                "🔙 رجوع",
                callback_data=back,
                style="primary",
            )
        ]
    )

    return Markup(rows)


# ============================================================
# التواصل
# ============================================================

def contact_buttons():

    return [

        [
            Btn(
                "✈️ تلقرام",
                url=f"https://t.me/{OWNER_TG}",
                style="primary",
            )
        ],

        [
            Btn(
                "🟢 واتساب",
                url=f"https://wa.me/{OWNER_WA}",
                style="success",
            )
        ],

    ]


# ============================================================
# قائمة الملخصات
# ============================================================

async def summaries_list(q, sid):

    subj = db.get_subject(sid)

    if not subj:

        return await show(
            q,
            "⚠️ المادة غير موجودة.",
            back_markup("sm"),
        )

    items = db.summaries(sid)

    if not items:

        return await show(
            q,
            f"⚠️ ما في ملخصات مضافة بعد لمادة {subj['name']}.",
            back_markup("sm"),
        )

    rows = [
        [
            Btn(
                f"📄 {it['title']}",
                callback_data=f"sd:{it['id']}",
                style="primary",
            )
        ]
        for it in items
    ]

    rows.append(
        [
            Btn(
                "🔙 رجوع للمواد",
                callback_data="sm",
                style="primary",
            )
        ]
    )

    await show(
        q,
        f"📄 ملخصات {subj['name']}:",
        Markup(rows),
    )


# ============================================================
# إرسال الملخص
# ============================================================

async def send_summary(q, sum_id):

    it = db.get_summary(sum_id)

    if not it:

        return await q.message.reply_text(
            "⚠️ هذا الملخص انحذف."
        )

    if it["file_id"]:

        await q.message.reply_document(
            it["file_id"],
            caption=f"📄 {it['title']}"
        )

    else:

        await q.message.reply_text(
            f"📄 {it['title']}\n{it['url']}"
        )


# ============================================================
# الاشتراك الإجباري
# ============================================================

SUB_TEXT = (
    "⚠️ لازم تشترك بالقناة أول عشان تستخدم البوت:\n"
    f"{CHANNEL_URL}\n\n"
    "بعد ما تشترك اضغط «اشتركت، تحقق»."
)


def sub_markup():

    return Markup(
        [

            [
                Btn(
                    "📢 اشترك بالقناة",
                    url=CHANNEL_URL,
                    style="primary",
                )
            ],

            [
                Btn(
                    "✅ اشتركت، تحقق",
                    callback_data="chk",
                    style="success",
                )
            ],

        ]
    )


# ============================================================
# التحقق من الاشتراك
# ============================================================

async def is_subscribed(
    context,
    uid,
    force=False
):

    if not CHANNEL or is_admin(uid):
        return True

    now = time.time()

    if (
        not force
        and context.user_data.get(
            "sub_until",
            0
        ) > now
    ):
        return True

    try:

        m = await context.bot.get_chat_member(
            CHANNEL,
            uid
        )

    except Exception:

        logger.exception(
            "ما قدرت أتحقق من الاشتراك. "
            "تأكد إن البوت أدمن بالقناة %s",
            CHANNEL
        )

        return True

    ok = (
        m.status in (
            "member",
            "administrator",
            "creator"
        )
        or (
            m.status == "restricted"
            and getattr(
                m,
                "is_member",
                False
            )
        )
    )

    if ok:

        context.user_data["sub_until"] = (
            now + 600
        )

    return ok
