# -*- coding: utf-8 -*-

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
    context.user_data.pop("await", None)
    context.user_data.pop("ai_text", None)

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
    aw = context.user_data.get("await")

    # -----------------------------------------------------
    # طلب التقرير
    # -----------------------------------------------------

    if (
        aw
        and aw.get("type") == "report"
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
    # النصوص
    # -----------------------------------------------------

    if update.message and update.message.text:
        text = update.message.text.strip()

        if not text:
            return

        # نخزن النص حتى تستخدمه أزرار الذكاء الاصطناعي
        context.user_data["ai_text"] = text

        await update.message.reply_text(
            "🤖 شنو تريد أسوي للنص؟\n\n"
            "اختر نوع التحليل:",
            reply_markup=ai_markup()
        )

        return

    # -----------------------------------------------------
    # الملفات
    # -----------------------------------------------------

    if update.message:
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
    text = context.user_data.get("ai_text")

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
        f"⏳ جاري {title}...\n"
        "انتظر قليلاً."
    )

    try:
        result = await ask_ai(
            mode,
            text
        )

        if not result:
            result = "❌ ما حصلت نتيجة من الذكاء الاصطناعي."

        # Telegram يسمح تقريباً بـ 4096 حرف
        if len(result) <= 4000:
            await status_message.edit_text(
                f"{title}\n\n{result}"
            )
        else:
            await status_message.edit_text(
                f"{title}\n\n{result[:4000]}"
            )

            remaining = result[4000:]

            while remaining:
                chunk = remaining[:4000]
                remaining = remaining[4000:]

                await q.message.reply_text(chunk)

    except Exception as e:
        logger.exception(
            "AI analysis error"
        )

        await status_message.edit_text(
            "❌ صار خطأ أثناء تحليل النص.\n\n"
            f"نوع الخطأ: {type(e).__name__}\n\n"
            "راجع Railway Logs لمعرفة السبب."
        )


# =========================================================
# أزرار الذكاء الاصطناعي
# =========================================================

async def ai_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query

    if not q:
        return

    data = q.data or ""

    if not data.startswith("ai:"):
        return

    mode = data.split(":", 1)[1]

    if mode not in AI_MODES:
        await q.answer(
            "❌ نوع التحليل غير معروف.",
            show_alert=True
        )
        return

    await handle_ai(
        q,
        context,
        mode
    )


# =========================================================
# أخطاء عامة
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):
    logger.exception(
        "Unhandled Telegram error",
        exc_info=context.error
    )


# =========================================================
# تشغيل البوت
# =========================================================

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

    # -----------------------------------------------------
    # الأوامر
    # -----------------------------------------------------

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
            "cancel",
            cancel
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

    # -----------------------------------------------------
    # أزرار الذكاء الاصطناعي
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            ai_callback,
            pattern=r"^ai:"
        )
    )

    # -----------------------------------------------------
    # بقية أزرار البوت
    # -----------------------------------------------------

    app.add_handler(
        CallbackQueryHandler(
            quiz_flow.callback
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            timetable.callback
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            reports.callback
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin.callback
        )
    )

    # -----------------------------------------------------
    # الرسائل النصية
    # -----------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_message
        )
    )

    # -----------------------------------------------------
    # معالج الأخطاء
    # -----------------------------------------------------

    app.add_error_handler(
        error_handler
    )

    print(
        "✅ البوت شغال... اضغط Ctrl+C للإيقاف",
        flush=True
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    main()
