# -*- coding: utf-8 -*-

"""المعالج الرئيسي للبوت."""

import os
import asyncio
import tempfile
import datetime as dt
import threading
import json
import re
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

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
import webapp

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
# Gemini Voice + Image + Grammar Challenge
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


# ------------------------------------------------------------
# Voice
# ------------------------------------------------------------

VOICE_MODEL = os.getenv(
    "VOICE_MODEL",
    "gemini-3.5-transcribe",
).strip()


# ------------------------------------------------------------
# Image OCR
# ------------------------------------------------------------

IMAGE_MODEL = os.getenv(
    "IMAGE_MODEL",
    "gemini-3.1-flash-lite",
).strip()


# ------------------------------------------------------------
# Grammar Challenge
# ------------------------------------------------------------

CHALLENGE_MODEL = os.getenv(
    "CHALLENGE_MODEL",
    "gemini-3.1-flash-lite",
).strip()


voice_client = None
image_client = None


if GEMINI_API_KEY and genai is not None:

    # --------------------------------------------------------
    # Voice client
    # --------------------------------------------------------

    try:

        if types is not None:

            voice_client = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options=types.HttpOptions(
                    api_version="v1beta",
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

    # --------------------------------------------------------
    # Image client
    # --------------------------------------------------------

    try:

        if types is not None:

            image_client = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options=types.HttpOptions(
                    api_version="v1",
                    timeout=60000,
                ),
            )

        else:

            image_client = genai.Client(
                api_key=GEMINI_API_KEY,
            )

        logger.info(
            "Gemini Image client initialized: %s",
            IMAGE_MODEL,
        )

    except Exception:

        logger.exception(
            "Failed to initialize Gemini Image client."
        )

        image_client = None

else:

    logger.warning(
        "Gemini Voice/Image clients not initialized."
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
# Grammar Challenge Settings
# ============================================================

CHALLENGE_TOTAL = 10


# ============================================================
# Helpers
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


# ============================================================
# Access / Subscription
# ============================================================

async def check_access(
    update,
    context,
):

    user = update.effective_user

    if not user:
        return False

    try:

        db.upsert_user(
            user.id,
            user.full_name,
        )

    except Exception:

        logger.exception(
            "Could not update user."
        )

    if is_admin(user.id):
        return True

    try:

        ok = await is_subscribed(
            context,
            user.id,
        )

    except Exception:

        logger.exception(
            "Subscription check failed."
        )

        ok = False

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
# Voice Transcription
# ============================================================

def _transcribe_voice_file(
    file_path
):

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

    audio_file = voice_client.files.upload(

        file=file_path,

        config=types.UploadFileConfig(
            mime_type="audio/ogg",
        ),

    )

    logger.info(
        "Voice file uploaded successfully."
    )

    interaction = (
        voice_client.interactions.create(

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


async def transcribe_voice(
    file_path
):

    return await asyncio.to_thread(
        _transcribe_voice_file,
        file_path,
    )


# ============================================================
# Voice Handler
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

    if not await check_access(
        update,
        context,
    ):
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

        elif (
            "NOT_FOUND" in error_text
            or (
                "MODEL" in error_text
                and "NOT FOUND" in error_text
            )
        ):

            error_message = (

                "❌ نموذج تحويل الصوت غير متاح حالياً.\n\n"
                "تحقق من إعدادات Gemini."

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

            try:

                await update.message.reply_text(
                    error_message
                )

            except Exception:
                pass

    finally:

        if temp_path:

            try:

                if os.path.exists(temp_path):
                    os.remove(temp_path)

            except Exception:

                logger.warning(
                    "Could not remove temporary voice file.",
                    exc_info=True,
                )


# ============================================================
# Image OCR
# ============================================================

def _extract_text_from_image_file(
    file_path,
    mime_type,
):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY غير موجود."
        )

    if image_client is None:

        raise RuntimeError(
            "تعذر إنشاء اتصال Gemini للصور."
        )

    prompt = """
استخرج النص الموجود داخل الصورة فقط.

مهم جداً:
- الصورة قد تحتوي على نص عربي أو إنكليزي أو الاثنين معاً.
- حافظ على الكلمات كما تظهر في الصورة قدر الإمكان.
- لا تشرح الصورة.
- لا تلخص.
- لا تضف أي كلام من عندك.
- لا تضع مقدمة مثل "النص هو".
- إذا كان هناك أكثر من سطر، حافظ على ترتيب الأسطر.
- إذا كانت هناك أسئلة أو أبيات أو جمل، اكتبها كما تظهر.
- إذا كانت هناك كلمات غير واضحة، حاول قراءتها من السياق، وإذا تعذر ذلك اتركها كما تبدو بدلاً من اختراع كلمة.
- أعد النص المستخرج فقط.
"""

    logger.info(
        "Uploading image to Gemini: %s",
        file_path,
    )

    uploaded_file = image_client.files.upload(
        file=file_path,
    )

    if not uploaded_file:

        raise RuntimeError(
            "فشل رفع الصورة إلى Gemini."
        )

    file_uri = getattr(
        uploaded_file,
        "uri",
        None,
    )

    uploaded_mime = getattr(
        uploaded_file,
        "mime_type",
        None,
    )

    if not file_uri:

        raise RuntimeError(
            "Gemini لم يرجع رابط الصورة."
        )

    if not uploaded_mime:
        uploaded_mime = mime_type or "image/jpeg"

    logger.info(
        "Image uploaded successfully."
    )

    interaction = image_client.interactions.create(

        model=IMAGE_MODEL,

        input=[

            {
                "type": "text",
                "text": prompt,
            },

            {
                "type": "image",
                "uri": file_uri,
                "mime_type": uploaded_mime,
            },

        ],

        generation_config={
            "thinking_level": "minimal",
            "max_output_tokens": 2000,
        },

    )

    if not interaction:

        raise RuntimeError(
            "Gemini أعاد استجابة فارغة للصورة."
        )

    result = getattr(
        interaction,
        "output_text",
        None,
    )

    if not result:

        raise RuntimeError(
            "Gemini لم يرجع نصاً من الصورة."
        )

    return result.strip()


async def extract_text_from_image(
    file_path,
    mime_type,
):

    return await asyncio.to_thread(
        _extract_text_from_image_file,
        file_path,
        mime_type,
    )


# ============================================================
# Image Handler
# ============================================================

async def handle_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    message = update.message

    photo = message.photo

    document = message.document

    if not photo and not document:
        return

    if not await check_access(
        update,
        context,
    ):
        return

    status = await message.reply_text(

        "📷 استلمت الصورة.\n"
        "⏳ جاري قراءة النص منها..."

    )

    temp_path = None

    try:

        # ----------------------------------------------------
        # Telegram Photo
        # ----------------------------------------------------

        if photo:

            telegram_file = await context.bot.get_file(
                photo[-1].file_id
            )

            suffix = ".jpg"
            mime_type = "image/jpeg"

        # ----------------------------------------------------
        # Image sent as Document
        # ----------------------------------------------------

        else:

            telegram_file = await context.bot.get_file(
                document.file_id
            )

            mime_type = (
                document.mime_type
                or "image/jpeg"
            )

            if mime_type == "image/png":
                suffix = ".png"

            elif mime_type == "image/webp":
                suffix = ".webp"

            elif mime_type == "image/gif":
                suffix = ".gif"

            else:
                suffix = ".jpg"

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False,
        ) as temp_file:

            temp_path = temp_file.name

        await telegram_file.download_to_drive(
            custom_path=temp_path
        )

        logger.info(
            "Image downloaded: %s",
            temp_path,
        )

        # ----------------------------------------------------
        # OCR
        # ----------------------------------------------------

        text = await extract_text_from_image(
            temp_path,
            mime_type,
        )

        if not text:

            await status.edit_text(

                "❌ ما قدرت أقرأ نص واضح من الصورة.\n\n"
                "حاول إرسال صورة أوضح."

            )

            return

        # ----------------------------------------------------
        # Save extracted text for AI
        # ----------------------------------------------------

        context.user_data[
            "ai_text"
        ] = text

        # ----------------------------------------------------
        # Show extracted text
        # ----------------------------------------------------

        if len(text) <= 3900:

            await status.edit_text(

                "📷 النص المستخرج من الصورة:\n\n"
                + text

            )

        else:

            await status.edit_text(

                "📷 النص المستخرج من الصورة:\n\n"
                + text[:3900]

            )

            remaining = text[3900:]

            while remaining:

                chunk = remaining[:3900]
                remaining = remaining[3900:]

                await message.reply_text(
                    chunk
                )

        # ----------------------------------------------------
        # AI choices
        # ----------------------------------------------------

        await message.reply_text(

            "🤖 شنو تريد أسوي للنص المستخرج؟\n\n"
            "اختر نوع التحليل:",

            reply_markup=ai_markup(),

        )

    except Exception as error:

        logger.exception(
            "Image OCR error."
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

                "⏱️ Gemini تأخر بقراءة الصورة.\n\n"
                "حاول إرسال الصورة مرة ثانية 🔄"

            )

        elif (
            "NOT_FOUND" in error_text
            or (
                "MODEL" in error_text
                and "NOT FOUND" in error_text
            )
        ):

            error_message = (

                "❌ نموذج قراءة الصور غير متاح حالياً.\n\n"
                "تحقق من إعدادات Gemini."

            )

        else:

            error_message = (

                "❌ صار خطأ أثناء قراءة الصورة.\n\n"
                "تأكد أن الصورة واضحة وتحتوي على نص، "
                "ثم حاول مرة ثانية."

            )

        try:

            await status.edit_text(
                error_message
            )

        except Exception:

            try:

                await message.reply_text(
                    error_message
                )

            except Exception:
                pass

    finally:

        if temp_path:

            try:

                if os.path.exists(temp_path):
                    os.remove(temp_path)

            except Exception:

                logger.warning(
                    "Could not remove temporary image file.",
                    exc_info=True,
                )


# ============================================================
# Grammar Challenge - Gemini
# ============================================================

def _clean_json_response(text):

    if not text:
        return ""

    text = text.strip()

    # إزالة ```json و ```
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    text = text.strip()

    # إذا Gemini أضاف كلام قبل/بعد JSON
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:

        text = text[start:end + 1]

    return text.strip()


def _generate_grammar_question():

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY غير موجود."
        )

    if image_client is None:

        raise RuntimeError(
            "تعذر الاتصال بخدمة Gemini."
        )

    prompt = """
أنت مولّد أسئلة لتحدي قواعد اللغة العربية للطلاب.

أنشئ سؤال قواعد عربية واحد فقط.

الشروط:
- السؤال يجب أن يكون واضحاً ومناسباً للطالب.
- استخدم قواعد عربية مدرسية صحيحة.
- اجعل السؤال متوسط الصعوبة.
- يجب أن يحتوي على 4 خيارات فقط.
- خيار واحد فقط صحيح.
- لا تجعل أكثر من خيار صحيحاً.
- لا تستخدم معلومات غامضة أو خلافية.
- بعد السؤال، اكتب شرحاً قصيراً جداً لسبب صحة الإجابة.

أمثلة لأنواع الأسئلة:
- تحديد المفعول به.
- تحديد الفاعل.
- تحديد المبتدأ والخبر.
- علامة الإعراب.
- نوع الجملة.
- كان وأخواتها.
- إن وأخواتها.
- النعت.
- الحال.
- التمييز.
- المفعول المطلق.
- المفعول لأجله.
- جمع المذكر السالم.
- المثنى.
- الأسماء الخمسة.

أعد النتيجة بصيغة JSON فقط، بدون أي كلام خارج JSON.

الشكل المطلوب بالضبط:

{
  "question": "السؤال هنا",
  "options": [
    "الخيار الأول",
    "الخيار الثاني",
    "الخيار الثالث",
    "الخيار الرابع"
  ],
  "correct": 0,
  "explanation": "شرح مختصر."
}

مهم:
- correct يجب أن يكون رقماً من 0 إلى 3.
- options يجب أن تحتوي على 4 عناصر بالضبط.
- لا تستخدم Markdown.
- لا تضع ```json.
"""

    logger.info(
        "Generating grammar challenge question..."
    )

    interaction = image_client.interactions.create(

        model=CHALLENGE_MODEL,

        input=prompt,

        generation_config={
            "thinking_level": "minimal",
            "max_output_tokens": 700,
        },

    )

    if not interaction:

        raise RuntimeError(
            "Gemini أعاد استجابة فارغة للسؤال."
        )

    result = getattr(
        interaction,
        "output_text",
        None,
    )

    if not result:

        raise RuntimeError(
            "Gemini لم يرجع سؤالاً."
        )

    result = _clean_json_response(
        result
    )

    try:

        data = json.loads(
            result
        )

    except Exception as error:

        logger.error(
            "Invalid challenge JSON: %s",
            result,
        )

        raise RuntimeError(
            "Gemini أعاد صيغة سؤال غير صالحة."
        ) from error

    question = str(
        data.get(
            "question",
            "",
        )
    ).strip()

    options = data.get(
        "options",
        [],
    )

    correct = data.get(
        "correct",
        -1,
    )

    explanation = str(
        data.get(
            "explanation",
            "",
        )
    ).strip()

    if not question:

        raise RuntimeError(
            "السؤال فارغ."
        )

    if not isinstance(
        options,
        list,
    ):

        raise RuntimeError(
            "خيارات السؤال غير صالحة."
        )

    options = [
        str(option).strip()
        for option in options
        if str(option).strip()
    ]

    if len(options) != 4:

        raise RuntimeError(
            "يجب أن يحتوي السؤال على أربعة خيارات."
        )

    try:

        correct = int(
            correct
        )

    except Exception:

        correct = -1

    if correct not in range(4):

        raise RuntimeError(
            "الإجابة الصحيحة غير صالحة."
        )

    if not explanation:

        explanation = (
            "هذه هي الإجابة الصحيحة حسب القاعدة النحوية."
        )

    return {
        "question": question,
        "options": options,
        "correct": correct,
        "explanation": explanation,
    }


async def generate_grammar_question():

    return await asyncio.to_thread(
        _generate_grammar_question
    )


# ============================================================
# Grammar Challenge - Keyboard
# ============================================================

def grammar_challenge_markup():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "1️⃣",
                    callback_data="aich:0",
                ),
                InlineKeyboardButton(
                    "2️⃣",
                    callback_data="aich:1",
                ),
            ],
            [
                InlineKeyboardButton(
                    "3️⃣",
                    callback_data="aich:2",
                ),
                InlineKeyboardButton(
                    "4️⃣",
                    callback_data="aich:3",
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ إلغاء التحدي",
                    callback_data="aich:cancel",
                ),
            ],
        ]
    )


# ============================================================
# Send Grammar Challenge Question
# ============================================================

async def send_grammar_challenge_question(
    q,
    context,
    first=False,
):

    challenge = context.user_data.get(
        "ai_challenge"
    )

    if not challenge:

        return

    number = challenge.get(
        "number",
        1,
    )

    if first:

        await q.edit_message_text(
            "🧠 **تحدي قواعد اللغة العربية**\n\n"
            "⏳ جاري تجهيز السؤال الأول...",
            parse_mode="Markdown",
        )

    else:

        try:

            await q.edit_message_text(
                "🧠 **تحدي قواعد اللغة العربية**\n\n"
                f"📊 السؤال {number} من {CHALLENGE_TOTAL}\n\n"
                "⏳ جاري تجهيز السؤال...",
                parse_mode="Markdown",
            )

        except Exception:

            pass

    try:

        question_data = (
            await generate_grammar_question()
        )

    except Exception as error:

        logger.exception(
            "Grammar challenge question generation failed."
        )

        error_text = str(error).upper()

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):

            message = (
                "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n\n"
                "حاول مرة ثانية بعد قليل."
            )

        elif (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):

            message = (
                "⚠️ Gemini مشغول حالياً.\n\n"
                "حاول مرة ثانية 🔄"
            )

        elif (
            "504" in error_text
            or "TIMEOUT" in error_text
            or "DEADLINE_EXCEEDED" in error_text
        ):

            message = (
                "⏱️ Gemini تأخر بتجهيز السؤال.\n\n"
                "حاول مرة ثانية 🔄"
            )

        else:

            message = (
                "❌ ما قدرت أجهز سؤال التحدي حالياً.\n\n"
                "حاول مرة ثانية 🔄"
            )

        try:

            await q.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔄 إعادة المحاولة",
                                callback_data="aichallenge",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🏠 القائمة الرئيسية",
                                callback_data="m",
                            )
                        ],
                    ]
                ),
            )

        except Exception:

            pass

        return

    challenge["question"] = (
        question_data["question"]
    )

    challenge["options"] = (
        question_data["options"]
    )

    challenge["correct"] = (
        question_data["correct"]
    )

    challenge["explanation"] = (
        question_data["explanation"]
    )

    context.user_data[
        "ai_challenge"
    ] = challenge

    text = (

        "🧠 **تحدي قواعد اللغة العربية**\n\n"

        f"📊 السؤال {number} من {CHALLENGE_TOTAL}\n"

        f"✅ الصحيح: {challenge.get('correct_count', 0)}\n\n"

        f"❓ {question_data['question']}\n\n"

        f"1️⃣ {question_data['options'][0]}\n"
        f"2️⃣ {question_data['options'][1]}\n"
        f"3️⃣ {question_data['options'][2]}\n"
        f"4️⃣ {question_data['options'][3]}\n\n"

        "👇 اختر الإجابة الصحيحة:"

    )

    try:

        await q.edit_message_text(

            text,

            parse_mode="Markdown",

            reply_markup=grammar_challenge_markup(),

        )

    except Exception:

        logger.exception(
            "Could not display grammar challenge question."
        )


# ============================================================
# Start Grammar Challenge
# ============================================================

async def start_grammar_challenge(
    update,
    context,
):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    # إعادة بدء التحدي من الصفر
    context.user_data[
        "ai_challenge"
    ] = {

        "number": 1,

        "correct_count": 0,

        "wrong_count": 0,

        "question": "",

        "options": [],

        "correct": -1,

        "explanation": "",

    }

    await send_grammar_challenge_question(
        q,
        context,
        first=True,
    )


# ============================================================
# Grammar Challenge Answer
# ============================================================

async def handle_grammar_challenge_answer(
    update,
    context,
    answer_index,
):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    challenge = context.user_data.get(
        "ai_challenge"
    )

    if not challenge:

        await q.edit_message_text(

            "❌ لا يوجد تحدي نشط حالياً.\n\n"
            "اضغط على زر تحدي قواعد اللغة العربية من القائمة.",

            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🧠 بدء التحدي",
                            callback_data="aichallenge",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 القائمة الرئيسية",
                            callback_data="m",
                        )
                    ],
                ]
            ),

        )

        return

    try:

        selected = int(
            answer_index
        )

    except Exception:

        return

    if selected not in range(4):

        return

    correct = challenge.get(
        "correct",
        -1,
    )

    options = challenge.get(
        "options",
        [],
    )

    explanation = challenge.get(
        "explanation",
        "",
    )

    number = challenge.get(
        "number",
        1,
    )

    if not isinstance(
        options,
        list,
    ) or len(options) != 4:

        await q.edit_message_text(
            "❌ حدث خطأ في بيانات السؤال.\n\n"
            "سننهي التحدي الحالي.",
        )

        context.user_data.pop(
            "ai_challenge",
            None,
        )

        return

    selected_text = options[selected]

    correct_text = options[correct]

    if selected == correct:

        challenge[
            "correct_count"
        ] = challenge.get(
            "correct_count",
            0,
        ) + 1

        result_text = (

            "✅ **إجابة صحيحة!**\n\n"

            f"إجابتك: {selected_text}\n\n"

            f"📚 **الشرح:**\n"
            f"{explanation}"

        )

    else:

        challenge[
            "wrong_count"
        ] = challenge.get(
            "wrong_count",
            0,
        ) + 1

        result_text = (

            "❌ **إجابة غير صحيحة**\n\n"

            f"إجابتك: {selected_text}\n\n"

            f"✅ الإجابة الصحيحة: {correct_text}\n\n"

            f"📚 **الشرح:**\n"
            f"{explanation}"

        )

    # --------------------------------------------------------
    # إذا انتهت الأسئلة
    # --------------------------------------------------------

    if number >= CHALLENGE_TOTAL:

        correct_count = challenge.get(
            "correct_count",
            0,
        )

        wrong_count = challenge.get(
            "wrong_count",
            0,
        )

        percentage = round(
            (
                correct_count
                / CHALLENGE_TOTAL
            ) * 100
        )

        final_text = (

            result_text

            + "\n\n"
            + "━━━━━━━━━━━━━━\n\n"

            + "🏁 **انتهى التحدي!**\n\n"

            + f"📊 النتيجة: "
            + f"{correct_count}/{CHALLENGE_TOTAL}\n"

            + f"❌ الأخطاء: "
            + f"{wrong_count}\n"

            + f"🎯 النسبة: "
            + f"{percentage}%\n\n"

            + "👏 أحسنت! استمر بالتدريب."

        )

        await q.edit_message_text(

            final_text,

            parse_mode="Markdown",

            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 تحدي جديد",
                            callback_data="aichallenge",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 القائمة الرئيسية",
                            callback_data="m",
                        )
                    ],
                ]
            ),

        )

        context.user_data.pop(
            "ai_challenge",
            None,
        )

        return

    # --------------------------------------------------------
    # السؤال التالي
    # --------------------------------------------------------

    challenge["number"] = (
        number + 1
    )

    challenge["question"] = ""
    challenge["options"] = []
    challenge["correct"] = -1
    challenge["explanation"] = ""

    context.user_data[
        "ai_challenge"
    ] = challenge

    # عرض نتيجة السؤال أولاً
    await q.edit_message_text(

        result_text
        + "\n\n"
        + f"📊 النتيجة الحالية: "
        + f"{challenge.get('correct_count', 0)}/"
        + f"{number}\n\n"
        + "⏳ جاري تجهيز السؤال التالي...",

        parse_mode="Markdown",

    )

    # تجهيز السؤال الجديد
    try:

        question_data = (
            await generate_grammar_question()
        )

    except Exception as error:

        logger.exception(
            "Next grammar challenge question failed."
        )

        error_text = str(error).upper()

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):

            message = (
                result_text
                + "\n\n"
                + "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n\n"
                "يمكنك الضغط على إعادة المحاولة."
            )

        elif (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):

            message = (
                result_text
                + "\n\n"
                + "⚠️ Gemini مشغول حالياً.\n\n"
                "حاول مرة ثانية 🔄"
            )

        else:

            message = (
                result_text
                + "\n\n"
                + "❌ ما قدرت أجهز السؤال التالي.\n\n"
                "حاول مرة ثانية 🔄"
            )

        await q.edit_message_text(

            message,

            parse_mode="Markdown",

            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 إعادة المحاولة",
                            callback_data="aichallenge",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 القائمة الرئيسية",
                            callback_data="m",
                        )
                    ],
                ]
            ),

        )

        return

    challenge["question"] = (
        question_data["question"]
    )

    challenge["options"] = (
        question_data["options"]
    )

    challenge["correct"] = (
        question_data["correct"]
    )

    challenge["explanation"] = (
        question_data["explanation"]
    )

    context.user_data[
        "ai_challenge"
    ] = challenge

    text = (

        "🧠 **تحدي قواعد اللغة العربية**\n\n"

        f"📊 السؤال {challenge['number']} "
        f"من {CHALLENGE_TOTAL}\n"

        f"✅ الصحيح حتى الآن: "
        f"{challenge.get('correct_count', 0)}\n\n"

        f"❓ {question_data['question']}\n\n"

        f"1️⃣ {question_data['options'][0]}\n"
        f"2️⃣ {question_data['options'][1]}\n"
        f"3️⃣ {question_data['options'][2]}\n"
        f"4️⃣ {question_data['options'][3]}\n\n"

        "👇 اختر الإجابة الصحيحة:"

    )

    await q.edit_message_text(

        text,

        parse_mode="Markdown",

        reply_markup=grammar_challenge_markup(),

    )


# ============================================================
# Cancel Grammar Challenge
# ============================================================

async def cancel_grammar_challenge(
    update,
    context,
):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    context.user_data.pop(
        "ai_challenge",
        None,
    )

    if not await check_access(
        update,
        context,
    ):
        return

    await q.edit_message_text(

        "❌ تم إلغاء تحدي قواعد اللغة العربية.\n\n"
        "يمكنك بدء تحدي جديد من القائمة الرئيسية.",

        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🧠 بدء التحدي",
                        callback_data="aichallenge",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data="m",
                    )
                ],
            ]
        ),

    )


# ============================================================
# Start
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not user:
        return

    try:

        db.upsert_user(
            user.id,
            user.full_name,
        )

    except Exception:

        logger.exception(
            "Could not save user."
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

    context.user_data.pop(
        "ai_challenge",
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

    context.user_data.pop(
        "quiz",
        None,
    )

    context.user_data.pop(
        "ai_challenge",
        None,
    )

    await update.message.reply_text(

        "✅ تم الإلغاء.",

        reply_markup=main_menu(
            update.effective_user.id
        ),

    )


# ============================================================
# Subscription Verification
# ============================================================

async def verify_subscription(
    q,
    context,
):

    await safe_answer(q)

    uid = q.from_user.id

    try:

        ok = await is_subscribed(
            context,
            uid,
            force=True,
        )

    except TypeError:

        ok = await is_subscribed(
            context,
            uid,
        )

    except Exception:

        logger.exception(
            "Forced subscription check failed."
        )

        ok = False

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
# Main Menu
# ============================================================

async def show_main_menu(
    update,
    context,
):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
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
# AI Handler
# ============================================================

async def handle_ai(
    update,
    context,
    mode,
):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
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
            "أرسل نص أو صورة أو تسجيل صوتي أولاً.",

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
# Text Handler
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

    context.user_data[
        "ai_text"
    ] = text

    await update.message.reply_text(

        "🤖 استلمت النص.\n\n"
        "اختر نوع التحليل:",

        reply_markup=ai_markup(),

    )


# ============================================================
# Document Handler
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

    # --------------------------------------------------------
    # الصور المرسلة كملف
    # --------------------------------------------------------

    document = update.message.document

    if document:

        mime_type = (
            document.mime_type or ""
        ).lower()

        if mime_type.startswith(
            "image/"
        ):

            return await handle_image(
                update,
                context,
            )

    # --------------------------------------------------------
    # مستندات الأدمن الحالية
    # --------------------------------------------------------

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

    # ========================================================
    # Grammar AI Challenge
    # ========================================================

    if data == "aichallenge":

        return await start_grammar_challenge(
            update,
            context,
        )

    if data.startswith("aich:"):

        value = data.split(
            ":",
            1
        )[1]

        if value == "cancel":

            return await cancel_grammar_challenge(
                update,
                context,
            )

        return await handle_grammar_challenge_answer(
            update,
            context,
            value,
        )

    # ========================================================
    # Subscription
    # ========================================================

    if data == "chk":

        return await verify_subscription(
            q,
            context,
        )

    # ========================================================
    # AI
    # ========================================================

    if data.startswith("ai:"):

        mode = data.split(
            ":",
            1
        )[1]

        return await handle_ai(
            update,
            context,
            mode,
        )

    # ========================================================
    # Access
    # ========================================================

    if not await check_access(
        update,
        context,
    ):
        return

    # ========================================================
    # Main menu
    # ========================================================

    if data == "m":

        return await show_main_menu(
            update,
            context,
        )

    # ========================================================
    # Summaries
    # ========================================================

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
                    1
                )[1]
            )

        except ValueError:

            return

        try:

            from ui import summaries_list

            return await summaries_list(
                q,
                sid,
            )

        except Exception:

            logger.exception(
                "summaries_list failed."
            )

            return

    if data.startswith("sd:"):

        await safe_answer(q)

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
            sum_id,
        )

    # ========================================================
    # Quizzes
    # ========================================================

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
                    1
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
                    1
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

    if data == "me":

        await safe_answer(q)

        return await quiz.show_stats(
            q,
            q.from_user.id,
        )

    # ========================================================
    # Timetable
    # ========================================================

    if data == "sc":

        await safe_answer(q)

        return await timetable.open_menu(
            q,
            q.from_user.id,
        )

    if data == "scchg":

        await safe_answer(q)

        return await timetable.change_section(
            q
        )

    if data.startswith("scset:"):

        await safe_answer(q)

        section = data.split(
            ":",
            1
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
            1
        )[1]

        if day not in timetable.DAYS_ORDER:
            return

        return await timetable.show_day(
            q,
            q.from_user.id,
            day,
        )

    # ========================================================
    # Reports
    # ========================================================

    if data == "rp":

        await safe_answer(q)

        return await reports.show_report_info(
            q
        )

    if data == "rp1":

        await safe_answer(q)

        return await reports.ask_report(
            q,
            context,
        )

    if data == "ct":

        await safe_answer(q)

        return await reports.show_contact(
            q
        )

    # ========================================================
    # Admin
    # ========================================================

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

    # ========================================================
    # Unknown callback
    # ========================================================

    await safe_answer(q)

    logger.warning(
        "Unknown callback: %s",
        data,
    )


# ============================================================
# Error Handler
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
# Main
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

    # --------------------------------------------------------
    # Telegram handlers
    # --------------------------------------------------------

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

    app.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    # --------------------------------------------------------
    # Voice
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.VOICE,
            handle_voice,
        )
    )

    # --------------------------------------------------------
    # Images
    #
    # يجب وضع الصور قبل Document.ALL حتى يتم التعامل
    # مع الصور المرسلة كملف أيضاً.
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_image,
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Document.IMAGE,
            handle_image,
        )
    )

    # --------------------------------------------------------
    # Other documents
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_document,
        )
    )

    # --------------------------------------------------------
    # Text
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    app.add_error_handler(
        error_handler
    )

    # --------------------------------------------------------
    # Daily timetable reminder
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Web App server
    # --------------------------------------------------------

    try:

        web_thread = threading.Thread(

            target=webapp.start_web_server,

            daemon=True,

            name="webapp-server",

        )

        web_thread.start()

        logger.info(
            "✅ Web App server started."
        )

    except Exception:

        logger.exception(
            "❌ Could not start Web App server."
        )

    # --------------------------------------------------------
    # Start Telegram bot
    # --------------------------------------------------------

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
# Entry Point
# ============================================================

if __name__ == "__main__":

    main()
