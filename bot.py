# -*- coding: utf-8 -*-

import datetime as dt

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import admin
import admin_msg
import backup
import db
import quiz
import quiz_flow
import reports
import seed
import timetable

from config import BOT_TOKEN, logger

from ui import (
    SUB_TEXT,
    ai_markup,
    is_admin,
    is_subscribed,
    main_menu,
    send_summary,
    show,
    sub_markup,
    subjects_markup,
    summaries_list,
)

from ai import ask_ai


# =========================================================
# أوضاع الذكاء الاصطناعي
# =========================================================

AI_MODES = {
    "grammar": "📌 الإعراب المفصل",
    "rhetoric": "🎨 التحليل البلاغي",
    "morphology": "⚖️ الصرف والبنية",
    "dictionary": "📖 معجم المفردات",
    "explain": "📝 شرح النص",
    "prosody": "🪶 العروض والقافية",
    "poet": "👤 الشاعر والعصر",
}


# =========================================================
# /start
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data.pop("quiz", None)
    context.user_data.pop("await", None)
    context.user_data.pop("ai_text", None)

    db.upsert_user(
        update.effective_user.id,
        update.effective_user.full_name
    )

    if not await is_subscribed(
        context,
        update.effective_user.id
    ):
        return await update.message.reply_text(
            SUB_TEXT,
            reply_markup=sub_markup()
        )

    await update.message.reply_text(
        "أهلاً بيك 👋\nاختر من القائمة:",
        reply_markup=main_menu(
            update.effective_user.id
        )
    )


# =========================================================
# /myid
# =========================================================

async def myid(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        f"آيديك: {update.effective_user.id}"
    )


# =========================================================
# /cancel
# =========================================================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data.pop(
        "await",
        None
    )

    context.user_data.pop(
        "ai_text",
        None
    )

    await update.message.reply_text(
        "تم الإلغاء ✅",
        reply_markup=main_menu(
            update.effective_user.id
        )
    )


# =========================================================
# /admin
# =========================================================

async def admin_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    uid = update.effective_user.id

    if not is_admin(uid):
        return await update.message.reply_text(
            f"هذا الأمر للأدمن فقط.\n"
            f"آيديك: {uid}\n"
            f"(ضيفه في ADMIN_IDS)"
        )

    await update.message.reply_text(
        "⚙️ لوحة الأدمن:",
        reply_markup=admin.panel_markup()
    )


# =========================================================
# /content
# =========================================================

async def content_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(
        update.effective_user.id
    ):
        return

    text = (
        "\n".join(seed.REPORT)
        or "ما في تقرير."
    )

    tail = (
        f"\n\n🗄 القاعدة: {backup.counts()}"
        f"\n♻️ آخر استعادة: {backup.LAST_RESTORE}"
    )

    await update.message.reply_text(
        "📂 المحتوى المحمّل من الملفات:\n\n"
        + text[:3200]
        + tail
    )


# =========================================================
# /backup
# =========================================================

async def backup_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(
        update.effective_user.id
    ):
        return

    try:
        st = await backup.send_backup(
            context.bot,
            force=True
        )

    except Exception:
        logger.exception("backup")
        st = "error"

    names = {
        "ok":
            "✅ انحفظت النسخة "
            "(مثبّتة بأعلى هذي المحادثة)",

        "no_chat":
            "⚠️ ما في أدمن مسجّل بـ ADMIN_IDS",

        "error":
            "❌ فشل الحفظ، شوف Deploy Logs",
    }

    await update.message.reply_text(
        f"{names.get(st, st)}\n"
        f"🗄 {backup.counts()}"
    )


# =========================================================
# استقبال الرسائل
# =========================================================

async def on_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    aw = context.user_data.get(
        "await"
    )

    # -----------------------------------------------------
    # طلب التقرير
    # -----------------------------------------------------

    if (
        aw
        and aw["type"] == "report"
    ):
        return await reports.handle_report_request(
            update,
            context
        )

    # -----------------------------------------------------
    # رسائل الأدمن
    # -----------------------------------------------------

    if (
        aw
        and is_admin(
            update.effective_user.id
        )
    ):
        return await admin_msg.handle_admin_message(
            update,
            context,
            aw
        )

    # -----------------------------------------------------
    # إذا المستخدم أرسل نصاً
    # -----------------------------------------------------

    if update.message and update.message.text:

        text = update.message.text.strip()

        if not text:
            return

        # حفظ النص حتى تستخدمه أزرار الذكاء الاصطناعي
        context.user_data["ai_text"] = text

        await update.message.reply_text(
            "🤖 شنو تريد أسوي للنص؟\n\n"
            "اختر نوع التحليل:",
            reply_markup=ai_markup()
        )

        return

    # -----------------------------------------------------
    # إذا أرسل ملفاً أو مستنداً
    # -----------------------------------------------------

    await update.message.reply_text(
        "📄 استلمت الملف.\n"
        "حالياً تحليل الذكاء الاصطناعي يعمل على النصوص.\n"
        "دعم الصور والملفات راح نضيفه بالمرحلة التالية."
    )


# =========================================================
# معالجة الذكاء الاصطناعي
# =========================================================

async def handle_ai(
    q,
    context,
    mode
):

    text = context.user_data.get(
        "ai_text"
    )

    if not text:
        return await q.message.reply_text(
            "⚠️ ما عندي نص أحلله.\n"
            "أرسل بيت شعر أو جملة أولاً."
        )

    title = AI_MODES.get(
        mode,
        "🤖 تحليل الذكاء الاصطناعي"
    )

    try:

        result = await ask_ai(
            mode,
            text
        )

        await q.message.reply_text(
            f"{title}\n\n{result}"
        )

    except Exception as e:

        logger.exception(
            "AI callback failed"
        )

        await q.message.reply_text(
            "❌ صار خطأ أثناء تحليل النص.\n\n"
            f"نوع الخطأ: {type(e).__name__}\n"
            "راجع Railway Logs."
        )


# =========================================================
# معالجة جميع أزرار البوت
# =========================================================

async def callbacks(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    q = update.callback_query

    await q.answer()

    data = q.data or ""

    # =====================================================
    # الذكاء الاصطناعي
    # =====================================================

    if data.startswith("ai:"):

        mode = data.split(
            ":",
            1
        )[1]

        text = context.user_data.get(
            "ai_text"
        )

        if not text:

            return await q.message.reply_text(
                "⚠️ ما عندي نص أحلله.\n"
                "أرسل بيت شعر أو جملة أولاً."
            )

        status_message = await q.message.reply_text(
            "🤖 جاري التحليل بالذكاء الاصطناعي...\n"
            "⏳ انتظر قليلاً."
        )

        try:

            result = await ask_ai(
                mode,
                text
            )

            title = AI_MODES.get(
                mode,
                "🤖 تحليل الذكاء الاصطناعي"
            )

            await status_message.edit_text(
                f"{title}\n\n{result}"
            )

        except Exception as e:

            logger.exception(
                "AI callback failed"
            )

            await status_message.edit_text(
                "❌ صار خطأ أثناء تحليل النص.\n\n"
                f"نوع الخطأ: {type(e).__name__}\n\n"
                "راجع Railway Logs لمعرفة السبب."
            )

        return

    # =====================================================
    # القائمة الرئيسية
    # =====================================================

    if data == "m":

        return await show(
            q,
            "أهلاً بيك 👋\nاختر من القائمة:",
            main_menu(
                q.from_user.id
            )
        )

    # =====================================================
    # الاشتراك
    # =====================================================

    if data == "chk":

        ok = await is_subscribed(
            context,
            q.from_user.id,
            force=True
        )

        if not ok:

            return await show(
                q,
                SUB_TEXT,
                sub_markup()
            )

        return await show(
            q,
            "✅ تم التحقق من الاشتراك.\n"
            "أهلاً بيك، اختر من القائمة:",
            main_menu(
                q.from_user.id
            )
        )

    # =====================================================
    # الملخصات
    # =====================================================

    if data == "sm":

        return await show(
            q,
            "📄 اختر المادة:",
            subjects_markup(
                "ss",
                "summaries_count",
                "m"
            )
        )

    if data.startswith("ss:"):

        try:
            sid = int(
                data.split(
                    ":",
                    1
                )[1]
            )
        except ValueError:
            return

        return await summaries_list(
            q,
            sid
        )

    if data.startswith("sd:"):

        try:
            sum_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )
        except ValueError:
            return

        return await send_summary(
            q,
            sum_id
        )

    # =====================================================
    # الاختبارات
    # =====================================================

    if data == "qm":

        return await show(
            q,
            "📝 اختر المادة:",
            subjects_markup(
                "qsub",
                "questions_count",
                "m"
            )
        )

    if data.startswith("qsub:"):

        try:
            sid = int(
                data.split(
                    ":",
                    1
                )[1]
            )
        except ValueError:
            return

        return await quiz.show_subject_quiz(
            q,
            q.from_user.id,
            sid
        )

    if data.startswith("qs:"):

        try:
            sid = int(
                data.split(
                    ":",
                    1
                )[1]
            )
        except ValueError:
            return

        return await quiz.start_quiz(
            q,
            context,
            sid
        )

    if data.startswith("a:"):

        arg = data.split(
            ":",
            1
        )[1]

        return await quiz_flow.answer(
            q,
            context,
            arg
        )

    if data == "n":

        return await quiz_flow.next_question(
            q,
            context
        )

    if data == "rw":

        return await quiz.retry_wrong(
            q,
            context
        )

    # =====================================================
    # النتائج
    # =====================================================

    if data == "me":

        return await quiz.show_stats(
            q,
            q.from_user.id
        )

    # =====================================================
    # الجدول الأسبوعي
    # =====================================================

    if data == "sc":

        return await timetable.open_menu(
            q,
            q.from_user.id
        )

    if data.startswith("scset:"):

        section = data.split(
            ":",
            1
        )[1]

        return await timetable.set_section(
            q,
            context,
            section
        )

    if data == "scchg":

        return await timetable.change_section(
            q
        )

    if data.startswith("scday:"):

        day = data.split(
            ":",
            1
        )[1]

        return await timetable.show_day(
            q,
            q.from_user.id,
            day
        )

    # =====================================================
    # التواصل
    # =====================================================

    if data == "ct":

        return await reports.show_contact(
            q
        )

    # =====================================================
    # التقارير
    # =====================================================

    if data == "rp":

        return await reports.show_report_info(
            q
        )

    if data == "rp1":

        return await reports.ask_report(
            q,
            context
        )

    # =====================================================
    # الأدمن
    # =====================================================

    if data == "ad":

        if not is_admin(
            q.from_user.id
        ):
            return

        return await show(
            q,
            "⚙️ لوحة الأدمن:",
            admin.panel_markup()
        )

    if data.startswith("ap:"):

        if not is_admin(
            q.from_user.id
        ):
            return

        arg = data.split(
            ":",
            1
        )[1]

        return await admin.router(
            q,
            context,
            "ap",
            arg
        )

    if data.startswith("ak:"):

        if
