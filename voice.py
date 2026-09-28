# -*- coding: utf-8 -*-
"""معالجة الرسائل الصوتية وتحويلها إلى نص."""

import os
import asyncio
import tempfile
import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

VOICE_MODEL = "gemini-3.5-transcribe"

client = None

if GEMINI_API_KEY:
    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
                api_version="v1",
                timeout=60000,
                retry_options=types.HttpRetryOptions(
                    attempts=1
                ),
            ),
        )

        logger.info(
            "Gemini voice transcription initialized: %s",
            VOICE_MODEL,
        )

    except Exception:
        logger.exception(
            "Failed to initialize Gemini voice client."
        )
        client = None

else:
    logger.warning(
        "GEMINI_API_KEY is not set for voice transcription."
    )


def _transcribe_audio(file_path):
    """تحويل ملف الصوت إلى نص باستخدام Gemini."""

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY غير موجود."
        )

    if client is None:
        raise RuntimeError(
            "تعذر إنشاء اتصال Gemini للصوت."
        )

    logger.info(
        "Uploading voice file to Gemini..."
    )

    audio_file = client.files.upload(
        file=file_path
    )

    if not audio_file:
        raise RuntimeError(
            "فشل رفع الملف الصوتي إلى Gemini."
        )

    logger.info(
        "Voice uploaded: %s",
        getattr(audio_file, "uri", None),
    )

    interaction = client.interactions.create(
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
            "Gemini لم يرجع نصاً."
        )

    return result.strip()


async def transcribe_voice(file_path):
    """تشغيل التحويل بدون تجميد البوت."""

    return await asyncio.to_thread(
        _transcribe_audio,
        file_path,
    )


async def handle_voice(update, context):
    """استلام رسالة صوتية وتحويلها إلى نص."""

    if not update.message or not update.message.voice:
        return

    status = await update.message.reply_text(
        "🎙️ استلمت الصوت.\n"
        "⏳ جاري تحويله إلى نص..."
    )

    temp_path = None

    try:
        voice = update.message.voice

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

        text = await transcribe_voice(
            temp_path
        )

        if not text:
            await status.edit_text(
                "⚠️ ما قدرت أستخرج كلام واضح من الصوت."
            )
            return

        # نخلي النص جاهز للمرحلة القادمة
        context.user_data["ai_text"] = text

        await status.edit_text(
            "🎙️ النص المستخرج:\n\n"
            + text[:3900]
        )

        # إذا النص أطول من رسالة Telegram
        if len(text) > 3900:
            remaining = text[3900:]

            while remaining:
                chunk = remaining[:4000]
                remaining = remaining[4000:]

                await update.message.reply_text(
                    chunk
                )

        logger.info(
            "Voice transcription successful for user %s",
            update.effective_user.id,
        )

    except Exception as error:
        logger.exception(
            "Voice transcription failed."
        )

        error_text = str(error).upper()

        if "429" in error_text:
            message = (
                "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n"
                "حاول بعد قليل."
            )

        elif (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):
            message = (
                "⚠️ Gemini مشغول حالياً.\n"
                "حاول إرسال الصوت مرة ثانية."
            )

        elif (
            "504" in error_text
            or "TIMEOUT" in error_text
            or "DEADLINE" in error_text
        ):
            message = (
                "⏱️ تحويل الصوت تأخر.\n"
                "حاول مرة ثانية بصوت أقصر."
            )

        else:
            message = (
                "❌ صار خطأ أثناء تحويل الصوت إلى نص.\n"
                "راجع Railway Logs."
            )

        await status.edit_text(
            message
        )

    finally:
        if temp_path:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                logger.exception(
                    "Failed to remove temporary voice file."
                )
