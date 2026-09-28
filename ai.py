# ai.py
# ============================================================
# Gemini AI - Telegram Bot
# Interactions API - Fast & Stable
# ============================================================

import os
import asyncio
import logging

from google import genai
from google.genai import types


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Gemini Settings
# ============================================================

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    ""
).strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
).strip()

FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
]


# ============================================================
# Gemini Client
# ============================================================

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
                )
            )
        )

        logger.info(
            "Gemini Interactions client initialized."
        )

    except Exception:

        logger.exception(
            "Failed to initialize Gemini client."
        )

        client = None

else:

    logger.warning(
        "GEMINI_API_KEY is not set."
    )


# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """
أنت مساعد ذكاء اصطناعي عربي متخصص في اللغة العربية.

أجب باللغة العربية الواضحة والمباشرة.

قواعد مهمة:
- لا تخترع معلومات.
- لا تكرر السؤال.
- لا تطيل بدون فائدة.
- إذا كانت النتيجة غير مؤكدة، اذكر ذلك.
- استخدم النص الذي يرسله المستخدم فقط.

في الإعراب:
أعرب الكلمات المهمة بوضوح، واذكر:
الكلمة — إعرابها — علامة الإعراب — السبب.

في البلاغة:
حدد التشبيه والاستعارة والكناية والمجاز والمحسنات إن وجدت.

في الصرف:
اذكر الجذر والوزن ونوع الكلمة والمجرد والمزيد عند الحاجة.

في المعجم:
اذكر معنى الكلمة في السياق والجذر والمعاني المهمة.

في العروض:
حدد البحر المحتمل والتفعيلات والتقطيع والقافية والروي.
استخدم / للمتحرك و o للساكن.
إذا كان الوزن غير مؤكد، وضح ذلك.

في الشاعر:
لا تخترع اسم شاعر.
اذكر العصر والقرائن ودرجة الثقة.

في شرح النص:
اذكر المعنى العام وشرح الأبيات أو الجمل والأفكار الرئيسية.
"""


# ============================================================
# Prompts
# ============================================================

PROMPTS = {

    "grammar": """
أعرب النص التالي.

أريد إعراباً واضحاً ومفيداً للطالب.

رتب النتيجة بهذا الشكل:

📌 الإعراب:
- الكلمة: إعرابها، علامة الإعراب، السبب.
- الكلمة: إعرابها، علامة الإعراب، السبب.

ثم:
📚 ملاحظات نحوية مهمة.

لا تطل في الشرح.
ركز على الإعراب الصحيح.

النص:
""",

    "rhetoric": """
حلل النص التالي بلاغياً.

اذكر فقط الفنون البلاغية الموجودة فعلاً:
- التشبيه
- الاستعارة
- الكناية
- المجاز
- الطباق
- المقابلة
- الجناس
- السجع

ثم اذكر أثرها في المعنى.

النص:
""",

    "morphology": """
حلل النص التالي صرفياً.

للكلمات المهمة اذكر:
- الكلمة
- الجذر
- الوزن
- نوع الكلمة
- مجرد أو مزيد
- أهم الملاحظات الصرفية

النص:
""",

    "dictionary": """
حلل مفردات النص التالي.

لكل كلمة مهمة اذكر:
- الكلمة
- معناها في السياق
- الجذر
- معنى آخر مهم إن وجد

النص:
""",

    "explain": """
اشرح النص التالي للطالب.

أريد:
1. المعنى العام.
2. شرح الجمل أو الأبيات.
3. الأفكار الرئيسية.
4. الكلمات الصعبة.
5. الفكرة الأساسية.

اجعل الشرح واضحاً ومختصراً.

النص:
""",

    "prosody": """
حلل النص التالي عروضياً.

أريد:
1. البحر الشعري المحتمل.
2. التفعيلات.
3. التقطيع العروضي.
4. استخدم / للمتحرك و o للساكن.
5. القافية.
6. الروي.
7. الزحافات أو العلل إن وجدت.
8. هل البيت موزون؟

إذا لم تكن متأكداً من البحر، اذكر ذلك.

النص:
""",

    "poet": """
حلل النص لمعرفة الشاعر والعصر.

اذكر:
1. العصر المحتمل.
2. الخصائص الأسلوبية.
3. القرائن.
4. شاعر محتمل فقط إذا وجدت قرائن قوية.
5. درجة الثقة.

لا تخترع اسم شاعر.

النص:
"""
}


# ============================================================
# Configuration
# ============================================================

def check_gemini_config():

    if not GEMINI_API_KEY:

        return (
            False,
            "GEMINI_API_KEY غير موجود في Railway Variables."
        )

    if client is None:

        return (
            False,
            "تعذر إنشاء اتصال Gemini."
        )

    return (
        True,
        "Gemini جاهز."
    )


# ============================================================
# Temporary Error
# ============================================================

def is_temporary_error(error):

    text = str(error).upper()

    return (
        "503" in text
        or "504" in text
        or "UNAVAILABLE" in text
        or "DEADLINE_EXCEEDED" in text
        or "DEADLINE EXCEEDED" in text
        or "TIMEOUT" in text
    )


# ============================================================
# Generate using Interactions API
# ============================================================

def _generate_with_model(
    model,
    prompt
):

    if client is None:

        raise RuntimeError(
            "Gemini client غير جاهز."
        )

    logger.info(
        "Trying Gemini Interactions model: %s",
        model
    )

    full_prompt = (
        SYSTEM_PROMPT
        + "\n\n"
        + prompt
    )

    interaction = client.interactions.create(

        model=model,

        input=full_prompt
    )

    if not interaction:

        raise RuntimeError(
            "Gemini أعاد استجابة فارغة."
        )

    result = getattr(
        interaction,
        "output_text",
        None
    )

    if not result:

        raise RuntimeError(
            "Gemini لم يرجع نصاً."
        )

    return result.strip()


# ============================================================
# Generate
# ============================================================

def _generate(
    mode,
    prompt
):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "مفتاح Gemini غير موجود."
        )

    if client is None:

        raise RuntimeError(
            "تعذر الاتصال بخدمة Gemini."
        )

    # الإعراب يحتاج جواباً قصيراً
    # لذلك نستخدم الموديل السريع أولاً دائماً
    models = FALLBACK_MODELS

    last_error = None

    for model in models:

        try:

            return _generate_with_model(
                model,
                prompt
            )

        except Exception as error:

            last_error = error

            if is_temporary_error(error):

                logger.warning(
                    "Gemini %s temporary error: %s",
                    model,
                    error
                )

                continue

            logger.exception(
                "Gemini request failed."
            )

            raise RuntimeError(
                f"Gemini error: {error}"
            ) from error

    raise RuntimeError(
        "Gemini لم يكمل الطلب ضمن المهلة."
    ) from last_error


# ============================================================
# Public AI Function
# ============================================================

async def ask_ai(
    mode,
    text
):

    # --------------------------------------------------------
    # فحص النص
    # --------------------------------------------------------

    if not text or not text.strip():

        return (
            "❌ ما وصلني نص للتحليل.\n\n"
            "أرسل النص أولاً."
        )

    # --------------------------------------------------------
    # فحص Gemini
    # --------------------------------------------------------

    ok, message = check_gemini_config()

    if not ok:

        logger.error(
            "Gemini configuration error: %s",
            message
        )

        return (
            "❌ تعذر تشغيل الذكاء الاصطناعي حالياً.\n\n"
            + message
        )

    # --------------------------------------------------------
    # نوع التحليل
    # --------------------------------------------------------

    if mode not in PROMPTS:

        mode = "explain"

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = (
        PROMPTS[mode]
        + "\n\n"
        + text.strip()
    )

    # --------------------------------------------------------
    # تنفيذ خارج Telegram event loop
    # --------------------------------------------------------

    try:

        result = await asyncio.to_thread(
            _generate,
            mode,
            prompt
        )

        if not result:

            return (
                "❌ Gemini لم يرجع نتيجة."
            )

        return result

    except Exception as error:

        logger.exception(
            "AI request failed."
        )

        error_text = str(error).upper()

        if (
            "504" in error_text
            or "DEADLINE_EXCEEDED" in error_text
            or "TIMEOUT" in error_text
        ):

            return (
                "⏱️ Gemini تأخر بالاستجابة.\n\n"
                "حاول مرة ثانية 🔄"
            )

        if (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):

            return (
                "⚠️ Gemini مشغول حالياً.\n\n"
                "حاول مرة ثانية 🔄"
            )

        return (
            "❌ حدث خطأ أثناء تحليل النص.\n\n"
            f"التفاصيل: {error}"
        )


# ============================================================
# Test
# ============================================================

async def test_ai():

    return await ask_ai(
        "grammar",
        "العلم نور."
    )
