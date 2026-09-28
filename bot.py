# -*- coding: utf-8 -*-
"""المعالج الرئيسي للبوت."""
from telegram import Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
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
    SUB_TEXT, ai_markup, is_admin, is_subscribed, main_menu,
    send_summary, show, sub_markup, subjects_markup,
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("quiz", None)
    context.user_data.pop("await", None)
    context.user_data.pop("ai_text", None)
    context.user_data.pop("retry", None)

    db.upsert_user(
        update.effective_user.id,
        update.effective_user.full_name,
    )

    if not await is_subscribed(context, update.effective_user.id):
        return await update.message.reply_text(
            SUB_TEXT,
            reply_markup=sub_markup(),
        )

    await update.message.reply_text(
        "أهلاً بيك 👋\nاختر من القائمة:",
        reply_markup=main_menu(update.effective_user.id),
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"آيديك: {update.effective_user.id}"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("await", None)
    context.user_data.pop("ai_text", None)

    await update.message.reply_text(
        "تم الإلغاء ✅",
        reply_markup=main_menu(update.effective_user.id),
    )


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not is_admin(uid):
        return await update.message.reply_text(
            f"هذا الأمر للأدمن فقط.\nآيديك: {uid}\n(ضيفه في ADMIN_IDS)"
        )

    await update.message.reply_text(
        "⚙️ لوحة الأدمن:",
        reply_markup=admin.panel_markup(),
    )


async def content_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    text = "\n".join(seed.REPORT) or "ما في تقرير."

    tail = (
        f"\n\n🗄 القاعدة: {backup.counts()}"
        f"\n♻️ آخر استعادة: {backup.LAST_RESTORE}"
    )

    await update.message.reply_text(
        "📂 المحتوى المحمّل من الملفات:\n\n"
        + text[:3200]
        + tail
    )


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    try:
        st = await backup.send_backup(
            context.bot,
            force=True,
        )
    except Exception:
        logger.exception("backup")
        st = "error"

    names = {
        "ok": "✅ انحفظت النسخة (مثبّتة بأعلى هذي المحادثة)",
        "no_chat": "⚠️ ما في أدمن مسجّل بـ ADMIN_IDS",
        "error": "❌ فشل الحفظ، شوف Deploy Logs",
    }

    await update.message.reply_text(
        f"{names.get(st, st)}\n🗄 {backup.counts()}"
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aw = context.user_data.get("await")

    if aw and aw.get("type") == "report":
        return await reports.handle_report_request(
            update,
            context,
        )

    if aw and is_admin(update.effective_user.id):
        return await admin_msg.handle_admin_message(
            update,
            context,
            aw,
        )

    if update.message and update.message.text:
        text = update.message.text.strip()

        if not text:
            return

        context.user_data["ai_text"] = text

        await update.message.reply_text(
            "🤖 شنو تريد أسوي للنص؟\n\n"
            "اختر نوع التحليل:",
            reply_markup=ai_markup(),
        )

        return

    if update.message:
        await update.message.reply_text(
            "📄 استلمت الملف.\n"
            "حالياً تحليل الذكاء الاصطناعي يعمل على النصوص.\n"
            "دعم الصور والملفات راح نضيفه بالمرحلة التالية."
        )


async def handle_ai(q, context, mode):
    text = context.user_data.get("ai_text")

    if not text:
        return await q.message.reply_text(
            "⚠️ ما عندي نص أحلله.\n"
            "أرسل بيت شعر أو جملة أولاً."
        )

    title = AI_MODES.get(
        mode,
        "🤖 تحليل الذكاء الاصطناعي",
    )

    status = await q.message.reply_text(
        f"⏳ جاري {title}...\n"
        "انتظر قليلاً."
    )

    try:
        result = await ask_ai(
            mode,
            text,
        )

        result = result or (
            "❌ ما حصلت نتيجة من الذكاء الاصطناعي."
        )

        if len(result) <= 4000:
            await status.edit_text(
                f"{title}\n\n{result}"
            )

        else:
            await status.edit_text(
                f"{title}\n\n{result[:4000]}"
            )

            remaining = result[4000:]

            while remaining:
                chunk = remaining[:4000]
                remaining = remaining[4000:]

                await q.message.reply_text(chunk)

    except Exception as e:
        logger.exception("AI analysis error")

        await status.edit_text(
            "❌ صار خطأ أثناء تحليل النص.\n\n"
            f"نوع الخطأ: {type(e).__name__}\n"
            "راجع Railway Logs لمعرفة السبب."
        )


async def ai_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""

    mode = (
        data.split(":", 1)[1]
        if ":" in data
        else ""
    )

    if mode not in AI_MODES:
        return await q.answer(
            "❌ نوع التحليل غير معروف.",
            show_alert=True,
        )

    await handle_ai(
        q,
        context,
        mode,
    )


async def callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    معالج واحد لكل أزرار البوت.
    هذا يمنع تعارض CallbackQueryHandler.
    """

    q = update.callback_query

    if not q:
        return

    data = q.data or ""

    # نجاوب على ضغط الزر مرة واحدة فقط.
    await q.answer()

    # =========================
    # الذكاء الاصطناعي
    # =========================

    if data.startswith("ai:"):
        mode = data.split(":", 1)[1]

        if mode not in AI_MODES:
            return await q.message.reply_text(
                "❌ نوع التحليل غير معروف."
            )

        return await handle_ai(
            q,
            context,
            mode,
        )

    # =========================
    # القائمة الرئيسية
    # =========================

    if data == "m":
        return await show(
            q,
            "أهلاً بيك 👋\nاختر من القائمة:",
            main_menu(q.from_user.id),
        )

    # =========================
    # الاشتراك
    # =========================

    if data == "chk":
        ok = await is_subscribed(
            context,
            q.from_user.id,
            force=True,
        )

        if ok:
            return await show(
                q,
                "✅ تم التحقق من الاشتراك.\n"
                "اختر من القائمة:",
                main_menu(q.from_user.id),
            )

        return await show(
            q,
            SUB_TEXT,
            sub_markup(),
        )

    # =========================
    # الملخصات
    # =========================

    if data == "sm":
        return await show(
            q,
            "📄 اختر المادة:",
            subjects_markup(
                "sdm",
                "s_count",
                "m",
            ),
        )

    if data.startswith("sdm:"):
        sid = int(
            data.split(":", 1)[1]
        )

        import ui

        return await ui.summaries_list(
            q,
            sid,
        )

    if data.startswith("sd:"):
        sid = int(
            data.split(":", 1)[1]
        )

        return await send_summary(
            q,
            sid,
        )

    # =========================
    # الاختبارات
    # =========================

    if data == "qm":
        context.user_data.pop(
            "quiz",
            None,
        )

        context.user_data.pop(
            "retry",
            None,
        )

        return await show(
            q,
            "📝 اختر المادة:",
            subjects_markup(
                "qs",
                "q_count",
                "m",
            ),
        )

    # اختيار المادة
    if data.startswith("qs:"):
        sid = int(
            data.split(":", 1)[1]
        )

        return await quiz.show_subject_quiz(
            q,
            q.from_user.id,
            sid,
        )

    # بدء الاختبار
    if data.startswith("startq:"):
        sid = int(
            data.split(":", 1)[1]
        )

        return await quiz.start_quiz(
            q,
            context,
            sid,
        )

    # الإجابة
    if data.startswith("a:"):
        return await quiz_flow.answer(
            q,
            context,
            data[2:],
        )

    # السؤال التالي
    if data == "n":
        return await quiz_flow.next_question(
            q,
            context,
        )

    # إعادة الأسئلة الغلط
    if data == "rw":
        return await quiz.retry_wrong(
            q,
            context,
        )

    # النتائج
    if data == "me":
        return await quiz.show_stats(
            q,
            q.from_user.id,
        )

    # =========================
    # الجدول
    # =========================

    if data == "sc":
        return await timetable.open_menu(
            q,
            q.from_user.id,
        )

    if data == "scchg":
        return await timetable.change_section(q)

    if data.startswith("scset:"):
        section = data.split(
            ":",
            1,
        )[1]

        return await timetable.set_section(
            q,
            context,
            section,
        )

    if data.startswith("scday:"):
        day = data.split(
            ":",
            1,
        )[1]

        return await timetable.show_day(
            q,
            q.from_user.id,
            day,
        )

    # =========================
    # التقارير والتواصل
    # =========================

    if data == "rp":
        return await reports.show_report_info(q)

    if data == "rp1":
        return await reports.ask_report(
            q,
            context,
        )

    if data == "ct":
        return await reports.show_contact(q)

    # =========================
    # الأدمن
    # =========================

    action = data.split(
        ":",
        1,
    )[0]

    if action in {
        "ad",
        "ap",
        "ak",
        "ay",
        "ds",
    }:
        arg = (
            data.split(":", 1)[1]
            if ":" in data
            else ""
        )

        if not is_admin(q.from_user.id):
            return await show(
                q,
                "⛔ هذا القسم للأدمن فقط.",
                main_menu(q.from_user.id),
            )

        return await admin.router(
            q,
            context,
            action,
            arg,
        )

    await q.message.reply_text(
        "⚠️ هذا الزر قديم أو غير معروف.\n"
        "استخدم /start."
    )


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.exception(
        "Unhandled Telegram error",
        exc_info=context.error,
    )


def main():
    if not BOT_TOKEN:
        raise SystemExit(
            "❌ حط التوكن في متغير البيئة BOT_TOKEN"
        )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(backup.startup)
        .post_stop(backup.shutdown)
        .build()
    )

    # =========================
    # Commands
    # =========================

    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        CommandHandler(
            "myid",
            myid,
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            cancel,
        )
    )

    app.add_handler(
        CommandHandler(
            "admin",
            admin_cmd,
        )
    )

    app.add_handler(
        CommandHandler(
            "content",
            content_cmd,
        )
    )

    app.add_handler(
        CommandHandler(
            "backup",
            backup_cmd,
        )
    )

    # =========================
    # Callback واحد فقط
    # =========================

    app.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    # =========================
    # الرسائل النصية
    # =========================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_message,
        )
    )

    app.add_error_handler(
        error_handler
    )

    print(
        "✅ البوت شغال... اضغط Ctrl+C للإيقاف",
        flush=True,
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
