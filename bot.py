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


AI_MODES = {
    "grammar": "📌 الإعراب المفصل",
    "rhetoric": "🎨 التحليل البلاغي",
    "morphology": "⚖️ الصرف والبنية",
    "dictionary": "📖 معجم المفردات",
    "explain": "📝 شرح النص",
    "prosody": "🪶 العروض والقافية",
    "poet": "👤 الشاعر والعصر",
}


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data.pop(
        "quiz",
        None
    )

    context.user_data.pop(
        "await",
        None
    )

    context.user_data.pop(
        "ai_text",
        None
    )

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


async def myid(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        f"آيديك: {update.effective_user.id}"
    )


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


async def on_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    aw = context.user_data.get(
        "await"
    )

    # طلب التقرير
    if (
        aw
        and aw["type"] == "report"
    ):

        return await reports.handle_report_request(
            update,
            context
        )

    # رسائل الأدمن
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

    # إذا المستخدم أرسل نصاً
    if update.message and update.message.text:

        text = update.message.text.strip()

        if not text:

            return

        # نحفظ النص حتى تستخدمه أزرار التحليل
        context.user_data["ai_text"] = text

        await update.message.reply_text(
            "🤖 شنو تريد أسوي للنص؟\n\n"
            "اختر نوع التحليل:",
            reply_markup=ai_markup()
        )

        return

    # إذا أرسل ملفاً أو مستنداً
    await update.message.reply_text(
        "📄 استلمت الملف.\n"
        "حالياً تحليل الذكاء الاصطناعي يعمل على النصوص.\n"
        "دعم الصور والملفات راح نضيفه بالمرحلة التالية."
    )


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

    await q.answer()

    status_message = await q.message.reply_text(
        f"{title}\n\n"
        "⏳ جاري التحليل..."
    )

    try:

        result = await ask_ai(
            text,
            mode
        )

        # Telegram يسمح تقريباً بـ 4096 حرف للرسالة.
        # نقسم النتيجة إذا كانت طويلة.

        chunks = [
            result[i:i + 3900]
            for i in range(
                0,
                len(result),
                3900
            )
        ]

        await status_message.edit_text(
            f"{title}\n\n"
            f"{chunks[0]}"
        )

        for chunk in chunks[1:]:

            await q.message.reply_text(
                chunk
            )

    except Exception as e:

        logger.exception(
            "Gemini AI error"
        )

        try:

            await status_message.edit_text(
                "❌ صار خطأ أثناء الاتصال "
                "بـ Gemini.\n\n"
                "تأكد من:\n"
                "1. GEMINI_API_KEY موجود في Railway.\n"
                "2. مكتبة google-genai موجودة في requirements.txt.\n"
                "3. انتظر حتى يكتمل Deploy."
            )

        except Exception:

            await q.message.reply_text(
                "❌ صار خطأ أثناء تحليل النص."
            )


async def on_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    q = update.callback_query

    uid = q.from_user.id

    action, _, arg = q.data.partition(":")

    # ---------- التحقق من الاشتراك ----------

    if action == "chk":

        if await is_subscribed(
            context,
            uid,
            force=True
        ):

            await q.answer()

            return await show(
                q,
                "أهلاً بيك 👋\n"
                "اختر من القائمة:",
                main_menu(uid)
            )

        return await q.answer(
            "لسا ما اشتركت بالقناة ❌",
            show_alert=True
        )

    if not await is_subscribed(
        context,
        uid
    ):

        await q.answer()

        return await show(
            q,
            SUB_TEXT,
            sub_markup()
        )

    # ---------- الذكاء الاصطناعي ----------

    if action == "ai":

        if arg not in AI_MODES:

            return await q.answer(
                "خيار غير معروف ❌",
                show_alert=True
            )

        return await handle_ai(
            q,
            context,
            arg
        )

    # ---------- الاختبارات ----------

    if action == "a":

        return await quiz_flow.answer(
            q,
            context,
            arg
        )

    await q.answer()

    # ---------- الأدمن ----------

    if action in admin.ACTIONS:

        if not is_admin(uid):

            return await q.message.reply_text(
                "هذا للأدمن فقط."
            )

        return await admin.router(
            q,
            context,
            action,
            arg
        )

    # ---------- القائمة الرئيسية ----------

    if action == "m":

        context.user_data.pop(
            "await",
            None
        )

        await show(
            q,
            "اختر من القائمة:",
            main_menu(uid)
        )

    # ---------- الملخصات ----------

    elif action == "sm":

        await show(
            q,
            "📄 اختر المادة (الملخصات):",
            subjects_markup(
                "s",
                "s_count"
            )
        )

    elif action == "s":

        await summaries_list(
            q,
            int(arg)
        )

    elif action == "sd":

        await send_summary(
            q,
            int(arg)
        )

    # ---------- الاختبارات ----------

    elif action == "qm":

        await show(
            q,
            "📝 اختر المادة (الاختبارات):",
            subjects_markup(
                "q",
                "q_count"
            )
        )

    elif action == "q":

        await quiz.show_subject_quiz(
            q,
            uid,
            int(arg)
        )

    elif action == "qs":

        await quiz.start_quiz(
            q,
            context,
            int(arg)
        )

    elif action == "rw":

        await quiz.retry_wrong(
            q,
            context
        )

    elif action == "n":

        await quiz_flow.next_question(
            q,
            context
        )

    elif action == "me":

        await quiz.show_stats(
            q,
            uid
        )

    # ---------- التواصل ----------

    elif action == "ct":

        await reports.show_contact(
            q
        )

    elif action == "rp":

        await reports.show_report_info(
            q
        )

    elif action == "rp1":

        await reports.ask_report(
            q,
            context
        )

    # ---------- الجدول ----------

    elif action == "sc":

        await timetable.open_menu(
            q,
            uid
        )

    elif action == "scset":

        await timetable.set_section(
            q,
            context,
            arg
        )

    elif action == "scday":

        await timetable.show_day(
            q,
            uid,
            arg
        )

    elif action == "scchg":

        await timetable.change_section(
            q
        )


async def on_error(
    update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Unhandled error",
        exc_info=context.error
    )


def main():

    if not BOT_TOKEN:

        raise SystemExit(
            "❌ حط التوكن في متغير البيئة "
            "BOT_TOKEN (شوف README.md)"
        )

    app = (
        Application.builder()

        .token(BOT_TOKEN)

        .post_init(
            backup.startup
        )

        .post_stop(
            backup.shutdown
        )

        .connect_timeout(30)

        .read_timeout(30)

        .write_timeout(30)

        .pool_timeout(30)

        .get_updates_connect_timeout(30)

        .get_updates_read_timeout(30)

        .get_updates_write_timeout(30)

        .get_updates_pool_timeout(30)

        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "myid",
            myid
        )
    )

    app.add_handler(
        CommandHandler(
            "admin",
            admin_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            cancel
        )
    )

    app.add_handler(
        CommandHandler(
            "content",
            content_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "backup",
            backup_cmd
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            on_button
        )
    )

    app.add_handler(
        MessageHandler(
            (
                filters.TEXT
                & ~filters.COMMAND
            )
            | filters.Document.ALL,
            on_message
        )
    )

    app.add_error_handler(
        on_error
    )

    from zoneinfo import ZoneInfo

    app.job_queue.run_daily(
        timetable.send_daily_reminders,

        time=dt.time(
            21,
            0,
            tzinfo=ZoneInfo(
                "Asia/Baghdad"
            )
        ),

        name="daily_schedule_reminder"
    )

    print(
        "✅ البوت شغال... "
        "اضغط Ctrl+C للإيقاف"
    )

    app.run_polling()


if __name__ == "__main__":

    main()
