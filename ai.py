# ai.py
# ============================================================
# Gemini AI for Telegram Bot
# ============================================================

import os
import asyncio
import logging
import random

from google import genai
from google.genai import types


# ============================================================
# Logging
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Gemini Settings
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
).strip()

# نخلي عدد الموديلات قليل حتى لا يطول الانتظار
FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
]


# ============================================================
# Gemini Client
# ============================================================

client = None

if GEMINI_API_KEY:
    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY
        )
        logger.info("Gemini client initialized successfully.")
    except Exception:
        logger.exception("Failed to initialize Gemini client.")
        client = None
else:
    logger.warning("GEMINI_API_KEY is not set.")


# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """
أنت مساعد ذكاء اصطناعي عربي متخصص في اللغة العربية.

تحدث مع المستخدم باللغة العربية الواضحة والبسيطة.

عند تحليل النصوص العربية:
- كن دقيقاً قدر الإمكان.
- لا تخترع معلومات غير موجودة في النص.
- إذا كانت هناك احتمالات متعددة، اذكرها.
- إذا لم تكن متأكداً من معلومة، صرّح بعدم اليقين.
- استخدم أمثلة من النص نفسه عندما يكون ذلك مفيداً.
- اجعل الإجابة منظمة وسهلة القراءة.

في الإعراب:
- اذكر إعراب الكلمات المهمة بالتفصيل.
- اذكر علامة الإعراب وسببها.
- وضح العلاقات النحوية.

في البلاغة:
- حدد التشبيه والاستعارة والكناية والمجاز والمحسنات إن وجدت.
- لا تعتبر كل تعبير مجازاً بدون دليل.

في الصرف:
- اذكر الجذر.
- الوزن الصرفي.
- نوع الكلمة.
- الزيادة إن وجدت.
- التصريف أو المصدر عند الحاجة.

في المعجم:
- اذكر المعنى المناسب للسياق.
- الجذر.
- معانٍ أخرى مهمة عند الحاجة.
- لا تنسب نصاً حرفياً إلى معجم معين إذا لم تكن متأكداً منه.

في العروض:
- حاول تحديد البحر.
- اذكر التفعيلات.
- استخدم / للحرف المتحرك و o للحرف الساكن عندما يكون ذلك مناسباً.
- اذكر القافية والروي إن أمكن.
- إذا كان النص غير موزون أو يحتاج إلى ضبط حركات، وضح ذلك.
- لا تجزم بالبحر إذا كانت القراءة تحتمل أكثر من وجه.

في تحديد الشاعر والعصر:
- لا تجزم بهوية الشاعر من مجرد الأسلوب.
- اذكر القرائن.
- إذا لم تتوفر قرائن كافية، قل إن التحديد غير مؤكد.

في شرح النص:
- اشرح المعنى العام.
- ثم اشرح الجمل أو الأبيات المهمة.
- ثم استخرج الأفكار الرئيسية.
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
4. الجملة الفعلية أو الاسمية إن وجدت.
5. أي ملاحظات نحوية مهمة.

النص:
""",

    "rhetoric": """
حلل النص التالي بلاغياً.

أريد:
1. التشبيه.
2. الاستعارة.
3. الكناية.
4. المجاز.
5. الطباق والمقابلة والجناس والسجع إن وجدت.
6. أثر الأساليب البلاغية في المعنى.

لا تذكر فناً بلاغياً إلا إذا كان له دليل واضح من النص.

النص:
""",

    "morphology": """
حلل النص التالي من الناحية الصرفية.

أريد:
1. الكلمات المهمة.
2. جذر كل كلمة.
3. الوزن الصرفي.
4. نوع الكلمة.
5. المجرد والمزيد.
6. المصدر أو التصريفات المهمة عند الحاجة.
7. أي ملاحظات صرفية مهمة.

النص:
""",

    "dictionary": """
حلل مفردات النص التالي معجمياً.

لكل كلمة مهمة اذكر:
1. الكلمة.
2. معناها في السياق.
3. جذرها.
4. معنى أو معاني أخرى مهمة.
5. مثال قصير إن كان مفيداً.

إذا طلب المستخدم معلومات مرتبطة بلسان العرب أو المعجم الوسيط، وضح أن المعلومات تقريبية ما لم يكن النص المعجمي متاحاً أمامك.

النص:
""",

    "explain": """
اشرح النص التالي شرحاً واضحاً ومفيداً.

أريد:
1. المعنى العام.
2. شرح كل جملة أو بيت باختصار.
3. الأفكار الرئيسية.
4. الكلمات الصعبة.
5. الفكرة أو الرسالة الأساسية للنص.
6. ملاحظات مهمة للطالب.

النص:
""",

    "prosody": """
حلل النص التالي من ناحية العروض والقافية.

أريد:
1. محاولة تحديد البحر الشعري.
2. التفعيلات.
3. التقطيع العروضي قدر الإمكان.
4. استخدم / للمتحرك و o للساكن.
5. القافية.
6. الروي.
7. الوصل والخروج إن أمكن.
8. أي زحاف أو علة مهمة.
9. إذا كان البيت غير موزون أو يحتاج إلى ضبط حركات، وضح ذلك.

مهم:
لا تجزم بالبحر إذا كان النص يحتمل أكثر من قراءة.

النص:
""",

    "poet": """
حلل النص التالي لمحاولة معرفة الشاعر والعصر.

أريد:
1. العصر الأدبي المحتمل.
2. الخصائص الأسلوبية.
3. القرائن الموجودة في النص.
4. أسماء شعراء محتملين فقط إذا كانت هناك قرائن.
5. درجة الثقة في النتيجة.

مهم:
لا تخترع اسم شاعر.
لا تجزم بهوية الشاعر اعتماداً على الأسلوب وحده.

النص:
"""
}


# ============================================================
# Check Configuration
# ============================================================

def check_gemini_config():
    """
    التأكد من وجود مفتاح Gemini.
    """

    if not GEMINI_API_KEY:
        return False, "GEMINI_API_KEY غير موجود في Railway Variables."

    if client is None:
        return False, "تعذر إنشاء اتصال Gemini."

    return True, "Gemini جاهز."


# ============================================================
# Detect 503
# ============================================================

def is_503_error(error):
    """
    فحص أخطاء Gemini التي تعني أن الخدمة مشغولة أو غير متاحة مؤقتاً.
    """

    text = str(error).upper()

    return (
        "503" in text
        or "UNAVAILABLE" in text
        or "SERVICE UNAVAILABLE" in text
    )


# ============================================================
# Generate with one model
# ============================================================

def _generate_with_model(model, prompt):

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
            max_output_tokens=3000,
        ),
    )

    if not response:
        raise RuntimeError(
            "Gemini أعاد استجابة فارغة."
        )

    text = getattr(
        response,
        "text",
        None
    )

    if not text:
        raise RuntimeError(
            "Gemini لم يرجع نصاً في الاستجابة."
        )

    return text.strip()


# ============================================================
# Generate with retry + fallback
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

    # نحاول كل موديل بحد أقصى مرتين
    for model in FALLBACK_MODELS:

        for attempt in range(2):

            try:

                logger.info(
                    "Gemini request: model=%s attempt=%s/2",
                    model,
                    attempt + 1
                )

                return _generate_with_model(
                    model,
                    prompt
                )

            except Exception as error:

                last_error = error

                # إذا الخطأ ليس 503
                # لا نكرر المحاولة بلا داعٍ
                if not is_503_error(error):

                    logger.exception(
                        "Gemini request failed."
                    )

                    raise RuntimeError(
                        f"Gemini error: {error}"
                    ) from error

                # 503
                logger.warning(
                    "Gemini model %s returned 503 "
                    "(attempt %s/2).",
                    model,
                    attempt + 1
                )

                # إذا بقيت محاولة ثانية
                if attempt == 0:

                    # تأخير 2-4 ثواني
                    delay = 2 + random.random() * 2

                    logger.info(
                        "Waiting %.1f seconds before retry...",
                        delay
                    )

                    import time
                    time.sleep(delay)

        logger.warning(
            "Model %s is unavailable. "
            "Trying next fallback model.",
            model
        )

    # إذا فشلت كل المحاولات
    raise RuntimeError(
        "خدمة Gemini مشغولة حالياً (503). "
        "حاول مرة أخرى بعد قليل."
    ) from last_error


# ============================================================
# Public AI Function
# ============================================================

async def ask_ai(
    mode,
    text
):
    """
    إرسال النص إلى Gemini حسب نوع التحليل.
    """

    if not text or not text.strip():

        return (
            "❌ ما وصلني نص للتحليل.\n"
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

    # إذا كان الوضع غير معروف
    if mode not in PROMPTS:

        mode = "explain"

    prompt = (
        PROMPTS[mode]
        + "\n\n"
        + text.strip()
    )

    try:

        # تشغيل الطلب خارج event loop
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

        error_text = str(error)

        if is_503_error(error):

            return (
                "⚠️ خدمة الذكاء الاصطناعي مشغولة حالياً.\n\n"
                "Gemini أعاد الخطأ 503، وهذا يعني أن "
                "الخدمة تواجه ضغطاً مؤقتاً.\n\n"
                "🔄 حاول مرة أخرى بعد قليل."
            )

        return (
            "❌ حدث خطأ أثناء تحليل النص.\n\n"
            f"التفاصيل: {error_text}"
        )


# ============================================================
# Simple AI Test
# ============================================================

async def test_ai():

    result = await ask_ai(
        "explain",
        "العلم نور."
    )

    return result
