# -*- coding: utf-8 -*-

"""المعالج الرئيسي للبوت."""

import os
import asyncio
import tempfile

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
)

from ai import ask_ai

# ============================================================
# Gemini Voice Transcription
# ============================================================

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    "",
).strip()

VOICE_MODEL = os.getenv(
    "VOICE_MODEL",
    "gemini-3.5-transcribe",
).strip()

voice_client = None

if GEMINI_API_KEY and genai is not None:
    try:
        voice_client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
                api_version="v1",
                timeout=60000,
            ),
        )

        logger.info(
            "Gemini Voice client initialized: %s",
            VOICE_MODEL,
        )

    except Exception:
        logger.exception(
            "Failed to initialize Gemini Voice client."
        )
        voice_client = None

else:
    logger.warning(
        "Gemini Voice client not initialized."
    )


# ============================================================
# AI Modes
# ============================================================

AI_MODES = {
    "grammar": "📌 الإعراب المفصل",
    "rhetoric": "🎨 التحليل البلاغي",
    "morphology": "⚖️ الصرف والبنية",
    "dictionary": "📖 معجم المفردات",
    "explain": "📝 شرح النص",
    "prosody": "🪶 العروض والقافية",
    "poet": "👤 الشاعر والعصر",
}


# ============================================================
# Voice → Text
# ============================================================

def _transcribe_voice_file(file_path):
    """
    تحويل الملف الصوتي إلى نص باستخدام Gemini.
    """

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY غير موجود."
        )

    if voice_client is None:
        raise RuntimeError(
            "تعذر إنشاء اتصال Gemini للصوت."
        )

    logger.info(
        "Uploading voice file to Gemini..."
    )

    audio_file = voice_client.files.upload(
        file=file_path
    )

    logger.info(
        "Voice file uploaded successfully."
    )

    interaction = voice_client.interactions.create(
        model=VOICE_MODEL,
        input=[
            {
                "type": "audio",
                "uri": audio_file.uri,
                "mime_type": audio_file.mime_type,
            }
        ],
        generation_config={
            "transcription_config": {
                "mode": "smart",
                "language_codes": ["ar"],
            }
        },
    )

    if not interaction:
        raise RuntimeError(
            "Gemini أعاد استجابة فارغة."
        )

    result = getattr(
        interaction,
        "output_text",
        None,
    )

    if not result:
        raise RuntimeError(
            "Gemini لم يرجع نصاً للصوت."
        )

    return result.strip()


async def transcribe_voice(file_path):
    """
    تشغيل تحويل الصوت خارج event loop
    حتى لا يتجمّد البوت.
    """

    return await asyncio.to_thread(
        _transcribe_voice_file,
        file_path,
    )


async def handle_voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    استقبال الرسالة الصوتية وتحويلها إلى نص.
    """

    if not update.message:
        return

    voice = update.message.voice

    if not voice:
        return

    status = await update.message.reply_text(
        "🎙️ استلمت الصوت.\n"
        "⏳ جاري تحويله إلى نص..."
    )

    temp_path = None

    try:
        # تحميل الصوت من Telegram
        telegram_file = await context.bot.get_file(
            voice.file_id
        )

        # ملف مؤقت
        with tempfile.NamedTemporaryFile(
            suffix=".ogg",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name

        # تنزيل الصوت
        await telegram_file.download_to_drive(
            custom_path=temp_path
        )

        logger.info(
            "Voice downloaded: %s",
            temp_path,
        )

        # تحويل الصوت إلى نص
        text = await transcribe_voice(
            temp_path
        )

        if not text:
            await status.edit_text(
                "❌ ما قدرت أستخرج كلام واضح من التسجيل."
            )
            return

        # نخزن النص حتى نستخدمه مع الذكاء الاصطناعي
        context.user_data["ai_text"] = text

        # عرض النص للمستخدم
        await status.edit_text(
            "🎙️ النص المستخرج:\n\n"
            + text[:3900]
        )

        # إذا النص طويل جداً، نرسل الباقي
        if len(text) > 3900:
            remaining = text[3900:]

            while remaining:
                chunk = remaining[:4000]
                remaining = remaining[4000:]

                await update.message.reply_text(
                    chunk
                )

        # أزرار التحليل
        await update.message.reply_text(
            "🤖 شنو تريد أسوي للنص؟\n\n"
            "اختر نوع التحليل:",
            reply_markup=ai_markup(),
        )

    except Exception as error:
        logger.exception(
            "Voice transcription error."
        )

        error_text = str(error).upper()

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):
            message = (
                "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n\n"
                "انتظر قليلاً وحاول مرة ثانية."
            )

        elif (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):
            message = (
                "⚠️ Gemini مشغول حالياً.\n\n"
                "حاول مرة ثانية بعد قليل."
            )

        elif (
            "504" in error_text
            or "TIMEOUT" in error_text
            or "DEADLINE" in error_text
        ):
            message = (
                "⏱️ تحويل الصوت أخذ وقتاً أطول من المتوقع.\n\n"
                "حاول تسجيل مقطع أقصر وإرساله مرة ثانية."
            )

        else:
            message = (
                "❌ صار خطأ أثناء تحويل الصوت إلى نص.\n\n"
                "تأكد من Railway Logs."
            )

        try:
            await status.edit_text(
                message
            )
        except Exception:
            await update.message.reply_text(
                message
            )

    finally:
        # حذف الملف المؤقت
        if temp_path:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                logger.exception(
                    "Failed to remove temporary voice file."
                )


# ============================================================
# Start
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop(
        "quiz",
        None,
    )

    context.user_data.pop(
        "await",
        None,
    )

    context.user_data.pop(
        "ai_text",
        None,
    )

    context.user_data.pop(
        "retry",
        None,
    )

    db.upsert_user(
        update.effective_user.id,
        update.effective_user.full_name,
    )

    if not await is_subscribed(
        context,
        update.effective_user.id,
    ):
        return await update.message.reply_text(
            SUB_TEXT,
            reply_markup=sub_markup(),
        )

    await update.message.reply_text(
        "أهلاً بيك 👋\n"
        "اختر من القائمة:",
        reply_markup=main_menu(
            update.effective_user.id
        ),
    )


# ============================================================
# My ID
# ============================================================

async def myid(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        f"آيديك: {update.effective_user.id}"
    )


# ============================================================
# Cancel
# ============================================================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop(
        "await",
        None,
    )

    context.user_data.pop(
        "ai_text",
        None,
    )

    await update.message.reply_text(
        "تم الإلغاء ✅",
        reply_markup=main_menu(
            update.effective_user.id
        ),
    )


# ============================================================
# Admin
# ============================================================

async def admin_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
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
        reply_markup=admin.panel_markup(),
    )


# ============================================================
# Content
# ============================================================

async def content_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(
        update.effective_user.id
    ):
        return

    text = "\n".join(seed.REPORT)

    if not text:
        text = "ما في تقرير."

    tail = (
        f"\n\n🗄 القاعدة: {backup.counts()}"
        f"\n♻️ آخر استعادة: {backup.LAST_RESTORE}"
    )

    await update.message.reply_text(
        "📂 المحتوى المحمّل من الملفات:\n\n"
        + text[:3200]
        + tail
    )


# ============================================================
# Backup
# ============================================================

async def backup_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(
        update.effective_user.id
    ):
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
        "ok": (
            "✅ انحفظت النسخة "
            "(مثبّتة بأعلى هذي المحادثة)"
        ),
        "no_chat": (
            "⚠️ ما في أدمن مسجّل بـ ADMIN_IDS"
        ),
        "error": (
            "❌ فشل الحفظ، شوف Deploy Logs"
        ),
    }

    await update.message.reply_text(
        f"{names.get(st, st)}\n"
        f"🗄 {backup.counts()}"
    )


# ============================================================
# Text Messages
# ============================================================

async def on_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    aw = context.user_data.get(
        "await"
    )

    # تقرير
    if aw and aw.get("type") == "report":
        return await reports.handle_report_request(
            update,
            context,
        )

    # رسائل الأدمن
    if aw and is_admin(
        update.effective_user.id
    ):
        return await admin_msg.handle_admin_message(
            update,
            context,
            aw,
        )

    # النصوص
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
            "حالياً تحليل الذكاء الاصطناعي يعمل "
            "على النصوص والصوت.\n"
            "دعم الصور والملفات راح نضيفه بالمرحلة التالية."
        )


# ============================================================
# AI Handler
# ============================================================

async def handle_ai(
    q,
    context,
    mode,
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

                await q.message.reply_text(
                    chunk
                )

    except Exception as e:

        logger.exception(
            "AI analysis error"
        )

        await status.edit_text(
            "❌ صار خطأ أثناء تحليل النص.\n\n"
            f"نوع الخطأ: {type(e).__name__}\n"
            "راجع Railway Logs لمعرفة السبب."
        )


# ============================================================
# AI Callback
# ============================================================

async def ai_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
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


# ============================================================
# Callback Router
# ============================================================

async def callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    معالج واحد لكل أزرار البوت.
    """

    q = update.callback_query

    if not q:
        return

    data = q.data or ""

    # نجاوب على ضغط الزر مرة واحدة
    await q.answer()

    # ========================================================
    # الذكاء الاصطناعي
    # ========================================================

    if data.startswith("ai:"):

        mode = data.split(
            ":",
            1,
        )[1]

        if mode not in AI_MODES:

            return await q.message.reply_text(
                "❌ نوع التحليل غير معروف."
            )

        return await handle_ai(
            q,
            context,
            mode,
        )

    # ========================================================
    # القائمة الرئيسية
    # ========================================================

    if data == "m":

        return await show(
            q,
            "أهلاً بيك 👋\n"
            "اختر من القائمة:",
            main_menu(
                q.from_user.id
            ),
        )

    # ========================================================
    # الاشتراك
    # ========================================================

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
                main_menu(
                    q.from_user.id
                ),
            )

        return await show(
            q,
            SUB_TEXT,
            sub_markup(),
        )

    # ========================================================
    # الملخصات
    # ========================================================

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
            data.split(
                ":",
                1,
            )[1]
        )

        import ui

        return await ui.summaries_list(
            q,
            sid,
        )

    if data.startswith("sd:"):

        sid = int(
            data.split(
                ":",
                1,
            )[1]
        )

        return await send_summary(
            q,
            sid,
        )

    # ========================================================
    # الاختبارات
    # ========================================================

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
            data.split(
                ":",
                1,
            )[1]
        )

        return await quiz.show_subject_quiz(
            q,
            q.from_user.id,
            sid,
        )

    # بدء الاختبار
    if data.startswith("startq:"):

        sid = int(
            data.split(
                ":",
                1,
            )[1]
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

    # ========================================================
    # الجدول
    # ========================================================

    if data == "sc":

        return await timetable.open_menu(
            q,
            q.from_user.id,
        )

    if data == "scchg":

        return await timetable.change_section(
            q
        )

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

    # ========================================================
    # التقارير والتواصل
    # ========================================================

    if data == "rp":

        return await reports.show_report_info(
            q
        )

    if data == "rp1":

        return await reports.ask_report(
            q,
            context,
        )

    if data == "ct":

        return await reports.show_contact(
            q
        )

    # ========================================================
    # الأدمن
    # ========================================================

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
            data.split(
                ":",
                1,
            )[1]
            if ":" in data
            else ""
        )

        if not is_admin(
            q.from_user.id
        ):

            return await show(
                q,
                "⛔ هذا القسم للأدمن فقط.",
                main_menu(
                    q.from_user.id
                ),
            )

        return await admin.router(
            q,
            context,
            action,
            arg,
        )

    # زر غير معروف
    await q.message.reply_text(
        "⚠️ هذا الزر قديم أو غير معروف.\n"
        "استخدم /start."
    )


# ============================================================
# Error Handler
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.exception(
        "Unhandled Telegram error",
        exc_info=context.error,
    )


# ============================================================
# Main
# ============================================================

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

    # ========================================================
    # Commands
    # ========================================================

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

    # ========================================================
    # Callback واحد
    # ========================================================

    app.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    # ========================================================
    # الصوت
    # مهم: قبل معالج النصوص
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.VOICE,
            handle_voice,
        )
    )

    # ========================================================
    # الرسائل النصية
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_message,
        )
    )

    # ========================================================
    # Errors
    # ========================================================

    app.add_error_handler(
        error_handler
    )

    print(
        "✅ البوت شغال... اضغط Ctrl+C للإيقاف",
        flush=True,
    )

    # ========================================================
    # Polling
    # ========================================================

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    main()
