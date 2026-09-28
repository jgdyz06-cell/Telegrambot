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

        # مهم:
        # لا نحدد api_version هنا.
        # نخلي مكتبة Gemini تستخدم الإعداد المناسب.
        voice_client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
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

    "grammar":
        "📌 الإعراب المفصل",

    "rhetoric":
        "🎨 التحليل البلاغي",

    "morphology":
        "⚖️ الصرف والبنية",

    "dictionary":
        "📖 معجم المفردات",

    "explain":
        "📝 شرح النص",

    "prosody":
        "🪶 العروض والقافية",

    "poet":
        "👤 الشاعر والعصر",
}


# ============================================================
# Voice → Text
# ============================================================

def _transcribe_voice_file(file_path):
    """
    تحويل ملف الصوت إلى نص بواسطة Gemini.
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


    # رفع الملف إلى Gemini
    audio_file = voice_client.files.upload(
        file=file_path
    )


    logger.info(
        "Voice file uploaded successfully."
    )


    # إرسال الصوت إلى نموذج النسخ
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

                # اللغة العربية
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


# ============================================================
# تشغيل النسخ خارج Event Loop
# ============================================================

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


    voice = update.message.voice

    if not voice:
        return


    status = await update.message.reply_text(

        "🎙️ استلمت التسجيل الصوتي.\n"
        "⏳ جاري استخراج الكلام إلى نص..."
    )


    temp_path = None


    try:

        # ----------------------------------------------------
        # تحميل الصوت من Telegram
        # ----------------------------------------------------

        telegram_file = await context.bot.get_file(
            voice.file_id
        )


        # ----------------------------------------------------
        # إنشاء ملف مؤقت
        # ----------------------------------------------------

        with tempfile.NamedTemporaryFile(
            suffix=".ogg",
            delete=False,
        ) as temp_file:

            temp_path = temp_file.name


        # ----------------------------------------------------
        # تنزيل الصوت
        # ----------------------------------------------------

        await telegram_file.download_to_drive(
            custom_path=temp_path
        )


        logger.info(
            "Voice downloaded: %s",
            temp_path,
        )


        # ----------------------------------------------------
        # تحويل الصوت إلى نص
        # ----------------------------------------------------

        text = await transcribe_voice(
            temp_path
        )


        if not text:

            await status.edit_text(

                "❌ ما قدرت أستخرج كلام واضح "
                "من التسجيل."
            )

            return


        # ----------------------------------------------------
        # حفظ النص للتحليل
        # ----------------------------------------------------

        context.user_data["ai_text"] = text


        # ----------------------------------------------------
        # عرض النص
        # ----------------------------------------------------

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

                chunk = remaining[:4000]

                remaining = remaining[4000:]


                await update.message.reply_text(
                    chunk
                )


        # ----------------------------------------------------
        # أزرار التحليل
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # أخطاء الحصة
        # ----------------------------------------------------

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):

            message = (

                "⚠️ تم الوصول إلى حد الطلبات "
                "مؤقتاً.\n\n"

                "انتظر قليلاً وحاول مرة ثانية."
            )


        # ----------------------------------------------------
        # Gemini مشغول
        # ----------------------------------------------------

        elif (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):

            message = (

               
