# ai.py
# ============================================================
# Gemini AI - Telegram Bot
# Fast Arabic Analysis
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

# موديل سريع
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
).strip()

# بدائل إذا صار ضغط أو خطأ مؤقت
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
                timeout=90000,

                retry_options=types.HttpRetryOptions(
                    attempts=1
                )
            )
        )

        logger.info(
            "Gemini client initialized successfully."
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
أنت مساعد عربي متخصص في اللغة العربية.

أجب بالعربية فقط.

قواعد مهمة:
- كن دقيقاً.
- لا تخترع معلومات.
- لا تكرر السؤال.
- لا تطل.
- أعطِ النتيجة مباشرة.
- استخدم النص الذي يرسله المستخدم.

إذا كان التحليل غير مؤكد، قل ذلك باختصار.
"""


# ============================================================
# Prompts
# ============================================================

PROMPTS = {

    # --------------------------------------------------------
    # الإعراب
    # --------------------------------------------------------

    "grammar": """
أعرب النص التالي إعراباً مدرسياً واضحاً.

اكتب:

📌 الإعراب:

- الكلمة: إعرابها، علامة الإعراب، السبب.
- الكلمة: إعرابها، علامة الإعراب، السبب.

أعرب الكلمات والجمل المهمة فقط.
لا تشرح شرحاً طويلاً.
ركز على صحة الإعراب.

النص:
""",

    # --------------------------------------------------------
    # البلاغة
    # --------------------------------------------------------

    "rhetoric": """
حلل النص بلاغياً.

اذكر فقط ما هو موجود فعلاً من:
- تشبيه
- استعارة
- كناية
- مجاز
- طباق
- مقابلة
- جناس
- سجع

ثم اذكر أثر الفن البلاغي باختصار.

إذا لم يوجد فن بلاغي واضح، قل:
لا يوجد فن بلاغي واضح في النص.

النص:
""",

    # --------------------------------------------------------
    # الصرف
    # --------------------------------------------------------

    "morphology": """
حلل أهم الكلمات صرفياً.

لكل كلمة مهمة اذكر:

الكلمة:
الجذر:
الوزن:
نوع الكلمة:
مجرد أم مزيد:

لا تشرح كثيراً.

النص:
""",

    # --------------------------------------------------------
    # المعجم
    # --------------------------------------------------------

    "dictionary": """
استخرج أهم المفردات من النص.

لكل كلمة اذكر:

الكلمة:
المعنى في السياق:
الجذر:

اختر الكلمات المهمة فقط.

النص:
""",

    # --------------------------------------------------------
    # شرح النص
    # --------------------------------------------------------

    "explain": """
اشرح النص للطالب باختصار.

اذكر:

1. المعنى العام.
2. شرح الجمل أو الأبيات.
3. الأفكار الرئيسية.
4. الكلمات الصعبة.

اجعل الشرح واضحاً ومختصراً.

النص:
""",

    # --------------------------------------------------------
    # العروض والقافية
    # --------------------------------------------------------

    "prosody": """
حلل النص عروضياً.

أعطني:

1. البحر المحتمل.
2. التفعيلات.
3. التقطيع العروضي.
4. استخدم / للمتحرك و o للساكن.
5. القافية.
6. الروي.
7. هل البيت موزون؟

إذا لم تكن متأكداً من البحر، اذكر ذلك.

لا تشرح طويلاً.

النص:
""",

    # --------------------------------------------------------
    # الشاعر والعصر
    # --------------------------------------------------------

    "poet": """
حلل النص لمعرفة الشاعر والعصر.

اذكر باختصار:

العصر المحتمل:
القرائن:
الخصائص الأسلوبية:
الشاعر المحتمل إن وجدت قرائن قوية:
درجة الثقة:

لا تخترع اسم شاعر.

النص:
"""
}


# ============================================================
# Configuration Check
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
# Error Detection
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
        or "429" in text
        or "RESOURCE_EXHAUSTED" in text
    )


# ============================================================
# Output Limits
# ============================================================

def get_output_tokens(mode):

    if mode == "grammar":
        return 900

    if mode == "prosody":
        return 1200

    if mode == "rhetoric":
        return 900

    if mode == "morphology":
        return 900

    if mode == "dictionary":
        return 800

    if mode == "poet":
        return 700

    return 900


# ============================================================
# Generate With Model
# ============================================================

def _generate_with_model(
    model,
    mode,
    prompt
):

    if client is None:

        raise RuntimeError(
            "Gemini client غير جاهز."
        )

    logger.info(
        "Trying Gemini model: %s | mode: %s",
        model,
        mode
    )

    full_prompt = (
        SYSTEM_PROMPT
        + "\n\n"
        + prompt
    )

    # --------------------------------------------------------
    # مهم جداً:
    # thinking_level = low
    #
    # هذا يقلل وقت التفكير للمهام السريعة
    # --------------------------------------------------------

    interaction = client.interactions.create(

        model=model,

        input=full_prompt,

        generation_config={
            "thinking_level": "low",
            "max_output_tokens": get_output_tokens(mode)
        }
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

    # --------------------------------------------------------
    # نستخدم الموديل السريع أولاً
    # --------------------------------------------------------

    models = FALLBACK_MODELS

    last_error = None

    for model in models:

        try:

            result = _generate_with_model(
                model,
                mode,
                prompt
            )

            return result

        except Exception as error:

            last_error = error

            logger.warning(
                "Gemini model %s failed: %s",
                model,
                error
            )

            # إذا كان خطأ مؤقت نجرب الموديل الثاني
            if is_temporary_error(error):

                continue

            # خطأ غير مؤقت
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
    # التأكد من وجود النص
    # --------------------------------------------------------

    if not text or not text.strip():

        return (
            "❌ ما وصلني نص للتحليل.\n\n"
            "أرسل النص أولاً."
        )

    # --------------------------------------------------------
    # التأكد من Gemini
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
    # التأكد من نوع التحليل
    # --------------------------------------------------------

    if mode not in PROMPTS:

        mode = "explain"

    # --------------------------------------------------------
    # تجهيز الطلب
    # --------------------------------------------------------

    prompt = (
        PROMPTS[mode]
        + "\n\n"
        + text.strip()
    )

    # --------------------------------------------------------
    # تشغيل Gemini خارج Telegram Event Loop
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

        # ----------------------------------------------------
        # Timeout
        # ----------------------------------------------------

        if (
            "504" in error_text
            or "DEADLINE_EXCEEDED" in error_text
            or "DEADLINE EXCEEDED" in error_text
            or "TIMEOUT" in error_text
        ):

            return (
                "⏱️ Gemini تأخر بالاستجابة.\n\n"
                "اضغط الزر مرة ثانية 🔄"
            )

        # ----------------------------------------------------
        # Server Busy
        # ----------------------------------------------------

        if (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):

            return (
                "⚠️ Gemini مشغول حالياً.\n\n"
                "اضغط الزر مرة ثانية 🔄"
            )

        # ----------------------------------------------------
        # Rate Limit
        # ----------------------------------------------------

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):

            return (
                "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n\n"
                "انتظر قليلاً ثم حاول مرة ثانية 🔄"
            )

        # ----------------------------------------------------
        # خطأ عام
        # ----------------------------------------------------

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
