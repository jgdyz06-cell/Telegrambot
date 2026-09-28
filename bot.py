# -*- coding: utf-8 -*-

"""المعالج الرئيسي للبوت."""

import os
import asyncio
import tempfile
import datetime as dt
from zoneinfo import ZoneInfo

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
# Gemini Voice
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

        if types is not None:

            voice_client = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options=types.HttpOptions(
                    api_version="v1",
                    timeout=60000,
                ),
            )

        else:

            voice_client = genai.Client(
                api_key=GEMINI_API_KEY,
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
# أدوات عامة
# ============================================================

async def safe_answer(q):

    try:
        await q.answer()
    except Exception:
        pass


async def send_long_message(
    message,
    text,
    reply_markup=None,
):

    if not text:
        return

    max_len = 3900

    if len(text) <= max_len:

        await message.reply_text(
            text,
            reply_markup=reply_markup,
        )

        return

    first = True

    while text:

        chunk = text[:max_len]
        text = text[max_len:]

        await message.reply_text(
            chunk,
            reply_markup=(
                reply_markup
                if first and not text
                else None
            ),
        )

        first = False


async def check_access(
    update,
    context,
):

    user = update.effective_user

    if not user:
        return False

    db.upsert_user(
        user.id,
        user.full_name,
    )

    if is_admin(user.id):
        return True

    ok = await is_subscribed(
        context,
        user.id,
    )

    if ok:
        return True

    if update.callback_query:

        await show(
            update.callback_query,
            SUB_TEXT,
            sub_markup(),
        )

    elif update.message:

        await update.message.reply_text(
            SUB_TEXT,
            reply_markup=sub_markup(),
        )

    return False


# ============================================================
# Voice → Text
# ============================================================

def _transcribe_voice_file(file_path):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY غير موجود."
        )

    if voice_client is None:

        raise RuntimeError(
            "تعذر إنشاء اتصال Gemini للصوت."
        )

    if types is None:

        raise RuntimeError(
            "تعذر تحميل إعدادات google-genai."
        )

    logger.info(
        "Uploading voice file to Gemini..."
    )

    # Telegram Voice = OGG/Opus
    # نحدد MIME type يدوياً حتى لا تحاول المكتبة
    # اكتشافه من اسم الملف المؤقت.
    audio_file = voice_client.files.upload(
        file=file_path,
        config=types.UploadFileConfig(
            mime_type="audio/ogg",
        ),
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
                "mime_type": "audio/ogg",
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

    return await asyncio.to_thread(
        _transcribe_voice_file,
        file_path,
    )


# ============================================================
# استقبال الصوت
# ============================================================

async def handle_voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    if not await check_access(
        update,
        context,
    ):
        return

    voice = update.message.voice

    if not voice:
        return

    status = await update.message.reply_text(
        "🎙️ استلمت التسجيل الصوتي.\n"
        "⏳ جاري استخراج الكلام إلى نص..."
    )

    temp_path = None

    try:

        telegram_file = await context.bot.get_file(
            voice.file_id
        )

        with tempfile.NamedTemporaryFile(
            suffix=".ogg",
            delete=False,
        ) as temp_file:

            temp_path = temp_file.name

        await telegram_file.download_to_drive(
            custom_path=temp_path
        )

        logger.info(
            "Voice downloaded: %s",
            temp_path,
        )

        text = await transcribe_voice(
            temp_path
        )

        if not text:

            await status.edit_text(
                "❌ ما قدرت أستخرج كلام واضح من التسجيل."
            )

            return

        context.user_data["ai_text"] = text

        if len(text) <= 3900:

            await status.edit_text(
                "🎙️ النص المستخرج:\n\n"
                + text
            )

        else:

            await status.edit_text(
                "🎙️ النص المستخرج:\n\n"
                + text[:3900]
            )

            remaining = text[3900:]

            while remaining:

                chunk = remaining[:3900]
                remaining = remaining[3900:]

                await update.message.reply_text(
                    chunk
                )

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

            error_message = (
                "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n\n"
                "انتظر قليلاً وحاول مرة ثانية."
            )

        elif (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):

            error_message = (
                "⚠️ Gemini مشغول حالياً.\n\n"
                "حاول مرة ثانية 🔄"
            )

        elif (
            "504" in error_text
            or "TIMEOUT" in error_text
            or "DEADLINE_EXCEEDED" in error_text
        ):

            error_message = (
                "⏱️ Gemini تأخر بالاستجابة.\n\n"
                "حاول مرة ثانية 🔄"
            )

        else:

            error_message = (
                "❌ صار خطأ أثناء تحويل الصوت إلى نص.\n\n"
                "حاول تسجيل مقطع أقصر وإرساله مرة ثانية."
            )

        try:

            await status.edit_text(
                error_message
            )

        except Exception:

            await update.message.reply_text(
                error_message
            )

    finally:

        if temp_path:

            try:

                if os.path.exists(temp_path):
                    os.remove(temp_path)

            except Exception:

                logger.warning(
                    "Could not remove temp voice file.",
                    exc_info=True,
                )


# ============================================================
# /start
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not user:
        return

    db.upsert_user(
        user.id,
        user.full_name,
    )

    if not await check_access(
        update,
        context,
    ):
        return

    context.user_data.pop(
        "await",
        None,
    )

    context.user_data.pop(
        "ai_text",
        None,
    )

    await update.message.reply_text(
        "🎓 أهلاً وسهلاً بك\n\n"
        "اختر من القائمة:",
        reply_markup=main_menu(
            user.id
        ),
    )


# ============================================================
# /cancel
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

    context.user_data.pop(
        "quiz",
        None,
    )

    await update.message.reply_text(
        "✅ تم الإلغاء.",
        reply_markup=main_menu(
            update.effective_user.id
        ),
    )


# ============================================================
# التحقق من الاشتراك
# ============================================================

async def verify_subscription(
    q,
    context,
):

    await safe_answer(q)

    uid = q.from_user.id

    ok = await is_subscribed(
        context,
        uid,
        force=True,
    )

    if ok:

        await show(
            q,
            "✅ تم التحقق من اشتراكك.\n\n"
            "اختر من القائمة:",
            main_menu(uid),
        )

    else:

        await show(
            q,
            "❌ بعدك غير مشترك بالقناة.\n\n"
            + SUB_TEXT,
            sub_markup(),
        )


# ============================================================
# القائمة الرئيسية
# ============================================================

async def show_main_menu(
    q,
    context,
):

    await safe_answer(q)

    if not await check_access(
        q,
        context,
    ):
        return

    await show(
        q,
        "🎓 القائمة الرئيسية:",
        main_menu(
            q.from_user.id
        ),
    )


# ============================================================
# تحليل AI
# ============================================================

async def handle_ai(
    q,
    context,
    mode,
):

    await safe_answer(q)

    if not await check_access(
        q,
        context,
    ):
        return

    if mode not in AI_MODES:
        mode = "explain"

    text = (
        context.user_data.get(
            "ai_text",
            "",
        )
        or ""
    ).strip()

    if not text:

        await show(
            q,
            "❌ ما عندي نص للتحليل.\n\n"
            "أرسل نص أو تسجيل صوتي أولاً.",
            main_menu(
                q.from_user.id
            ),
        )

        return

    await show(
        q,
        "⏳ جاري التحليل...\n\n"
        + AI_MODES[mode],
    )

    try:

        result = await ask_ai(
            mode,
            text,
        )

    except Exception:

        logger.exception(
            "AI callback error."
        )

        result = (
            "❌ صار خطأ أثناء التحليل.\n\n"
            "حاول مرة ثانية."
        )

    context.user_data[
        "last_ai_result"
    ] = result

    await send_long_message(
        q.message,
        result,
    )

    await q.message.reply_text(
        "🔄 تريد تحليل النص بطريقة ثانية؟",
        reply_markup=ai_markup(),
    )


# ============================================================
# النصوص
# ============================================================

async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    if not await check_access(
        update,
        context,
    ):
        return

    aw = context.user_data.get(
        "await"
    )

    if aw:

        if aw.get("type") == "report":

            await reports.handle_report_request(
                update,
                context,
            )

            return

        if is_admin(
            update.effective_user.id
        ):

            await admin_msg.handle_admin_message(
                update,
                context,
                aw,
            )

            return

    text = (
        update.message.text or ""
    ).strip()

    if not text:
        return

    context.user_data["ai_text"] = text

    await update.message.reply_text(
        "🤖 استلمت النص.\n\n"
        "اختر نوع التحليل:",
        reply_markup=ai_markup(),
    )


# ============================================================
# المستندات
# ============================================================

async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    if not await check_access(
        update,
        context,
    ):
        return

    aw = context.user_data.get(
        "await"
    )

    if (
        aw
        and is_admin(
            update.effective_user.id
        )
    ):

        await admin_msg.handle_admin_message(
            update,
            context,
            aw,
        )


# ============================================================
# Callback Router
# ============================================================

async def callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    q = update.callback_query

    if not q:
        return

    data = (
        q.data or ""
    ).strip()

    # الاشتراك
    if data == "chk":

        return await verify_subscription(
            q,
            context,
        )

    # AI
    if data.startswith("ai:"):

        mode = data.split(
            ":",
            1,
        )[1]

        return await handle_ai(
            q,
            context,
            mode,
        )

    # التحقق من الاشتراك
    if not await check_access(
        update,
        context,
    ):
        return

    # الرئيسية
    if data == "m":

        return await show_main_menu(
            q,
            context,
        )

    # --------------------------------------------------------
    # الملخصات
    # --------------------------------------------------------

    if data == "sm":

        await safe_answer(q)

        return await show(
            q,
            "📄 اختر المادة:",
            subjects_markup(
                "sm",
                "s_count",
                "m",
            ),
        )

    if data.startswith("sm:"):

        await safe_answer(q)

        try:

            sid = int(
                data.split(
                    ":",
                    1,
                )[1]
            )

        except ValueError:

            return

        from ui import summaries_list

        return await summaries_list(
            q,
            sid,
        )

    if data.startswith("sd:"):

        await safe_answer(q)

        try:

            sum_id = int(
                data.split(
                    ":",
                    1,
                )[1]
            )

        except ValueError:

            return

        return await send_summary(
            q,
            sum_id,
        )

    # --------------------------------------------------------
    # الاختبارات
    # --------------------------------------------------------

    if data == "qm":

        await safe_answer(q)

        return await show(
            q,
            "📝 اختر المادة:",
            subjects_markup(
                "qs",
                "q_count",
                "m",
            ),
        )

    if data.startswith("qs:"):

        await safe_answer(q)

        try:

            sid = int(
                data.split(
                    ":",
                    1,
                )[1]
            )

        except ValueError:

            return

        return await quiz.show_subject_quiz(
            q,
            q.from_user.id,
            sid,
        )

    if data.startswith("startq:"):

        await safe_answer(q)

        try:

            sid = int(
                data.split(
                    ":",
                    1,
                )[1]
            )

        except ValueError:

            return

        return await quiz.start_quiz(
            q,
            context,
            sid,
        )

    if data.startswith("a:"):

        await safe_answer(q)

        return await quiz_flow.answer(
            q,
            context,
            data[2:],
        )

    if data == "n":

        await safe_answer(q)

        return await quiz_flow.next_question(
            q,
            context,
        )

    if data == "rw":

        await safe_answer(q)

        return await quiz_flow.retry_wrong(
            q,
            context,
        )

    # --------------------------------------------------------
    # النتائج
    # --------------------------------------------------------

    if data == "me":

        await safe_answer(q)

        return await quiz.show_stats(
            q,
            q.from_user.id,
        )

    # --------------------------------------------------------
    # الجدول
    # --------------------------------------------------------

    if data == "sc":

        await safe_answer(q)

        return await timetable.open_menu(
            q,
            q.from_user.id,
        )

    if data == "scchg":

        await safe_answer(q)

        return await timetable.change_section(
            q,
        )

    if data.startswith("scset:"):

        await safe_answer(q)

        section = data.split(
            ":",
            1,
        )[1]

        if section not in timetable.SECTIONS:
            return

        return await timetable.set_section(
            q,
            context,
            section,
        )

    if data.startswith("scday:"):

        await safe_answer(q)

        day = data.split(
            ":",
            1,
        )[1]

        if day not in timetable.DAYS_ORDER:
            return

        return await timetable.show_day(
            q,
            q.from_user.id,
            day,
        )

    # --------------------------------------------------------
    # التقارير
    # --------------------------------------------------------

    if data == "rp":

        await safe_answer(q)

        return await reports.show_report_info(
            q,
        )

    if data == "rp1":

        await safe_answer(q)

        return await reports.ask_report(
            q,
            context,
        )

    # --------------------------------------------------------
    # التواصل
    # --------------------------------------------------------

    if data == "ct":

        await safe_answer(q)

        return await reports.show_contact(
            q,
        )

    # --------------------------------------------------------
    # الأدمن
    # --------------------------------------------------------

    if data == "ad":

        await safe_answer(q)

        if not is_admin(
            q.from_user.id
        ):
            return

        return await admin.router(
            q,
            context,
            "ad",
            "",
        )

    if data.startswith("ad:"):

        await safe_answer(q)

        if not is_admin(
            q.from_user.id
        ):
            return

        return await admin.router(
            q,
            context,
            "ad",
            data[3:],
        )

    if data.startswith("ap:"):

        await safe_answer(q)

        if not is_admin(
            q.from_user.id
        ):
            return

        return await admin.router(
            q,
            context,
            "ap",
            data[3:],
        )

    if data.startswith("ak:"):

        await safe_answer(q)

        if not is_admin(
            q.from_user.id
        ):
            return

        return await admin.router(
            q,
            context,
            "ak",
            data[3:],
        )

    if data.startswith("ay:"):

        await safe_answer(q)

        if not is_admin(
            q.from_user.id
        ):
            return

        return await admin.router(
            q,
            context,
            "ay",
            data[3:],
        )

    if data.startswith("ds:"):

        await safe_answer(q)

        if not is_admin(
            q.from_user.id
        ):
            return

        return await admin.router(
            q,
            context,
            "ds",
            data[3:],
        )

    await safe_answer(q)

    logger.warning(
        "Unknown callback: %s",
        data,
    )


# ============================================================
# معالجة الأخطاء
# ============================================================

async def error_handler(
    update,
    context,
):

    logger.exception(
        "Unhandled exception:",
        exc_info=context.error,
    )


# ============================================================
# تشغيل البوت
# ============================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN غير موجود في Railway Variables."
        )

    logger.info(
        "Initializing database..."
    )

    db.init()

    logger.info(
        "Syncing content..."
    )

    try:

        seed.sync()

    except Exception:

        logger.exception(
            "Content sync failed."
        )

    logger.info(
        "Building Telegram application..."
    )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(backup.startup)
        .post_shutdown(backup.shutdown)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            cancel,
        )
    )

    # Buttons
    app.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    # Voice
    app.add_handler(
        MessageHandler(
            filters.VOICE,
            handle_voice,
        )
    )

    # Documents
    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_document,
        )
    )

    # Text
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    # Errors
    app.add_error_handler(
        error_handler
    )

    # التذكير اليومي
    try:

        app.job_queue.run_daily(
            timetable.send_daily_reminders,
            time=dt.time(
                hour=20,
                minute=0,
                tzinfo=ZoneInfo(
                    "Asia/Baghdad"
                ),
            ),
            name="daily_timetable_reminder",
        )

        logger.info(
            "Daily timetable reminder scheduled."
        )

    except Exception:

        logger.exception(
            "Could not schedule daily reminder."
        )

    logger.info(
        "=========================================="
    )

    logger.info(
        "✅ البوت شغال..."
    )

    logger.info(
        "=========================================="
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# ============================================================
# Start
# ============================================================

if __name__ == "__main__":
    main()
