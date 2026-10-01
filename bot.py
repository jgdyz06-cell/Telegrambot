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
from urllib.parse import quote_plus

import httpx

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
import weather

from config import BOT_TOKEN, logger

from ui import (
    SUB_TEXT,
    ai_markup,
    is_admin,
    is_subscribed,
    main_menu as ui_main_menu,
    send_summary,
    show,
    sub_markup,
    subjects_markup,
)

from ai import ask_ai


# ============================================================
# Built-in Book Library + Characters
# ============================================================

class _LibraryModule:

    NOOR_BASE = "https://www.noor-book.com/"
    SHAMELA_BASE = "https://shamela.ws/"

@staticmethod
def _clean_query(query):
    return " ".join(str(query or "").strip().split())[:300]

@classmethod
def build_noor_search_url(cls, query):
    query = cls._clean_query(query)
    return f"{cls.NOOR_BASE}?q={quote_plus(query)}"

@classmethod
def build_shamela_search_url(cls, query):
    query = cls._clean_query(query)
    return f"{cls.SHAMELA_BASE}search?query={quote_plus(query)}"

@classmethod
def format_search_result(cls, query):
    query = cls._clean_query(query) or "غير محدد"
    return (
        "📚 <b>مكتبة الكتب</b>\n\n"
        f"🔎 البحث عن: <b>{query}</b>\n\n"
        "وجدت لك روابط بحث مباشرة في مصادر الكتب.\n"
        "يمكنك فتح المصدر واختيار النسخة المتاحة هناك.\n\n"
        "📌 إذا كانت نسخة PDF محمية بحقوق النشر، استخدم النسخة التي يتيحها المصدر قانونياً."
    )


library = _LibraryModule()


class _CharacterModule:

    CHARACTER_MODEL = os.getenv("CHARACTER_MODEL", "gemini-2.5-flash").strip()

    KNOWN = {
        "الجاحظ": {
            "name": "أبو عثمان عمرو بن بحر الجاحظ",
            "era": "القرن الثالث الهجري / العصر العباسي",
            "field": "الأدب واللغة والنقد والفكر",
            "summary": "أديب ومفكر عربي من أبرز أعلام النثر العربي في العصر العباسي، عُرف بأسلوبه في الكتابة وملاحظاته في اللغة والأدب والمجتمع.",
            "works": "البيان والتبيين، الحيوان، البخلاء.",
        },
        "المتنبي": {
            "name": "أبو الطيب أحمد بن الحسين المتنبي",
            "era": "القرن الرابع الهجري / العصر العباسي",
            "field": "الشعر واللغة",
            "summary": "من أشهر شعراء العربية، امتاز شعره بقوة اللغة والحكمة والصور البلاغية، وكان له أثر واسع في تاريخ الشعر العربي.",
            "works": "ديوان المتنبي، ومن أشهر قصائده قصائد المدح والحكمة والرثاء.",
        },
        "سيبويه": {
            "name": "أبو بشر عمرو بن عثمان سيبويه",
            "era": "القرن الثاني الهجري",
            "field": "النحو واللغة العربية",
            "summary": "من أعلام النحو العربي، وصاحب الكتاب الذي صار من أهم المصادر المؤسسة للدراسات النحوية العربية.",
            "works": "الكتاب.",
        },
        "الخليل بن أحمد": {
            "name": "الخليل بن أحمد الفراهيدي",
            "era": "القرن الثاني الهجري",
            "field": "اللغة والعَروض والمعاجم",
            "summary": "عالم لغوي بارز أسهم في تأسيس علم العَروض، وكان له دور مهم في دراسة العربية ومعجم العين.",
            "works": "كتاب العين، ونسبة وضع علم العَروض إليه مشهورة في كتب التراث.",
        },
        "ابن منظور": {
            "name": "محمد بن مكرم بن منظور الإفريقي",
            "era": "القرن السابع والثامن الهجريين",
            "field": "اللغة والمعاجم",
            "summary": "لغوي ومصنف اشتهر بجمع المادة اللغوية في معجمه الكبير لسان العرب.",
            "works": "لسان العرب.",
        },
    }

@staticmethod
def _key(name):
    value = re.sub(r"[ًٌٍَُِّْـ]", "", str(name or ""))
    value = re.sub(r"^(أبو|ابو|الشيخ|الإمام|الامام)\s+", "", value.strip())
    return value

@classmethod
def _known(cls, name):
    raw = str(name or "").strip()
    key = cls._key(raw)
    for k, value in cls.KNOWN.items():
        if cls._key(k) == key or k in raw or raw in k:
            return value
    return None

@staticmethod
def _extract_text(data):
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        return ""

@classmethod
async def _gemini(cls, prompt):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{cls.CHARACTER_MODEL}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1400},
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                url,
                params={"key": api_key},
                json=payload,
            )
            response.raise_for_status()
            return cls._extract_text(response.json())
    except Exception:
        return ""

@classmethod
async def get_character(cls, name):
    name = " ".join(str(name or "").strip().split())[:150]
    if not name:
        return False, "❌ اكتب اسم الشخصية أولاً."
    known = cls._known(name)
    if known:
        return True, cls._format_card(known)
    prompt = f""" أنت مساعد أكاديمي عربي لقسم «سير الأعلام». اكتب نبذة دقيقة ومختصرة عن الشخصية التالية: {name} مهم: - لا تخترع معلومات. - إذا كان الاسم غامضاً أو لا تستطيع تحديد الشخصية بثقة، اذكر أن الاسم غير واضح واطلب تحديد الشخصية. - اجعل الجواب مناسباً للطلاب. - أخرج النص فقط. التنسيق: 🏺 الاسم: 📅 العصر: 📚 المجال: نبذة: ... 🪶 أبرز المؤلفات/الآثار: ... """
    result = await cls._gemini(prompt)
    if result:
        return True, result
    return False, "❌ لم أتمكن من التحقق من الشخصية حالياً.\n\nاكتب الاسم بصورة أوضح، أو جرّب اسماً آخر."

@classmethod
async def get_character_detail(cls, name):
    name = " ".join(str(name or "").strip().split())[:150]
    if not name:
        return "❌ لم يتم تحديد اسم الشخصية."
    known = cls._known(name)
    if known:
        return cls._known_detail(known)
    prompt = f""" اكتب سيرة أكاديمية عربية منظمة للشخصية: {name} لا تخمّن. إذا كان الاسم غير واضح أو توجد شخصيات متعددة بالاسم، اذكر ذلك واطلب التحديد. غطِّ فقط ما يمكن دعمه بثقة، وبالعناوين التالية: 📚 حياته وآثاره 🧬 نشأته ونسبه 🎓 طلبه للعلم وشيوخه 📚 علمه ومكانته 🪶 أبرز مؤلفاته 👥 تلاميذه ومن تأثر بهم 🏛️ أهم محطات حياته 💡 أبرز أفكاره وإسهاماته 🕊️ وفاته 📌 أثره في اللغة والأدب 📚 مصادر ومراجع للتوسع اكتب بلغة عربية واضحة ومناسبة للطلاب، ولا تضع روابط مخترعة. """
    result = await cls._gemini(prompt)
    if result:
        return result
    return "❌ تعذر إعداد السيرة التفصيلية حالياً. حاول مرة ثانية بعد قليل."

@staticmethod
def _format_card(item):
    return (
        "🏺 <b>سيرة علم</b>\n\n"
        f"👤 <b>الاسم:</b> {item['name']}\n"
        f"📅 <b>العصر:</b> {item['era']}\n"
        f"📚 <b>المجال:</b> {item['field']}\n\n"
        f"📝 <b>نبذة:</b>\n{item['summary']}\n\n"
        f"🪶 <b>أبرز الآثار:</b>\n{item['works']}"
    )

@staticmethod
def _known_detail(item):
    return (
        "📚 <b>حياته وآثاره</b>\n\n"
        f"👤 <b>{item['name']}</b>\n\n"
        f"🧬 <b>نشأته ونسبه</b>\n{item['name']} من أعلام التراث العربي، وتُذكر ترجمته في مصادر التراجم واللغة والأدب.\n\n"
        "🎓 <b>طلبه للعلم وشيوخه</b>\nارتبط تكوينه العلمي ببيئة العلم والرواية في عصره، وتفاصيل الشيوخ والتلاميذ تُراجع في كتب التراجم المتخصصة.\n\n"
        f"📚 <b>علمه ومكانته</b>\nبرز في مجال {item['field']}، واشتهر بأثره في الدرس العربي.\n\n"
        f"🪶 <b>أبرز مؤلفاته</b>\n{item['works']}\n\n"
        "👥 <b>تلاميذه ومن تأثر بهم</b>\nتُبحث هذه التفاصيل في مصادر التراجم والدراسات المتخصصة.\n\n"
        "🏛️ <b>أهم محطات حياته</b>\nتُراجع في كتب الطبقات والتراجم الخاصة بعصره.\n\n"
        "💡 <b>أبرز أفكاره وإسهاماته</b>\nأسهم في المجال الذي عُرف به، وترك أثراً في التراث العربي.\n\n"
        "🕊️ <b>وفاته</b>\nتُراجع سنة الوفاة وتفاصيلها في المصادر المتخصصة لتجنب نقل تاريخ غير موثق.\n\n"
        "📌 <b>أثره في اللغة والأدب</b>\nيمثل جزءاً مهماً من تاريخ الدراسات العربية والأدب بحسب تخصصه.\n\n"
        "📚 <b>مصادر ومراجع للتوسع</b>\nيمكن الرجوع إلى كتب التراجم وطبقات العلماء، وإلى مكتبة نور والمكتبة الشاملة للبحث عن المصادر والنصوص الأصلية."
    )


character = _CharacterModule()


# ============================================================
# Main Menu Extensions
# ============================================================

def main_menu(user_id):

    markup = ui_main_menu(user_id)

    try:
        rows = [list(row) for row in markup.inline_keyboard]
        rows.append([
            InlineKeyboardButton(
                "📚 مكتبة الكتب",
                callback_data="library",
            ),
            InlineKeyboardButton(
                "🏺 سير الأعلام",
                callback_data="character",
            ),
        ])
        return InlineKeyboardMarkup(rows)
    except Exception:
        logger.exception("Could not extend main menu.")
        return markup


# ============================================================
# Gemini Voice + Image + Grammar Challenge + Outfit
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


# ------------------------------------------------------------
# Outfit
# ------------------------------------------------------------

OUTFIT_MODEL = os.getenv(
    "OUTFIT_MODEL",
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
# قواعد اللغة العربية
# ============================================================

ARABIC_RULES = {

    "mubtada_khabar": {
        "title": "📌 المبتدأ والخبر",
        "text": (
            "📚 **المبتدأ والخبر**\n\n"
            "🔹 **التعريف:**\n"
            "المبتدأ اسم مرفوع يأتي غالباً في بداية الجملة الاسمية، "
            "والخبر هو الجزء الذي يتمم معنى الجملة ويخبر عن المبتدأ.\n\n"

            "🔹 **القاعدة:**\n"
            "المبتدأ مرفوع، والخبر مرفوع.\n\n"

            "🔹 **مثال:**\n"
            "العلمُ نافعٌ.\n\n"

            "العلمُ: مبتدأ مرفوع وعلامة رفعه الضمة.\n"
            "نافعٌ: خبر مرفوع وعلامة رفعه الضمة.\n\n"

            "🔹 **مثال آخر:**\n"
            "الطلابُ مجتهدون.\n\n"

            "الطلابُ: مبتدأ مرفوع.\n"
            "مجتهدون: خبر مرفوع بالواو لأنه جمع مذكر سالم.\n\n"

            "💡 **ملاحظة:**\n"
            "الجملة الاسمية الأساسية تتكون غالباً من مبتدأ وخبر."
        ),
    },

    "kana": {
        "title": "🔵 كان وأخواتها",
        "text": (
            "📚 **كان وأخواتها**\n\n"
            "🔹 **التعريف:**\n"
            "أفعال ناسخة تدخل على الجملة الاسمية، فترفع المبتدأ "
            "ويسمى اسمها، وتنصب الخبر ويسمى خبرها.\n\n"

            "🔹 **من أخوات كان:**\n"
            "كان، أصبح، أمسى، أضحى، ظل، بات، صار، ليس، "
            "ما زال، ما دام.\n\n"

            "🔹 **القاعدة:**\n"
            "اسم كان وأخواتها: مرفوع.\n"
            "خبر كان وأخواتها: منصوب.\n\n"

            "🔹 **مثال:**\n"
            "كانَ الجوُّ جميلاً.\n\n"

            "الجوُّ: اسم كان مرفوع.\n"
            "جميلاً: خبر كان منصوب.\n\n"

            "💡 **احفظها:**\n"
            "كان وأخواتها = ترفع الأول وتنصب الثاني."
        ),
    },

    "inna": {
        "title": "🟢 إن وأخواتها",
        "text": (
            "📚 **إن وأخواتها**\n\n"
            "🔹 **التعريف:**\n"
            "حروف ناسخة تدخل على الجملة الاسمية، فتنصب المبتدأ "
            "ويسمى اسمها، وترفع الخبر ويسمى خبرها.\n\n"

            "🔹 **من أخوات إن:**\n"
            "إنَّ، أنَّ، كأنَّ، لكنَّ، ليتَ، لعلَّ.\n\n"

            "🔹 **القاعدة:**\n"
            "اسم إن وأخواتها: منصوب.\n"
            "خبر إن وأخواتها: مرفوع.\n\n"

            "🔹 **مثال:**\n"
            "إنَّ الطالبَ مجتهدٌ.\n\n"

            "الطالبَ: اسم إن منصوب.\n"
            "مجتهدٌ: خبر إن مرفوع.\n\n"

            "💡 **احفظها:**\n"
            "إن وأخواتها = تنصب الأول وترفع الثاني."
        ),
    },

    "fael": {
        "title": "🔴 الفاعل",
        "text": (
            "📚 **الفاعل**\n\n"
            "🔹 **التعريف:**\n"
            "الفاعل هو الاسم الذي قام بالفعل أو اتصف به.\n\n"

            "🔹 **القاعدة:**\n"
            "الفاعل مرفوع دائماً.\n\n"

            "🔹 **مثال:**\n"
            "كتبَ الطالبُ الدرسَ.\n\n"

            "الطالبُ: فاعل مرفوع وعلامة رفعه الضمة.\n\n"

            "🔹 **مثال آخر:**\n"
            "نجحَ الطالبانِ.\n\n"

            "الطالبانِ: فاعل مرفوع وعلامة رفعه الألف لأنه مثنى.\n\n"

            "💡 **طريقة اكتشافه:**\n"
            "اسأل: من الذي قام بالفعل؟"
        ),
    },

    "naeb": {
        "title": "🟠 نائب الفاعل",
        "text": (
            "📚 **نائب الفاعل**\n\n"
            "🔹 **التعريف:**\n"
            "اسم يأتي بعد الفعل المبني للمجهول، ويحل محل الفاعل المحذوف.\n\n"

            "🔹 **القاعدة:**\n"
            "نائب الفاعل مرفوع دائماً.\n\n"

            "🔹 **مثال:**\n"
            "كُتِبَ الدرسُ.\n\n"

            "الدرسُ: نائب فاعل مرفوع.\n\n"

            "🔹 **مثال آخر:**\n"
            "كُرِّمَ الطالبانِ.\n\n"

            "الطالبانِ: نائب فاعل مرفوع بالألف لأنه مثنى.\n\n"

            "💡 **ملاحظة:**\n"
            "عند بناء الفعل للمجهول يُحذف الفاعل ويأتي نائب الفاعل مكانه."
        ),
    },

    "mafool": {
        "title": "🟣 المفعول به",
        "text": (
            "📚 **المفعول به**\n\n"
            "🔹 **التعريف:**\n"
            "اسم يدل على من وقع عليه فعل الفاعل.\n\n"

            "🔹 **القاعدة:**\n"
            "المفعول به منصوب.\n\n"

            "🔹 **مثال:**\n"
            "قرأَ الطالبُ الكتابَ.\n\n"

            "الكتابَ: مفعول به منصوب وعلامة نصبه الفتحة.\n\n"

            "🔹 **طريقة اكتشافه:**\n"
            "اسأل: ماذا فعل الفاعل؟ أو وقع الفعل على ماذا؟\n\n"

            "💡 **مثال:**\n"
            "شربَ الطفلُ الماءَ.\n"
            "الماءَ هو الشيء الذي وقع عليه فعل الشرب."
        ),
    },

    "naat": {
        "title": "🟡 النعت",
        "text": (
            "📚 **النعت (الصفة)**\n\n"
            "🔹 **التعريف:**\n"
            "النعت كلمة تصف اسماً قبلها يسمى المنعوت.\n\n"

            "🔹 **القاعدة المهمة:**\n"
            "النعت يتبع المنعوت في:\n"
            "1. الإعراب.\n"
            "2. التعريف والتنكير.\n"
            "3. التذكير والتأنيث.\n"
            "4. الإفراد والتثنية والجمع.\n\n"

            "🔹 **مثال:**\n"
            "جاءَ الطالبُ المجتهدُ.\n\n"

            "الطالبُ: منعوت مرفوع.\n"
            "المجتهدُ: نعت مرفوع.\n\n"

            "🔹 **مثال منصوب:**\n"
            "رأيتُ الطالبَ المجتهدَ.\n\n"

            "الطالبَ: مفعول به منصوب.\n"
            "المجتهدَ: نعت منصوب."
        ),
    },

    "hal": {
        "title": "🟤 الحال",
        "text": (
            "📚 **الحال**\n\n"
            "🔹 **التعريف:**\n"
            "الحال اسم نكرة يبين هيئة صاحبه وقت حدوث الفعل.\n\n"

            "🔹 **القاعدة:**\n"
            "الحال منصوب غالباً.\n\n"

            "🔹 **مثال:**\n"
            "عادَ الطالبُ مسروراً.\n\n"

            "مسروراً: حال منصوب، يبين هيئة الطالب عند عودته.\n\n"

            "🔹 **طريقة اكتشافه:**\n"
            "اسأل: كيف حدث الفعل؟\n\n"

            "مثال:\n"
            "دخلَ المعلمُ مبتسماً.\n\n"

            "كيف دخل المعلم؟\n"
            "مبتسماً."
        ),
    },

    "tamyiz": {
        "title": "⚫ التمييز",
        "text": (
            "📚 **التمييز**\n\n"
            "🔹 **التعريف:**\n"
            "اسم نكرة يوضح كلمة أو معنى مبهماً قبله.\n\n"

            "🔹 **القاعدة:**\n"
            "التمييز يكون منصوباً في كثير من استعمالاته.\n\n"

            "🔹 **مثال:**\n"
            "اشتريتُ عشرينَ كتاباً.\n\n"

            "كتاباً: تمييز منصوب.\n"
            "وهو يوضح المقصود بالعدد عشرين.\n\n"

            "🔹 **مثال آخر:**\n"
            "ازدادَ الطالبُ علماً.\n\n"

            "علماً: تمييز منصوب.\n\n"

            "💡 **ملاحظة:**\n"
            "التمييز يزيل الإبهام عن كلمة أو جملة قبله."
        ),
    },

    "mafool_mutlaq": {
        "title": "🟦 المفعول المطلق",
        "text": (
            "📚 **المفعول المطلق**\n\n"
            "🔹 **التعريف:**\n"
            "مصدر منصوب يأتي من لفظ الفعل، ويستخدم للتوكيد "
            "أو بيان النوع أو العدد.\n\n"

            "🔹 **أنواعه:**\n"
            "1. مؤكد للفعل.\n"
            "2. مبين للنوع.\n"
            "3. مبين للعدد.\n\n"

            "🔹 **مثال:**\n"
            "نجحَ الطالبُ نجاحاً.\n\n"

            "نجاحاً: مفعول مطلق منصوب، مؤكد للفعل.\n\n"

            "🔹 **مثال:**\n"
            "سارَ الجنديُّ سيرَ الأبطالِ.\n\n"

            "سيرَ: مفعول مطلق مبين للنوع."
        ),
    },

    "mafool_liajlih": {
        "title": "🟥 المفعول لأجله",
        "text": (
            "📚 **المفعول لأجله**\n\n"
            "🔹 **التعريف:**\n"
            "مصدر منصوب يبين سبب حدوث الفعل.\n\n"

            "🔹 **القاعدة:**\n"
            "يجيب غالباً عن سؤال: لماذا؟\n\n"

            "🔹 **مثال:**\n"
            "درستُ طلباً للنجاح.\n\n"

            "طلباً: مفعول لأجله منصوب، لأنه يبين سبب الدراسة.\n\n"

            "🔹 **مثال آخر:**\n"
            "سافرتُ طلباً للعلم.\n\n"

            "طلباً: مفعول لأجله منصوب.\n\n"

            "💡 **طريقة اكتشافه:**\n"
            "اسأل: لماذا حدث الفعل؟"
        ),
    },

    "asmaa_khamsa": {
        "title": "🟪 الأسماء الخمسة",
        "text": (
            "📚 **الأسماء الخمسة**\n\n"
            "🔹 هي:\n"
            "أب، أخ، حم، فو، ذو.\n\n"

            "🔹 **علامات إعرابها:**\n"
            "ترفع بالواو.\n"
            "تنصب بالألف.\n"
            "تجر بالياء.\n\n"

            "🔹 **مثال الرفع:**\n"
            "جاءَ أبوك.\n"
            "أبوك: فاعل مرفوع بالواو.\n\n"

            "🔹 **مثال النصب:**\n"
            "رأيتُ أباك.\n"
            "أباك: مفعول به منصوب بالألف.\n\n"

            "🔹 **مثال الجر:**\n"
            "مررتُ بأبيك.\n"
            "أبيك: اسم مجرور بالياء.\n\n"

            "💡 **ملاحظة:**\n"
            "لها شروط خاصة حتى تعرب بالحروف."
        ),
    },

    "dual": {
        "title": "🟩 المثنى",
        "text": (
            "📚 **المثنى**\n\n"
            "🔹 **التعريف:**\n"
            "اسم يدل على اثنين أو اثنتين بزيادة ألف ونون "
            "أو ياء ونون في آخره.\n\n"

            "🔹 **علامات الإعراب:**\n"
            "يرفع بالألف.\n"
            "ينصب بالياء.\n"
            "يجر بالياء.\n\n"

            "🔹 **مثال الرفع:**\n"
            "جاءَ الطالبانِ.\n"
            "الطالبانِ: فاعل مرفوع بالألف.\n\n"

            "🔹 **مثال النصب:**\n"
            "رأيتُ الطالبينِ.\n"
            "الطالبينِ: مفعول به منصوب بالياء.\n\n"

            "🔹 **مثال الجر:**\n"
            "مررتُ بالطالبينِ.\n"
            "الطالبينِ: اسم مجرور بالياء."
        ),
    },

    "masculine_plural": {
        "title": "🟧 جمع المذكر السالم",
        "text": (
            "📚 **جمع المذكر السالم**\n\n"
            "🔹 **التعريف:**\n"
            "ما دل على أكثر من اثنين بزيادة واو ونون أو ياء ونون "
            "مع بقاء مفرده سالماً.\n\n"

            "🔹 **علامات الإعراب:**\n"
            "يرفع بالواو.\n"
            "ينصب بالياء.\n"
            "يجر بالياء.\n\n"

            "🔹 **مثال الرفع:**\n"
            "حضرَ المعلمونَ.\n"
            "المعلمونَ: فاعل مرفوع بالواو.\n\n"

            "🔹 **مثال النصب:**\n"
            "كرّمتُ المعلمينَ.\n"
            "المعلمينَ: مفعول به منصوب بالياء.\n\n"

            "🔹 **مثال الجر:**\n"
            "سلّمتُ على المعلمينَ.\n"
            "المعلمينَ: اسم مجرور بالياء."
        ),
    },

    "feminine_plural": {
        "title": "🟥 جمع المؤنث السالم",
        "text": (
            "📚 **جمع المؤنث السالم**\n\n"
            "🔹 **التعريف:**\n"
            "ما دل على أكثر من اثنتين بزيادة ألف وتاء على مفرده.\n\n"

            "🔹 **علامات الإعراب:**\n"
            "يرفع بالضمة.\n"
            "ينصب بالكسرة نيابة عن الفتحة.\n"
            "يجر بالكسرة.\n\n"

            "🔹 **مثال الرفع:**\n"
            "حضرتِ الطالباتُ.\n"
            "الطالباتُ: فاعل مرفوع بالضمة.\n\n"

            "🔹 **مثال النصب:**\n"
            "رأيتُ الطالباتِ.\n"
            "الطالباتِ: مفعول به منصوب بالكسرة نيابة عن الفتحة.\n\n"

            "🔹 **مثال الجر:**\n"
            "سلّمتُ على الطالباتِ.\n"
            "الطالباتِ: اسم مجرور بالكسرة."
        ),
    },

}


# ============================================================
# Helpers
# ============================================================

async def safe_answer(q):

    try:
        await q.answer()

    except Exception:
        pass


async def send_long_message( message, text, reply_markup=None, ):

    if not text:
        return

    max_len = 3900

    if len(text) <= max_len:

        await message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
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
            parse_mode="Markdown",
        )

        first = False


# ============================================================
# Access / Subscription
# ============================================================

async def check_access( update, context, ):

    user = update.effective_user

    if not user:
        return False

    try:

        db.upsert_user(
            user.id,
            user.full_name,
            user.username,
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
# Outfit
# ============================================================

def outfit_gender_markup():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🖤 For Him",
                    callback_data="outfit:him",
                ),
                InlineKeyboardButton(
                    "🤍 For Her",
                    callback_data="outfit:her",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية",
                    callback_data="m",
                ),
            ],
        ]
    )


def outfit_menu_markup(gender):

    title = (
        "🖤 For Him"
        if gender == "him"
        else "🤍 For Her"
    )

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"{title} — Casual",
                    callback_data=f"outfit:style:{gender}:casual",
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{title} — Formal",
                    callback_data=f"outfit:style:{gender}:formal",
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{title} — Sport",
                    callback_data=f"outfit:style:{gender}:sport",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 رجوع",
                    callback_data="outfit",
                ),
            ],
        ]
    )


def outfit_style_markup(gender, style):

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✨ توليد إطلالة",
                    callback_data=f"outfit:generate:{gender}:{style}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 رجوع",
                    callback_data=f"outfit:{gender}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية",
                    callback_data="m",
                ),
            ],
        ]
    )


def _safe_user_text(update):

    user = update.effective_user

    if not user:
        return ""

    return (
        f"المستخدم: {user.full_name}\n"
        f"المعرف: @{user.username or 'بدون معرف'}\n"
        f"ID: {user.id}"
    )


def outfit_prompt(gender, style):

    gender_text = (
        "رجل"
        if gender == "him"
        else "امرأة"
    )

    style_text = {
        "casual": "كاجوال",
        "formal": "رسمي",
        "sport": "رياضي",
    }.get(style, "كاجوال")

    return (
        "أنت خبير أزياء. "
        f"اقترح إطلالة {style_text} مناسبة لـ {gender_text}. "
        "اذكر القطع والألوان والتنسيق بصورة مختصرة وعملية. "
        "اكتب بالعربية."
    )


async def generate_outfit(gender, style):

    if not GEMINI_API_KEY:
        return (
            "❌ مفتاح Gemini غير موجود.\n\n"
            "أضف GEMINI_API_KEY إلى متغيرات البيئة."
        )

    prompt = outfit_prompt(
        gender,
        style,
    )

    try:

        async with httpx.AsyncClient(
            timeout=60.0,
        ) as client:

            response = await client.post(
                (
                    "https://generativelanguage.googleapis.com/"
                    "v1beta/models/"
                    f"{OUTFIT_MODEL}:generateContent"
                ),
                params={
                    "key": GEMINI_API_KEY,
                },
                json={
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": prompt,
                                }
                            ]
                        }
                    ],
                },
            )

            response.raise_for_status()

            data = response.json()

            try:

                parts = (
                    data["candidates"][0]
                    ["content"]["parts"]
                )

                text = "".join(
                    part.get("text", "")
                    for part in parts
                ).strip()

            except Exception:

                text = ""

            if text:
                return text

    except Exception:

        logger.exception(
            "Outfit generation failed."
        )

    return (
        "❌ تعذر توليد الإطلالة حالياً.\n"
        "حاول مرة ثانية."
    )


async def outfit_start(update, context):

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
        "👕 <b>من تختار؟</b>",
        outfit_gender_markup(),
    )


async def outfit_gender(update, context, gender):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    if gender not in {
        "him",
        "her",
    }:
        gender = "him"

    await show(
        q,
        "👕 <b>اختار نوع الإطلالة:</b>",
        outfit_menu_markup(gender),
    )


async def outfit_style(update, context, gender, style):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    if gender not in {
        "him",
        "her",
    }:
        gender = "him"

    if style not in {
        "casual",
        "formal",
        "sport",
    }:
        style = "casual"

    context.user_data[
        "outfit_gender"
    ] = gender

    context.user_data[
        "outfit_style"
    ] = style

    await show(
        q,
        (
            "👕 <b>الإطلالة جاهزة للإعداد</b>\n\n"
            "اضغط توليد حتى يحصل البوت على اقتراح مناسب."
        ),
        outfit_style_markup(
            gender,
            style,
        ),
    )


async def outfit_generate(update, context, gender, style):

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
        "⏳ جاري إعداد الإطلالة...",
    )

    result = await generate_outfit(
        gender,
        style,
    )

    await show(
        q,
        (
            "👕 <b>اقتراح الإطلالة</b>\n\n"
            f"{result}"
        ),
        outfit_style_markup(
            gender,
            style,
        ),
    )


# ============================================================
# Library Handlers
# ============================================================

async def library_start(update, context):

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
        (
            "📚 <b>مكتبة الكتب</b>\n\n"
            "أرسل اسم الكتاب أو المؤلف الذي تريد البحث عنه."
        ),
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data="m",
                    )
                ]
            ]
        ),
    )

    context.user_data[
        "waiting_library_query"
    ] = True


async def library_search(update, context):

    if not update.message:
        return

    if not context.user_data.get(
        "waiting_library_query"
    ):
        return

    if not await check_access(
        update,
        context,
    ):
        return

    query = (
        update.message.text
        or ""
    ).strip()

    if not query:
        await update.message.reply_text(
            "❌ اكتب اسم الكتاب أو المؤلف."
        )
        return

    context.user_data[
        "waiting_library_query"
    ] = False

    query = _LibraryModule._clean_query(
        query
    )

    noor = library.build_noor_search_url(
        query
    )

    shamela = library.build_shamela_search_url(
        query
    )

    text = (
        library.format_search_result(
            query
        )
        + "\n\n"
        f"🔗 <a href=\"{noor}\">البحث في مكتبة نور</a>\n"
        f"🔗 <a href=\"{shamela}\">البحث في المكتبة الشاملة</a>"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ============================================================
# Character Handlers
# ============================================================

async def character_start(update, context):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    context.user_data[
        "waiting_character"
    ] = True

    await show(
        q,
        (
            "🏺 <b>سير الأعلام</b>\n\n"
            "اكتب اسم الشخصية التي تريد معرفة سيرتها."
        ),
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data="m",
                    )
                ]
            ]
        ),
    )


async def character_search(update, context):

    if not update.message:
        return

    if not context.user_data.get(
        "waiting_character"
    ):
        return

    if not await check_access(
        update,
        context,
    ):
        return

    name = (
        update.message.text
        or ""
    ).strip()

    if not name:
        await update.message.reply_text(
            "❌ اكتب اسم الشخصية."
        )
        return

    context.user_data[
        "waiting_character"
    ] = False

    ok, result = await character.get_character(
        name
    )

    if not ok:
        await update.message.reply_text(
            result
        )
        return

    await update.message.reply_text(
        result,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📚 السيرة التفصيلية",
                        callback_data=f"character:detail:{name[:80]}",
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


async def character_detail(update, context, name):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    result = await character.get_character_detail(
        name
    )

    await show(
        q,
        result,
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 رجوع",
                        callback_data="character",
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
# Voice Handler
# ============================================================

async def transcribe_voice(file_path):

    if not GEMINI_API_KEY:
        return ""

    if not voice_client:
        return ""

    try:

        uploaded = await asyncio.to_thread(
            voice_client.files.upload,
            file=file_path,
        )

        response = await asyncio.to_thread(
            voice_client.models.generate_content,
            model=VOICE_MODEL,
            contents=[
                uploaded,
                (
                    "حوّل التسجيل الصوتي إلى نص عربي واضح. "
                    "اكتب النص فقط بدون شرح."
                ),
            ],
        )

        text = getattr(
            response,
            "text",
            "",
        )

        return (
            text.strip()
            if text
            else ""
        )

    except Exception:

        logger.exception(
            "Voice transcription failed."
        )

        return ""


async def handle_voice(update, context):

    message = update.message

    if not message or not message.voice:
        return

    if not await check_access(
        update,
        context,
    ):
        return

    temp_path = None

    try:

        voice = await message.voice.get_file()

        with tempfile.NamedTemporaryFile(
            suffix=".ogg",
            delete=False,
        ) as tmp:

            temp_path = tmp.name

        await voice.download_to_drive(
            custom_path=temp_path
        )

        await message.reply_text(
            "⏳ جاري تحويل التسجيل إلى نص..."
        )

        text = await transcribe_voice(
            temp_path
        )

        if not text:

            await message.reply_text(
                "❌ ما قدرت أستخرج النص من التسجيل."
            )

            return

        context.user_data[
            "ai_text"
        ] = text

        await message.reply_text(
            (
                "🎙️ <b>النص المستخرج:</b>\n\n"
                f"{text}\n\n"
                "اختر نوع التحليل:"
            ),
            parse_mode="HTML",
            reply_markup=ai_markup(),
        )

    except Exception:

        logger.exception(
            "Voice handler failed."
        )

        await message.reply_text(
            "❌ صار خطأ أثناء معالجة التسجيل."
        )

    finally:

        if temp_path:

            try:
                os.remove(
                    temp_path
                )
            except Exception:
                pass


# ============================================================
# Image OCR Handler
# ============================================================

async def analyze_image(file_path):

    if not GEMINI_API_KEY:
        return ""

    if not image_client:
        return ""

    try:

        uploaded = await asyncio.to_thread(
            image_client.files.upload,
            file=file_path,
        )

        response = await asyncio.to_thread(
            image_client.models.generate_content,
            model=IMAGE_MODEL,
            contents=[
                uploaded,
                (
                    "استخرج النص الموجود في الصورة "
                    "بدقة، وحافظ على علامات الترقيم "
                    "والحركات إن كانت واضحة. "
                    "أخرج النص فقط."
                ),
            ],
        )

        text = getattr(
            response,
            "text",
            "",
        )

        return (
            text.strip()
            if text
            else ""
        )

    except Exception:

        logger.exception(
            "Image OCR failed."
        )

        return ""


async def handle_photo(update, context):

    message = update.message

    if not message or not message.photo:
        return

    if not await check_access(
        update,
        context,
    ):
        return

    temp_path = None

    try:

        photo = message.photo[-1]

        file = await photo.get_file()

        with tempfile.NamedTemporaryFile(
            suffix=".jpg",
            delete=False,
        ) as tmp:

            temp_path = tmp.name

        await file.download_to_drive(
            custom_path=temp_path
        )

        await message.reply_text(
            "⏳ جاري قراءة النص من الصورة..."
        )

        text = await analyze_image(
            temp_path
        )

        if not text:

            await message.reply_text(
                "❌ ما قدرت أقرأ النص من الصورة."
            )

            return

        context.user_data[
            "ai_text"
        ] = text

        await message.reply_text(
            (
                "🖼️ <b>النص المستخرج:</b>\n\n"
                f"{text}\n\n"
                "اختر نوع التحليل:"
            ),
            parse_mode="HTML",
            reply_markup=ai_markup(),
        )

    except Exception:

        logger.exception(
            "Photo handler failed."
        )

        await message.reply_text(
            "❌ صار خطأ أثناء معالجة الصورة."
        )

    finally:

        if temp_path:

            try:
                os.remove(
                    temp_path
                )
            except Exception:
                pass


# ============================================================
# Text Handler
# ============================================================

async def handle_text(update, context):

    message = update.message

    if not message:
        return

    if not message.text:
        return

    text = message.text.strip()

    if not text:
        return

    # Library input
    if context.user_data.get(
        "waiting_library_query"
    ):
        await library_search(
            update,
            context,
        )
        return

    # Character input
    if context.user_data.get(
        "waiting_character"
    ):
        await character_search(
            update,
            context,
        )
        return

    # Save text for AI
    context.user_data[
        "ai_text"
    ] = text

    if not await check_access(
        update,
        context,
    ):
        return

    await message.reply_text(
        (
            "📝 <b>تم استلام النص.</b>\n\n"
            "اختار شنو تريد أسوي بالنص:"
        ),
        parse_mode="HTML",
        reply_markup=ai_markup(),
    )


# ============================================================
# Start
# ============================================================

async def start(update, context):

    if not update.message:
        return

    user = update.effective_user

    if user:

        try:

            db.upsert_user(
                user.id,
                user.full_name,
                user.username,
            )

        except Exception:

            logger.exception(
                "Failed to save start user."
            )

    if not await check_access(
        update,
        context,
    ):
        return

    await update.message.reply_text(
        (
            "👋 أهلاً وسهلاً بك\n\n"
            "📚 هذا البوت مخصص لخدمة اللغة العربية "
            "والدراسة والتحليل.\n\n"
            "اختر من القائمة:"
        ),
        reply_markup=main_menu(
            user.id
            if user
            else 0
        ),
    )


# ============================================================
# Cancel
# ============================================================

async def cancel(update, context):

    context.user_data.pop(
        "waiting_library_query",
        None,
    )

    context.user_data.pop(
        "waiting_character",
        None,
    )

    context.user_data.pop(
        "ai_text",
        None,
    )

    if update.message:

        await update.message.reply_text(
            "تم الإلغاء.",
            reply_markup=main_menu(
                update.effective_user.id
            ),
        )


# ============================================================
# Callback Router
# ============================================================

async def callback_router(update, context):

    q = update.callback_query

    if not q:
        return

    data = q.data or ""

    if data == "m":

        await safe_answer(q)

        if not await check_access(
            update,
            context,
        ):
            return

        await show(
            q,
            "🏠 <b>القائمة الرئيسية</b>",
            main_menu(
                q.from_user.id
            ),
        )

        return

    if data == "library":

        await library_start(
            update,
            context,
        )

        return

    if data == "character":

        await character_start(
            update,
            context,
        )

        return

    if data.startswith(
        "character:detail:"
    ):

        name = data.split(
            "character:detail:",
            1,
        )[1]

        await character_detail(
            update,
            context,
            name,
        )

        return

    if data == "outfit":

        await outfit_start(
            update,
            context,
        )

        return

    if data.startswith(
        "outfit:"
    ):

        parts = data.split(":")

        if len(parts) == 2:

            await outfit_gender(
                update,
                context,
                parts[1],
            )

            return

        if len(parts) == 4:

            action = parts[1]
            gender = parts[2]
            style = parts[3]

            if action == "style":

                await outfit_style(
                    update,
                    context,
                    gender,
                    style,
                )

                return

            if action == "generate":

                await outfit_generate(
                    update,
                    context,
                    gender,
                    style,
                )

                return

    if data.startswith(
        "ai:"
    ):

        mode = data.split(
            "ai:",
            1,
        )[1]

        await handle_ai(
            update,
            context,
            mode,
        )

        return

    await safe_answer(q)


# ============================================================
# Application
# ============================================================

def build_application():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is not configured."
        )

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            callback_router,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.VOICE,
            handle_voice,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text,
        )
    )

    return application


# ============================================================
# Main
# ============================================================

def main():

    logger.info(
        "Starting Telegram bot..."
    )

    application = build_application()

    application.run_polling(
        drop_pending_updates=True,
    )


if __name__ == "__main__":

    main()
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

def _extract_text_from_image_file( file_path, mime_type, ):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY غير موجود."
        )

    if image_client is None:

        raise RuntimeError(
            "تعذر إنشاء اتصال Gemini للصور."
        )

    prompt = """ استخرج النص الموجود داخل الصورة فقط. مهم جداً: - الصورة قد تحتوي على نص عربي أو إنكليزي أو الاثنين معاً. - حافظ على الكلمات كما تظهر في الصورة قدر الإمكان. - لا تشرح الصورة. - لا تلخص. - لا تضف أي كلام من عندك. - لا تضع مقدمة مثل "النص هو". - إذا كان هناك أكثر من سطر، حافظ على ترتيب الأسطر. - إذا كانت هناك أسئلة أو أبيات أو جمل، اكتبها كما تظهر. - إذا كانت هناك كلمات غير واضحة، حاول قراءتها من السياق، وإذا تعذر ذلك اتركها كما تبدو بدلاً من اختراع كلمة. - أعد النص المستخرج فقط. """

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


async def extract_text_from_image( file_path, mime_type, ):

    return await asyncio.to_thread(
        _extract_text_from_image_file,
        file_path,
        mime_type,
    )


# ============================================================
# Image Handler
# ============================================================

async def handle_image( update: Update, context: ContextTypes.DEFAULT_TYPE, ):

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

        if photo:

            telegram_file = await context.bot.get_file(
                photo[-1].file_id
            )

            suffix = ".jpg"
            mime_type = "image/jpeg"

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

        context.user_data[
            "ai_text"
        ] = text

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

    prompt = """ أنت مولّد أسئلة لتحدي قواعد اللغة العربية للطلاب. أنشئ سؤال قواعد عربية واحد فقط. الشروط: - السؤال يجب أن يكون واضحاً ومناسباً للطالب. - استخدم قواعد عربية مدرسية صحيحة. - اجعل السؤال متوسط الصعوبة. - يجب أن يحتوي على 4 خيارات فقط. - خيار واحد فقط صحيح. - لا تجعل أكثر من خيار صحيحاً. - لا تستخدم معلومات غامضة أو خلافية. - بعد السؤال، اكتب شرحاً قصيراً جداً لسبب صحة الإجابة. أمثلة لأنواع الأسئلة: - تحديد المفعول به. - تحديد الفاعل. - تحديد المبتدأ والخبر. - علامة الإعراب. - نوع الجملة. - كان وأخواتها. - إن وأخواتها. - النعت. - الحال. - التمييز. - المفعول المطلق. - المفعول لأجله. - جمع المذكر السالم. - المثنى. - الأسماء الخمسة. أعد النتيجة بصيغة JSON فقط، بدون أي كلام خارج JSON. الشكل المطلوب بالضبط: { "question": "السؤال هنا", "options": [ "الخيار الأول", "الخيار الثاني", "الخيار الثالث", "الخيار الرابع" ], "correct": 0, "explanation": "شرح مختصر." } مهم: - correct يجب أن يكون رقماً من 0 إلى 3. - options يجب أن تحتوي على 4 عناصر بالضبط. - لا تستخدم Markdown. - لا تضع ```json. """

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

async def send_grammar_challenge_question( q, context, first=False, ):

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

async def start_grammar_challenge( update, context, ):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

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

async def handle_grammar_challenge_answer( update, context, answer_index, ):

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

    await q.edit_message_text(

        result_text
        + "\n\n"
        + f"📊 النتيجة الحالية: "
        + f"{challenge.get('correct_count', 0)}/"
        + f"{number}\n\n"
        + "⏳ جاري تجهيز السؤال التالي...",

        parse_mode="Markdown",

    )

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

async def cancel_grammar_challenge( update, context, ):

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
# شرح قواعد اللغة العربية
# ============================================================

def rules_menu_markup():

    rows = []

    items = list(ARABIC_RULES.items())

    for i in range(0, len(items), 2):

        row = []

        for key, rule in items[i:i + 2]:

            row.append(
                InlineKeyboardButton(
                    rule["title"],
                    callback_data=f"rule:{key}",
                )
            )

        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                "🎲 قاعدة عشوائية",
                callback_data="rule:random",
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                "🏠 القائمة الرئيسية",
                callback_data="m",
            )
        ]
    )

    return InlineKeyboardMarkup(rows)


async def show_rules_menu( update, context, ):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    await q.edit_message_text(

        "📚 **شرح قواعد اللغة العربية**\n\n"
        "اختر القاعدة التي تريد شرحها:\n\n"
        "يمكنك دراسة القاعدة ثم الانتقال إلى "
        "🧠 تحدي قواعد اللغة العربية للتدريب.",

        parse_mode="Markdown",

        reply_markup=rules_menu_markup(),

    )


async def show_rule( update, context, key, ):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    if key == "random":

        import random

        key = random.choice(
            list(ARABIC_RULES.keys())
        )

    rule = ARABIC_RULES.get(key)

    if not rule:

        await q.edit_message_text(

            "❌ هذه القاعدة غير موجودة.",

            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📚 قواعد اللغة",
                            callback_data="rules",
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

    await q.edit_message_text(

        rule["text"],

        parse_mode="Markdown",

        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📚 كل القواعد",
                        callback_data="rules",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🧠 تحدي قواعد اللغة",
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
# Weather - Kirkuk
# ============================================================

async def show_weather( update, context, ):

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
        "🌤️ طقس كركوك\n\n"
        "⏳ جاري جلب حالة الطقس...",
    )

    try:
               data = await weather.get_weather()

        text = weather.format_weather(data)

        await show(
            q,
            text,
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 تحديث الطقس",
                            callback_data="weather",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 القائمة الرئيسية",
                            callback_data="m"
                        )
                    ],
                ]
            ),
        )

    except Exception:

        logger.exception(
            "Weather request failed."
        )

        await show(
            q,
            "❌ تعذر جلب طقس كركوك حالياً.\n\n"
            "حاول مرة ثانية بعد قليل.",
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 إعادة المحاولة",
                            callback_data="weather",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 القائمة الرئيسية",
                            callback_data="m"
                        )
                    ],
                ]
            ),
        )


# ============================================================
# Start
# ============================================================

async def start( update: Update, context: ContextTypes.DEFAULT_TYPE, ):

    user = update.effective_user

    if not user:
        return

    try:

        db.upsert_user(
            user.id,
            user.full_name,
            user.username,
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

    context.user_data.pop(
        "outfit_await",
        None,
    )

    context.user_data.pop(
        "library_await",
        None,
    )

    context.user_data.pop(
        "character_await",
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

async def cancel( update: Update, context: ContextTypes.DEFAULT_TYPE, ):

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

    context.user_data.pop(
        "outfit_await",
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

async def verify_subscription( q, context, ):

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

async def show_main_menu( update, context, ):

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

async def handle_ai( update, context, mode, ):

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

async def handle_text( update: Update, context: ContextTypes.DEFAULT_TYPE, ):

    if not update.message:
        return

    if not await check_access(
        update,
        context,
    ):
        return

    text = (
        update.message.text or ""
    ).strip()

    if not text:
        return

    # --------------------------------------------------------
    # Book Library text input
    # --------------------------------------------------------

    if context.user_data.get("library_await"):

        context.user_data.pop("library_await", None)

        query = text

        await update.message.reply_text(
            library.format_search_result(query),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📖 البحث في مكتبة نور",
                        url=library.build_noor_search_url(query),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📚 البحث في المكتبة الشاملة",
                        url=library.build_shamela_search_url(query),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔎 بحث عن كتاب آخر",
                        callback_data="library",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🏠 القائمة الرئيسية",
                        callback_data="m",
                    ),
                ],
            ]),
        )

        return

    # --------------------------------------------------------
    # Character Biography text input
    # --------------------------------------------------------

    if context.user_data.get("character_await"):

        context.user_data.pop("character_await", None)

        await update.message.reply_text(
            "⏳ جاري إعداد نبذة عن الشخصية..."
        )

        ok, result = await character.get_character(text)

        context.user_data["character_name"] = text[:150]

        buttons = [
            [
                InlineKeyboardButton(
                    "📚 حياته وآثاره",
                    callback_data="character:detail",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔎 بحث عن شخصية أخرى",
                    callback_data="character",
                ),
                InlineKeyboardButton(
                    "📖 الكتب",
                    callback_data="library",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏠 القائمة الرئيسية",
                    callback_data="m",
                ),
            ],
        ]

        await update.message.reply_text(
            result,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

        return

    # --------------------------------------------------------
    # Outfit text input
    # --------------------------------------------------------

    if context.user_data.get(
        "outfit_await"
    ):

        handled = await outfit_save_text(
            update,
            context,
            text,
        )

        if handled:
            return

    # --------------------------------------------------------
    # Existing await handlers
    # --------------------------------------------------------

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

async def handle_document( update: Update, context: ContextTypes.DEFAULT_TYPE, ):

    if not update.message:
        return

    if not await check_access(
        update,
        context,
    ):
        return

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

async def callback_router( update: Update, context: ContextTypes.DEFAULT_TYPE, ):

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
    # Arabic Grammar Rules
    # ========================================================

    if data == "rules":

        return await show_rules_menu(
            update,
            context,
        )

    if data.startswith("rule:"):

        key = data.split(
            ":",
            1
        )[1]

        return await show_rule(
            update,
            context,
            key,
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
    # Weather - Kirkuk
    # ========================================================

    if data == "weather":

        return await show_weather(
            update,
            context,
        )

    # ========================================================
    # Book Library
    # ========================================================

    if data == "library":

        await safe_answer(q)
        context.user_data["library_await"] = True

        return await show(
            q,
            "📚 مكتبة الكتب\n\n"
            "اكتب اسم الكتاب أو اسم المؤلف، وسأجهز لك روابط البحث في المكتبة الشاملة ومكتبة نور.\n\n"
            "📌 إذا كانت هناك نسخة PDF متاحة قانونياً من المصدر، استخدم رابط التحميل الذي يتيحه المصدر.",
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ إلغاء",
                        callback_data="m"
                    ),
                ],
            ]),
        )

    # ========================================================
    # Character Biography - Detailed Life
    # ========================================================

    if data == "character:detail":

        await safe_answer(q)

        name = str(
            context.user_data.get(
                "character_name",
                ""
            )
        ).strip()

        if not name:

            return await show(
                q,
                "❌ لم أتمكن من تحديد اسم الشخصية.",
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ رجوع",
                            callback_data="character"
                        )
                    ],
                ]),
            )

        await show(
            q,
            "📚 حياته وآثاره\n\n"
            "⏳ جاري إعداد السيرة التفصيلية...",
        )

        ok, result = await character.get_character_detail(
            name
        )

        buttons = [
            [
                InlineKeyboardButton(
                    "🔄 إعادة التفاصيل",
                    callback_data="character:detail",
                ),
                InlineKeyboardButton(
                    "🔎 شخصية أخرى",
                    callback_data="character",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📖 الكتب",
                    callback_data="library",
                ),
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="m",
                ),
            ],
        ]

        return await show(
            q,
            result,
            InlineKeyboardMarkup(buttons),
        )

    # ========================================================
    # Character Biography
    # ========================================================

    if data == "character":

        await safe_answer(q)
        context.user_data["character_await"] = True

        return await show(
            q,
            "🏺 سير الأعلام\n\n"
            "اكتب اسم الشخصية، وسأعرض لك نبذة موثقة قدر الإمكان عن حياتها ومكانتها وآثارها.\n\n"
            "بعد ظهور النبذة ستجد زر 📚 حياته وآثاره للتوسع في السيرة.",
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ إلغاء",
                        callback_data="m"
                    ),
                ],
            ]),
        )

    # ========================================================
    # Outfit
    # ========================================================

    if data == "outfit":

        return await show_outfit(
            update,
            context,
        )

    if data == "outfit:him":

        return await show_outfit_gender(
            update,
            context,
            "him",
        )

    if data == "outfit:her":

        return await show_outfit_gender(
            update,
            context,
            "her",
        )

    if data.startswith("outfit:add:"):

        gender = data.split(
            ":",
            2
        )[2]

        return await outfit_add_start(
            update,
            context,
            gender,
        )

    if data.startswith("outfit:list:"):

        gender = data.split(
            ":",
            2
        )[2]

        return await outfit_list(
            update,
            context,
            gender,
        )

    if data.startswith("outfit:manage:"):

        gender = data.split(
            ":",
            2
        )[2]

        return await outfit_manage(
            update,
            context,
            gender,
        )

    if data.startswith("outfit:delete_menu:"):

        gender = data.split(
            ":",
            2
        )[2]

        return await outfit_delete_menu(
            update,
            context,
            gender,
        )

    if data.startswith("outfit:delete:"):

        parts = data.split(":")

        if len(parts) != 4:
            return

        try:

            item_id = int(
                parts[2]
            )

        except ValueError:

            return

        gender = parts[3]

        return await outfit_delete(
            update,
            context,
            item_id,
            gender,
        )

    if data.startswith("outfit:clear_yes:"):

        gender = data.split(
            ":",
            2
        )[2]

        return await outfit_clear_yes(
            update,
            context,
            gender,
        )

    if data.startswith("outfit:clear:"):

        gender = data.split(
            ":",
            2
        )[2]

        return await outfit_clear(
            update,
            context,
            gender,
        )

    if data.startswith("outfit:generate:"):

        gender = data.split(
            ":",
            2
        )[2]

        return await outfit_generate(
            update,
            context,
            gender,
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
    # Admin - Users
    # ========================================================

    if data == "users":

        await safe_answer(q)

        if not is_admin(
            q.from_user.id
        ):
            return

        return await admin.router(
            q,
            context,
            "users",
            "",
        )

    if data.startswith("userspage:"):

        await safe_answer(q)

        if not is_admin(
            q.from_user.id
        ):
            return

        return await admin.router(
            q,
            context,
            "userspage",
            data.split(
                ":",
                1
            )[1],
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

async def error_handler( update, context, ):

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
