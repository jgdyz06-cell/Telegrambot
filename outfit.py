# -*- coding: utf-8 -*-
"""
Outfit System
نظام تنسيق الملابس والخزانة
"""

import os
import asyncio
import logging

from google import genai
from google.genai import types

import db


logger = logging.getLogger(__name__)


# ============================================================
# Gemini
# ============================================================

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    ""
).strip()

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.1-flash-lite"
).strip()


client = None


if GEMINI_API_KEY:

    try:

        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
                api_version="v1",
                timeout=30000,
                retry_options=types.HttpRetryOptions(
                    attempts=1
                )
            )
        )

        logger.info(
            "Outfit Gemini client initialized: %s",
            GEMINI_MODEL
        )

    except Exception:

        logger.exception(
            "Failed to initialize Outfit Gemini client."
        )

        client = None


# ============================================================
# Constants
# ============================================================

GENDER_NAMES = {
    "him": "For Him",
    "her": "For Her",
}


# ============================================================
# Gender
# ============================================================

def valid_gender(gender):
    return gender in ("him", "her")


def gender_name(gender):

    return GENDER_NAMES.get(
        gender,
        gender
    )


# ============================================================
# Add clothing
# ============================================================

def add_item(
    user_id,
    gender,
    category,
    color,
):
    """
    إضافة قطعة ملابس إلى خزانة المستخدم.
    """

    if not valid_gender(gender):
        raise ValueError("قسم الملابس غير صحيح.")

    category = str(category or "").strip()
    color = str(color or "").strip()

    if not category:
        raise ValueError("نوع القطعة فارغ.")

    if not color:
        raise ValueError("لون القطعة فارغ.")

    if len(category) > 100:
        category = category[:100]

    if len(color) > 100:
        color = color[:100]

    return db.add_wardrobe_item(
        user_id,
        gender,
        category,
        color,
    )


# ============================================================
# Get wardrobe
# ============================================================

def get_items(
    user_id,
    gender,
):
    """
    جلب ملابس المستخدم حسب القسم.
    """

    if not valid_gender(gender):
        return []

    return db.get_wardrobe_items(
        user_id,
        gender,
    )


# ============================================================
# Delete item
# ============================================================

def delete_item(
    user_id,
    item_id,
):
    """
    حذف قطعة محددة من خزانة المستخدم.
    """

    return db.delete_wardrobe_item(
        item_id,
        user_id,
    )


# ============================================================
# Clear wardrobe
# ============================================================

def clear_items(
    user_id,
    gender,
):
    """
    حذف جميع الملابس من قسم معين.
    """

    if not valid_gender(gender):
        return 0

    return db.clear_wardrobe(
        user_id,
        gender,
    )


# ============================================================
# Count
# ============================================================

def count_items(
    user_id,
    gender,
):
    if not valid_gender(gender):
        return 0

    return db.count_wardrobe_items(
        user_id,
        gender,
    )


# ============================================================
# Format wardrobe
# ============================================================

def format_wardrobe(
    items,
    gender,
):
    """
    تحويل الملابس إلى نص مرتب.
    """

    title = gender_name(gender)

    if not items:

        return (
            f"👕 الخزانة — {title}\n\n"
            "الخزانة فارغة حالياً.\n\n"
            "اضغط «➕ إضافة قطعة» حتى تضيف أول قطعة."
        )

    text = (
        f"👕 الخزانة — {title}\n\n"
        "الملابس المحفوظة:\n\n"
    )

    for index, item in enumerate(
        items,
        start=1
    ):

        item_id = item.get("id")

        category = item.get(
            "category",
            "قطعة"
        )

        color = item.get(
            "color",
            "غير محدد"
        )

        text += (
            f"{index}. "
            f"👕 {category} — "
            f"🎨 {color}"
        )

        if item_id is not None:
            text += f"  #{item_id}"

        text += "\n"

    text += (
        "\n━━━━━━━━━━━━━━\n"
        f"📦 عدد القطع: {len(items)}"
    )

    return text


# ============================================================
# Build AI wardrobe
# ============================================================

def build_wardrobe_prompt(
    items,
    gender,
):
    """
    بناء Prompt صارم حتى Gemini لا يخترع ملابس.
    """

    title = gender_name(gender)

    if not items:
        return None

    lines = []

    for item in items:

        category = str(
            item.get(
                "category",
                ""
            )
        ).strip()

        color = str(
            item.get(
                "color",
                ""
            )
        ).strip()

        if not category:
            continue

        lines.append(
            f"- {category} | اللون: {color}"
        )

    if not lines:
        return None

    wardrobe_text = "\n".join(lines)

    return f"""
أنت خبير تنسيق ملابس.

القسم:
{title}

هذه هي الملابس التي يملكها المستخدم فعلياً:

{wardrobe_text}

مهم جداً:

- استخدم فقط الملابس الموجودة في القائمة.
- ممنوع اختراع أي قطعة ملابس جديدة.
- ممنوع إضافة لون غير موجود للقطعة.
- ممنوع اقتراح قطعة غير موجودة في القائمة.
- لا تفترض أن المستخدم يمتلك حذاء أو بنطال أو قميصاً إذا لم يكن موجوداً.
- إذا كانت الملابس غير كافية لتكوين تنسيق كامل، قل ذلك بوضوح.
- يمكنك عدم استخدام بعض القطع.
- يمكنك إنشاء أكثر من تنسيق باستخدام القطع الموجودة فقط.
- حافظ على ألوان القطع كما هي.
- اجعل الاقتراحات عملية ومناسبة للألوان.

أعطني 3 تنسيقات كحد أقصى.

لكل تنسيق:

✨ التنسيق الأول
👕 القطع:
- القطعة + اللون
- القطعة + اللون

🎨 تناسق الألوان:
شرح قصير جداً.

💡 ملاحظة:
ملاحظة قصيرة عن المناسبة أو طريقة اللبس.

ثم التنسيق الثاني والثالث بنفس الطريقة عند إمكانية ذلك.

لا تضف مقدمة طويلة.
"""


# ============================================================
# Gemini generation
# ============================================================

def _generate_outfit(
    prompt,
):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY غير موجود."
        )

    if client is None:

        raise RuntimeError(
            "تعذر إنشاء اتصال Gemini."
        )

    interaction = client.interactions.create(
        model=GEMINI_MODEL,
        input=prompt,
        generation_config={
            "thinking_level": "minimal",
            "max_output_tokens": 700,
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


# ============================================================
# Generate outfit
# ============================================================

async def generate_outfit(
    user_id,
    gender,
):
    """
    توليد تنسيق باستخدام الملابس المحفوظة فقط.
    """

    if not valid_gender(gender):

        return (
            False,
            "❌ قسم الملابس غير صحيح."
        )

    items = get_items(
        user_id,
        gender,
    )

    if not items:

        return (
            False,
            "👕 ما عندك ملابس محفوظة بهذا القسم بعد.\n\n"
            "أضف بعض القطع والألوان أولاً، وبعدها أقدر "
            "أرتب لك تنسيقات منها."
        )

    prompt = build_wardrobe_prompt(
        items,
        gender,
    )

    if not prompt:

        return (
            False,
            "❌ ما قدرت أقرأ الملابس المحفوظة."
        )

    try:

        result = await asyncio.to_thread(
            _generate_outfit,
            prompt,
        )

        if not result:

            return (
                False,
                "❌ Gemini لم يرجع تنسيقاً."
            )

        return (
            True,
            result,
        )

    except Exception as error:

        logger.exception(
            "Outfit generation failed."
        )

        error_text = str(
            error
        ).upper()

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):

            return (
                False,
                "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n\n"
                "حاول مرة ثانية بعد قليل 🔄"
            )

        if (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):

            return (
                False,
                "⚠️ Gemini مشغول حالياً.\n\n"
                "حاول مرة ثانية 🔄"
            )

        if (
            "504" in error_text
            or "TIMEOUT" in error_text
            or "DEADLINE_EXCEEDED" in error_text
        ):

            return (
                False,
                "⏱️ Gemini تأخر بالاستجابة.\n\n"
                "حاول مرة ثانية 🔄"
            )

        return (
            False,
            "❌ حدث خطأ أثناء إنشاء التنسيق.\n\n"
            "حاول مرة ثانية 🔄"
        )


# ============================================================
# Parse user clothing input
# ============================================================

def parse_item_text(text):
    """
    يقبل:

    قميص - أسود
    قميص: أسود
    قميص، أسود
    قميص, أسود
    """

    text = str(
        text or ""
    ).strip()

    if not text:
        return None, None

    separators = (
        "-",
        "—",
        ":",
        "،",
        ",",
        "|",
    )

    for separator in separators:

        if separator not in text:
            continue

        parts = text.split(
            separator,
            1
        )

        category = parts[0].strip()
        color = parts[1].strip()

        if category and color:

            return (
                category,
                color,
            )

    return None, None


# ============================================================
# Export
# ============================================================

__all__ = [
    "valid_gender",
    "gender_name",
    "add_item",
    "get_items",
    "delete_item",
    "clear_items",
    "count_items",
    "format_wardrobe",
    "generate_outfit",
    "parse_item_text",
]
