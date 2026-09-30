# -*- coding: utf-8 -*-
"""نبذة عن الشخصيات والأعلام، مع تركيز خاص على اللغة العربية."""

import asyncio
import os
import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
CHARACTER_MODEL = os.getenv(
    "CHARACTER_MODEL",
    "gemini-3.1-flash-lite",
).strip()

client = None

if GEMINI_API_KEY:
    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
                api_version="v1",
                timeout=30000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    except Exception:
        logger.exception("Failed to initialize Character Gemini client.")
        client = None


def _generate_sync(name):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY غير موجود.")
    if client is None:
        raise RuntimeError("تعذر إنشاء اتصال Gemini.")

    prompt = f"""
أنت مساعد أكاديمي متخصص في اللغة العربية والأدب العربي والتاريخ الثقافي.

أريد معلومات موثوقة ومختصرة عن الشخصية التالية:

{str(name).strip()}

اكتب بالعربية الفصحى، وركز خصوصاً على الشخصيات المرتبطة باللغة العربية والأدب والنحو والبلاغة والشعر والنقد والتأليف.

مهم جداً:
- لا تخترع معلومات أو مؤلفات أو تواريخ.
- إذا كان الاسم غير واضح أو توجد شخصيات متعددة بالاسم نفسه، اذكر ذلك بوضوح.
- إذا لم تكن متأكداً من معلومة، لا تعرضها كحقيقة.
- ميّز بين المعلومات المؤكدة والآراء أو الأقوال المنسوبة.
- لا تجعل النبذة طويلة.

استخدم هذا التنسيق:

👤 الاسم:
...

📅 العصر / الفترة:
...

📚 المجال:
...

📝 نبذة:
فقرة قصيرة.

🔤 علاقته باللغة العربية:
اذكر أهم ما عُرف به في العربية أو الأدب أو النحو أو البلاغة أو الشعر، إن وُجد.

📖 أبرز المؤلفات أو الأعمال:
- ...
- ...
- ...

⭐ لماذا يُذكر في دراسة العربية؟
سطران كحد أقصى.
"""

    interaction = client.interactions.create(
        model=CHARACTER_MODEL,
        input=prompt,
        generation_config={
            "thinking_level": "minimal",
            "max_output_tokens": 900,
        },
    )

    result = getattr(interaction, "output_text", None)
    if not result:
        raise RuntimeError("Gemini لم يرجع نصاً.")
    return result.strip()


async def get_character(name):
    name = str(name or "").strip()
    if not name:
        return False, "❌ اكتب اسم الشخصية أولاً."

    if len(name) > 150:
        name = name[:150].strip()

    try:
        result = await asyncio.to_thread(_generate_sync, name)
        return True, result
    except Exception as error:
        logger.exception("Character lookup failed.")
        error_text = str(error).upper()
        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            return False, "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n\nحاول مرة ثانية بعد قليل."
        if "503" in error_text or "UNAVAILABLE" in error_text:
            return False, "⚠️ Gemini مشغول حالياً.\n\nحاول مرة ثانية."
        if "504" in error_text or "TIMEOUT" in error_text or "DEADLINE_EXCEEDED" in error_text:
            return False, "⏱️ تأخر البحث عن الشخصية.\n\nحاول مرة ثانية."
        return False, "❌ تعذر إعداد نبذة عن الشخصية حالياً.\n\nحاول مرة ثانية."


__all__ = ["get_character"]


def _generate_detail_sync(name):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY غير موجود.")
    if client is None:
        raise RuntimeError("تعذر إنشاء اتصال Gemini.")

    prompt = f"""
أنت مساعد أكاديمي متخصص في تراجم أعلام اللغة العربية والأدب والفكر العربي.

اكتب سيرة تفصيلية تعليمية للشخصية التالية:

{name}

التزم بالقواعد التالية:
- لا تخترع أي معلومة أو تاريخ أو كتاب أو شيخ أو تلميذ.
- إذا كانت هوية الشخصية غير واضحة أو يوجد أكثر من شخص بهذا الاسم، اذكر ذلك ولا تختر شخصية من عندك.
- إذا لم تكن متأكداً من معلومة، اذكر أنها غير مؤكدة أو احذفها.
- لا تنسب كتاباً أو قولاً إلى الشخصية إلا إذا كان معروفاً على نحو موثوق.
- اجعل النص مناسباً لطالب يريد التعمق في الشخصية.
- استخدم العربية الفصحى الواضحة.
- لا تستخدم جداول.
- في قسم المصادر، اذكر فقط المراجع المعروفة التي ترتبط بالشخصية فعلاً، ولا تخترع أرقام صفحات أو روابط.

استخدم هذا التنظيم:

🏺 سيرته وحياته

🧬 نشأته ونسبه
اذكر أصله ونشأته وأسرته بالقدر المعروف.

🎓 طلبه للعلم وشيوخه
اذكر رحلته العلمية وشيوخه إن كانوا معروفين.

📚 علمه ومكانته
اشرح تخصصه ومكانته العلمية وأهم ما عُرف به.

🪶 أبرز مؤلفاته وآثاره
اذكر أشهر الكتب أو الأعمال، مع وصف مختصر لكل عمل إن أمكن.

👥 تلاميذه ومن تأثر بهم
اذكرهم فقط إذا كانوا معروفين ومثبتين.

🏛️ أهم محطات حياته
رتب أهم المحطات زمنياً قدر الإمكان دون اختراع تواريخ.

💡 أبرز أفكاره وإسهاماته
وضح إسهاماته في اللغة أو الأدب أو النحو أو البلاغة أو الشعر أو الفكر بحسب الشخصية.

🕊️ وفاته
اذكر مكان وزمان الوفاة إذا كانا معروفين، مع التنبيه عند وجود اختلاف مشهور.

📌 أثره في اللغة والأدب
وضح أثره العلمي أو الأدبي وما بقي من تأثيره.

📚 مصادر ومراجع للتوسع
اذكر مصادر تراثية أو دراسات معروفة يمكن للطالب الرجوع إليها. لا تضع روابط غير متأكد منها.
"""

    interaction = client.interactions.create(
        model=CHARACTER_MODEL,
        input=prompt,
        generation_config={
            "thinking_level": "minimal",
            "max_output_tokens": 1800,
        },
    )

    result = getattr(interaction, "output_text", None)
    if not result:
        raise RuntimeError("Gemini لم يرجع نصاً.")
    return result.strip()


async def get_character_detail(name):
    name = str(name or "").strip()
    if not name:
        return False, "❌ اكتب اسم الشخصية أولاً."

    if len(name) > 150:
        name = name[:150].strip()

    try:
        result = await asyncio.to_thread(_generate_detail_sync, name)
        return True, result
    except Exception as error:
        logger.exception("Character detailed lookup failed.")
        error_text = str(error).upper()
        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            return False, "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n\nحاول مرة ثانية بعد قليل."
        if "503" in error_text or "UNAVAILABLE" in error_text:
            return False, "⚠️ Gemini مشغول حالياً.\n\nحاول مرة ثانية."
        if "504" in error_text or "TIMEOUT" in error_text or "DEADLINE_EXCEEDED" in error_text:
            return False, "⏱️ تأخر إعداد السيرة التفصيلية.\n\nحاول مرة ثانية."
        return False, "❌ تعذر إعداد السيرة التفصيلية حالياً.\n\nحاول مرة ثانية."


__all__ = ["get_character", "get_character_detail"]
