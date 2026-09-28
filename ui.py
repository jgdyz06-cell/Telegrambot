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

        # Web App
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
           
