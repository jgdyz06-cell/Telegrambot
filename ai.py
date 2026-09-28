# ai.py
# ============================================================
# Gemini AI - Telegram Bot
# Stable Timeout + Fallback Version
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

                # نرفع المهلة من 30 إلى 60 ثانية
                timeout=60000,

                # لا نريد SDK يعيد الطلب عدة مرات
                # حتى لا يتأخر البوت
                retry_options=types.HttpRetryOptions(
                    attempts=1
                ),

                # استخدام API المستقر
                api_version="v1"
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
أنت مساعد ذكاء اصطناعي عربي متخصص في اللغة العربية.

أجب باللغة العربية الواضحة والبسيطة.

كن دقيقاً ولا تخترع معلومات.

إذا كانت المعلومة غير مؤكدة، اذكر أنها غير مؤكدة.

عند تحليل النصوص:
- اعتمد على النص المرسل.
- نظم الإجابة بعناوين ونقاط.
- لا تكرر السؤال.
- أعط النتيجة مباشرة.

في الإعراب:
اذكر إعراب الكلمات المهمة وعلامة الإعراب وسببها.

في البلاغة:
حدد التشبيه والاستعارة والكناية والمجاز والمحسنات إن وجدت.

في الصرف:
اذكر الجذر والوزن والنوع والمجرد والمزيد عند الحاجة.

في المعجم:
اذكر معنى الكلمة في السياق وجذرها والمعاني المهمة الأخرى.

في العروض:
حاول تحديد البحر والتفعيلات والتقطيع والقافية والروي.
استخدم / للمتحرك و o للساكن عند الحاجة.
إذا كان الوزن غير مؤكد فلا تجزم.

في تحديد الشاعر:
لا تخترع اسم شاعر.
اذكر العصر والقرائن ودرجة الثقة.

في شرح النص:
اذكر المعنى العام ثم شرح الأبيات أو الجمل والأفكار الرئيسية.
"""


# ============================================================
# Prompts
# ============================================================

PROMPTS = {

    "grammar": """
حلل النص التالي من ناحية الإعراب.

أريد:
1. الإعراب التفصيلي للكلمات المهمة.
2. علامة الإعراب.
3. سبب الإعراب.
4. الجمل الاسمية والفعلية.
5. الملاحظات النحوية المهمة.

النص:
""",

    "rhetoric": """
حلل النص التالي بلاغياً.

أريد:
1. التشبيه.
2. الاستعارة.
3. الكناية.
4. المجاز.
5. الطباق والمقابلة.
6. الجناس والسجع إن وجدا.
7. أثر الأساليب البلاغية.

النص:
""",

    "morphology": """
حلل النص التالي صرفياً.

أريد:
1. الكلمات المهمة.
2. الجذر.
3. الوزن الصرفي.
4. نوع الكلمة.
5. مجرد أم مزيد.
6. المصدر أو التصريف عند الحاجة.
7. الملاحظات الصرفية.

النص:
""",

    "dictionary": """
حلل مفردات النص التالي معجمياً.

لكل كلمة مهمة اذكر:
1. الكلمة.
2. معناها في السياق.
3. جذرها.
4. المعاني الأخرى المهمة.
5. مثال عند الحاجة.

النص:
""",

    "explain": """
اشرح النص التالي شرحاً واضحاً.

أريد:
1. المعنى العام.
2. شرح الجمل أو الأبيات.
3. الأفكار الرئيسية.
4. الكلمات الصعبة.
5. الفكرة الأساسية.
6. ملاحظات مفيدة للطالب.

النص:
""",

    "prosody": """
حلل النص التالي من ناحية العروض والقافية.

أريد:
1. البحر الشعري المحتمل.
2. التفعيلات.
3. التقطيع العروضي.
4. استخدم / للمتحرك و o للساكن.
5. القافية.
6. الروي.
7. الوصل والخروج إن أمكن.
8. الزحافات والعلل إن وجدت.
9. هل البيت موزون أم لا؟

مهم:
إذا كان البحر غير مؤكد، اذكر ذلك ولا تجزم.

النص:
""",

    "poet": """
حلل النص التالي لمعرفة الشاعر والعصر.

أريد:
1. العصر الأدبي المحتمل.
2. الخصائص الأسلوبية.
3. القرائن.
4. أسماء شعراء محتملين إذا وجدت قرائن قوية.
5. درجة الثقة.

مهم:
لا تخترع اسم شاعر.
لا تجزم بالهوية من الأسلوب وحده.

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
# Temporary Error Check
# ============================================================

def is_temporary_error(error):

    text = str(error).upper()

    return (
        "503" in text
        or "UNAVAILABLE" in text
        or "504" in text
        or "DEADLINE_EXCEEDED" in text
        or "DEADLINE EXCEEDED" in text
        or "TIMEOUT" in text
    )


# ============================================================
# Generate With Model
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
        "Trying Gemini model: %s",
        model
    )

    full_prompt = (
        SYSTEM_PROMPT
        + "\n\n"
        + prompt
    )

    response = client.models.generate_content(

        model=model,

        contents=full_prompt,

        config=types.GenerateContentConfig(

            max_output_tokens=2000
        )
    )

    if not response:

        raise RuntimeError(
            "Gemini أعاد استجابة فارغة."
        )

    result = getattr(
        response,
        "text",
        None
    )

    if not result:

        raise RuntimeError(
            "Gemini لم يرجع نصاً."
        )

    return result.strip()


# ============================================================
# Main Generate
# ============================================================

def _generate(prompt):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "مفتاح Gemini غير موجود."
        )

    if client is None:

        raise RuntimeError(
            "تعذر الاتصال بخدمة Gemini."
        )

    last_error = None

    for model in FALLBACK_MODELS:

        try:

            return _generate_with_model(
                model,
                prompt
            )

        except Exception as error:

            last_error = error

            if is_temporary_error(error):

                logger.warning(
                    "Gemini model %s temporary error: %s. "
                    "Trying next model.",
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

    if not text or not text.strip():

        return (
            "❌ ما وصلني نص للتحليل.\n\n"
            "أرسل النص أولاً ثم اختر نوع التحليل."
        )

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

    if mode not in PROMPTS:

        mode = "explain"

    prompt = (
        PROMPTS[mode]
        + "\n\n"
        + text.strip()
    )

    try:

        result = await asyncio.to_thread(
            _generate,
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
                "حاول مرة ثانية بعد قليل 🔄"
            )

        if (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):

            return (
                "⚠️ Gemini مشغول حالياً.\n\n"
                "حاول مرة ثانية بعد قليل 🔄"
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
        "explain",
        "العلم نور."
    )
