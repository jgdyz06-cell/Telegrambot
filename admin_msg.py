-- coding: utf-8 --

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
[
[
Btn(
label,
callback_data=data,
)
],
[
Btn(
"⚙️ لوحة الأدمن",
callback_data="ad",
)
],
]
)

async def handle_admin_message(update, context, aw):

msg = update.message
kind = aw["type"]

# ========================================================
# إضافة مادة
# ========================================================

if kind == "subject":

    name = (msg.text or "").strip()

    if not name:
        return await msg.reply_text(
            "أرسل اسم المادة كنص."
        )

    context.user_data.pop(
        "await",
        None,
    )

    panel = back_markup(
        "ad",
        "⚙️ لوحة الأدمن",
    )

    if db.add_subject(name):

        return await msg.reply_text(
            f"✅ انضافت مادة «{name}».",
            reply_markup=panel,
        )

    return await msg.reply_text(
        "⚠️ هذي المادة موجودة من قبل.",
        reply_markup=panel,
    )

# ========================================================
# إضافة ملخص
# ========================================================

if kind == "summary":

    if msg.document:

        title = (
            msg.caption
            or msg.document.file_name
            or "ملخص"
        ).strip()[:60]

        db.add_summary(
            aw["sid"],
            title,
            file_id=msg.document.file_id,
        )

    else:

        title, url = parse_summary(
            msg.text or ""
        )

        if not url:

            return await msg.reply_text(
                "⚠️ ما لقيت رابط يبدأ بـ http. "
                "جرّب مرة ثانية."
            )

        db.add_summary(
            aw["sid"],
            title,
            url=url,
        )

    context.user_data.pop(
        "await",
        None,
    )

    return await msg.reply_text(
        f"✅ انضاف الملخص «{title}».",
        reply_markup=again_markup(
            "➕ ملخص ثاني لنفس المادة",
            f"ak:sum:{aw['sid']}",
        ),
    )

# ========================================================
# إضافة أسئلة عادية
# ========================================================

if kind == "questions":

    if not msg.text:

        return await msg.reply_text(
            "أرسل الأسئلة كنص."
        )

    good, errors = db.parse_questions(
        msg.text
    )

    parts = []

    if good:

        db.add_questions(
            aw["sid"],
            good,
        )

        context.user_data.pop(
            "await",
            None,
        )

        parts.append(
            f"✅ انضافت {len(good)} سؤال."
        )

    if errors:

        parts.append(
            "⚠️ ما انضافت هذي:\n"
            + "\n".join(errors)
        )

    if not good:

        parts.append(
            "صحّحها وأرسلها مرة ثانية، "
            "أو /cancel للإلغاء."
        )

        return await msg.reply_text(
            "\n\n".join(parts)
        )

    await msg.reply_text(
        "\n\n".join(parts),
        reply_markup=again_markup(
            "➕ أسئلة أخرى لنفس المادة",
            f"ak:q:{aw['sid']}",
        ),
    )

    return

# ========================================================
# إضافة أسئلة شهرية كصورة
# ========================================================

if kind == "monthly_image":

    # ----------------------------------------------------
    # لازم تكون صورة
    # ----------------------------------------------------

    if not msg.photo:

        return await msg.reply_text(
            "⚠️ أرسل أسئلة الشهر كـ **صورة** فقط.\n\n"
            "📸 أرسل الصورة من Telegram، "
            "وتقدر تضيف اسم الامتحان أو ملاحظة في الـ Caption.\n\n"
            "للإلغاء: /cancel",
            parse_mode="Markdown",
        )

    # ----------------------------------------------------
    # استخراج آخر وأعلى جودة للصورة
    # ----------------------------------------------------

    photo = msg.photo[-1]

    file_id = photo.file_id

    # ----------------------------------------------------
    # البيانات المطلوبة من admin.py
    # ----------------------------------------------------

    sid = aw.get("sid")
    quiz_type = aw.get("quiz_type")
    section = aw.get(
        "section",
        db.SECTION_SHARED,
    )

    if not sid:

        context.user_data.pop(
            "await",
            None,
        )

        return await msg.reply_text(
            "⚠️ انتهت جلسة إضافة الأسئلة. "
            "ارجع إلى لوحة الأدمن وابدأ من جديد.",
            reply_markup=back_markup(
                "ad",
                "⚙️ لوحة الأدمن",
            ),
        )

    if quiz_type not in (
        db.MONTHLY_PREVIOUS,
        db.MONTHLY_CURRENT,
    ):

        context.user_data.pop(
            "await",
            None,
        )

        return await msg.reply_text(
            "⚠️ نوع الأسئلة الشهرية غير صالح.",
            reply_markup=back_markup(
                "ad",
                "⚙️ لوحة الأدمن",
            ),
        )

    if section not in (
        db.SECTION_SHARED,
        db.SECTION_MORNING,
        db.SECTION_EVENING,
    ):

        context.user_data.pop(
            "await",
            None,
        )

        return await msg.reply_text(
            "⚠️ القسم غير صالح.",
            reply_markup=back_markup(
                "ad",
                "⚙️ لوحة الأدمن",
            ),
        )

    # ----------------------------------------------------
    # حفظ الصورة
    # ----------------------------------------------------

    caption = (
        (msg.caption or "").strip()
        or None
    )

    image_id = db.add_monthly_question_image(
        sid=sid,
        quiz_type=quiz_type,
        section=section,
        file_id=file_id,
        caption=caption,
    )

    # ----------------------------------------------------
    # إنهاء الانتظار
    # ----------------------------------------------------

    context.user_data.pop(
        "await",
        None,
    )

    # ----------------------------------------------------
    # تحديد اسم النوع للرسالة
    # ----------------------------------------------------

    if quiz_type == db.MONTHLY_PREVIOUS:

        type_name = "📚 أسئلة شهرية سابقة"

    elif section == db.SECTION_MORNING:

        type_name = "📝 أسئلة الشهر الحالي — ☀️ صباحي"

    else:

        type_name = "📝 أسئلة الشهر الحالي — 🌙 مسائي"

    # ----------------------------------------------------
    # نجاح
    # ----------------------------------------------------

    return await msg.reply_text(
        "✅ تم حفظ أسئلة الشهر بنجاح.\n\n"
        f"{type_name}\n"
        f"🆔 رقم الصورة: {image_id}\n\n"
        "تقدر تضيف صورة أخرى من لوحة الأدمن.",
        reply_markup=again_markup(
            "➕ إضافة صورة أخرى",
            f"ak:mi:{sid}",
        ),
    )
