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
        [[
            Btn(
                label,
                callback_data=target,
                style="primary",
            )
        ]]
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
# قائمة الأوتفيت
# ============================================================

def outfit_markup():
    return Markup(
        [
            [
                Btn("🖤 For Him", callback_data="outfit:him", style="primary")
            ],
            [
                Btn("🤍 For Her", callback_data="outfit:her", style="success")
            ],
            [
                Btn("🔙 رجوع", callback_data="m", style="primary")
            ],
        ]
    )


# ============================================================
# القائمة الرئيسية
# ============================================================

def main_menu(uid):
    rows = [
        [
            Btn("📄 الملخصات", callback_data="sm", style="primary"),
            Btn("📝 الاختبارات", callback_data="qm", style="success"),
        ],
        [
            Btn("📊 نتائجي", callback_data="me", style="primary"),
            Btn("📅 الجدول الأسبوعي", callback_data="sc", style="primary"),
        ],
        [
            Btn(
                "📚 شرح قواعد اللغة العربية",
                callback_data="rules",
                style="primary",
            )
        ],
        [
            Btn(
                "🧠 تحدي قواعد اللغة العربية",
                callback_data="aichallenge",
                style="success",
            )
        ],
        [
            Btn("👕 Outfit", callback_data="outfit", style="primary"),
            Btn("🌤️ Weather", callback_data="weather", style="success"),
        ],
        [
            Btn(
                "🌐 فتح قطوف الأكلم",
                web_app=WebAppInfo(
                    url="https://telegrambot-production-4013.up.railway.app"
                ),
                style="primary",
            )
        ],
        [
            Btn("📑 طلب تقرير", callback_data="rp", style="success"),
            Btn("📞 تواصل معنا", callback_data="ct", style="primary"),
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
            Btn("📌 إعراب مفصل", callback_data="ai:grammar", style="primary"),
            Btn("🎨 تحليل بلاغي", callback_data="ai:rhetoric", style="success"),
        ],
        [
            Btn("⚖️ الصرف والبنية", callback_data="ai:morphology", style="primary"),
            Btn("📖 معجم المفردات", callback_data="ai:dictionary", style="success"),
        ],
        [
            Btn("📝 شرح النص", callback_data="ai:explain", style="primary"),
            Btn("🪶 عروض وقافية", callback_data="ai:prosody", style="success"),
        ],
        [
            Btn("👤 الشاعر والعصر", callback_data="ai:poet", style="primary"),
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
# الأسئلة الشهرية
# ============================================================

def monthly_menu_markup():
    return Markup(
        [
            [
                Btn(
                    "📚 أسئلة شهرية سابقة",
                    callback_data="mq:previous",
                    style="primary",
                )
            ],
            [
                Btn(
                    "📝 أسئلة الشهر الحالي",
                    callback_data="mq:current",
                    style="success",
                )
            ],
            [
                Btn(
                    "🎯 الاختبارات",
                    callback_data="iqm",
                    style="primary",
                )
            ],
            [
                Btn(
                    "🔙 رجوع",
                    callback_data="m",
                    style="primary",
                )
            ],
        ]
    )


def monthly_section_markup():
    return Markup(
        [
            [
                Btn(
                    "☀️ صباحي",
                    callback_data="mqs:current:morning",
                    style="primary",
                ),
                Btn(
                    "🌙 مسائي",
                    callback_data="mqs:current:evening",
                    style="success",
                ),
            ],
            [
                Btn(
                    "🔙 رجوع",
                    callback_data="qm",
                    style="primary",
                )
            ],
        ]
    )


def monthly_subjects_markup(quiz_type, section):
    buttons = []

    for s in db.subjects():
        count = db.count_monthly_question_images(
            s["id"],
            quiz_type,
            section,
        )

        if count > 0:
            buttons.append(
                Btn(
                    f"{s['name']} ({count})",
                    callback_data=f"mqi:{quiz_type}:{section}:{s['id']}",
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
                callback_data="qm",
                style="primary",
            )
        ]
    )

    return Markup(rows)


async def show_monthly_subjects(q, quiz_type, section):
    if quiz_type == db.MONTHLY_PREVIOUS:
        title = "📚 أسئلة شهرية سابقة\n\nاختر المادة:"
    elif section == db.SECTION_MORNING:
        title = "📝 أسئلة الشهر الحالي — ☀️ صباحي\n\nاختر المادة:"
    else:
        title = "📝 أسئلة الشهر الحالي — 🌙 مسائي\n\nاختر المادة:"

    has_subjects = any(
        db.count_monthly_question_images(
            s["id"],
            quiz_type,
            section,
        ) > 0
        for s in db.subjects()
    )

    if not has_subjects:
        return await show(
            q,
            title + "\n\n⚠️ لا توجد أسئلة مضافة حالياً.",
            back_markup("qm"),
        )

    return await show(
        q,
        title,
        monthly_subjects_markup(
            quiz_type,
            section,
        ),
    )


async def show_monthly_images(q, sid, quiz_type, section):
    subj = db.get_subject(sid)

    if not subj:
        return await show(
            q,
            "⚠️ المادة غير موجودة.",
            back_markup("qm"),
        )

    images = db.monthly_question_images(
        sid,
        quiz_type,
        section,
    )

    if not images:
        return await show(
            q,
            "⚠️ لا توجد أسئلة مضافة لهذا القسم.",
            back_markup("qm"),
        )

    for image in images:
        caption = image["caption"] or "📝 أسئلة شهرية"
        await q.message.reply_photo(
            image["file_id"],
            caption=caption,
        )

    if quiz_type == db.MONTHLY_PREVIOUS:
        title = f"📚 الأسئلة الشهرية السابقة — {subj['name']}"
    elif section == db.SECTION_MORNING:
        title = f"☀️ أسئلة الشهر الحالي الصباحية — {subj['name']}"
    else:
        title = f"🌙 أسئلة الشهر الحالي المسائية — {subj['name']}"

    return await show(
        q,
        title,
        Markup(
            [
                [
                    Btn(
                        "🔙 رجوع للمواد",
                        callback_data=f"mqs:{quiz_type}:{section}",
                        style="primary",
                    )
                ],
                [
                    Btn(
                        "📝 قائمة الاختبارات",
                        callback_data="qm",
                        style="success",
                    )
                ],
            ]
        ),
    )


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
        return await q.message.reply_text("⚠️ هذا الملخص انحذف.")

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

async def is_subscribed(context, uid, force=False):
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
        context.user_data["sub_until"] = now + 600

    return ok
