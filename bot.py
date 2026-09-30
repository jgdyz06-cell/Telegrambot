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

    except Exception:

        voice_client = None


    # --------------------------------------------------------
    # Image client
    # --------------------------------------------------------

    try:

        if types is not None:

            image_client = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options=types.HttpOptions(
                    api_version="v1beta",
                    timeout=60000,
                ),
            )

        else:

            image_client = genai.Client(
                api_key=GEMINI_API_KEY,
            )

    except Exception:

        image_client = None

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
            "📚 المبتدأ والخبر\n\n"
            "🔹 التعريف:\n"
            "المبتدأ اسم مرفوع يأتي غالباً في بداية الجملة الاسمية، "
            "والخبر هو الجزء الذي يتمم معنى الجملة ويخبر عن المبتدأ.\n\n"

            "🔹 القاعدة:\n"
            "المبتدأ مرفوع، والخبر مرفوع.\n\n"

            "🔹 مثال:\n"
            "العلمُ نافعٌ.\n\n"

            "العلمُ: مبتدأ مرفوع وعلامة رفعه الضمة.\n"
            "نافعٌ: خبر مرفوع وعلامة رفعه الضمة.\n\n"

            "🔹 مثال آخر:\n"
            "الطلابُ مجتهدون.\n\n"

            "الطلابُ: مبتدأ مرفوع.\n"
            "مجتهدون: خبر مرفوع بالواو لأنه جمع مذكر سالم.\n\n"
        ),
    },

    "kana": {
        "title": "📌 كان وأخواتها",
        "text": (
            "📚 كان وأخواتها\n\n"
            "🔹 التعريف:\n"
            "أفعال ناسخة تدخل على الجملة الاسمية، فترفع المبتدأ ويسمى اسمها، "
            "وتنصب الخبر ويسمى خبرها.\n\n"

            "🔹 مثال:\n"
            "كانَ الجوُّ معتدلاً.\n\n"

            "الجوُّ: اسم كان مرفوع.\n"
            "معتدلاً: خبر كان منصوب.\n\n"
        ),
    },

    "inna": {
        "title": "📌 إن وأخواتها",
        "text": (
            "📚 إن وأخواتها\n\n"
            "🔹 التعريف:\n"
            "حروف ناسخة تدخل على الجملة الاسمية، فتنصب المبتدأ ويسمى اسمها، "
            "وترفع الخبر ويسمى خبرها.\n\n"

            "🔹 مثال:\n"
            "إنَّ العلمَ نافعٌ.\n\n"

            "العلمَ: اسم إن منصوب.\n"
            "نافعٌ: خبر إن مرفوع.\n\n"
        ),
    },

    "fa3il": {
        "title": "📌 الفاعل",
        "text": (
            "📚 الفاعل\n\n"
            "🔹 التعريف:\n"
            "اسم مرفوع يدل على من قام بالفعل أو اتصف به.\n\n"

            "🔹 مثال:\n"
            "كتبَ الطالبُ الدرسَ.\n\n"

            "الطالبُ: فاعل مرفوع وعلامة رفعه الضمة.\n\n"
        ),
    },

    "maf3ool": {
        "title": "📌 المفعول به",
        "text": (
            "📚 المفعول به\n\n"
            "🔹 التعريف:\n"
            "اسم منصوب وقع عليه فعل الفاعل.\n\n"

"🔹 مثال:\n"
            "قرأَ الطالبُ الكتابَ.\n\n"

            "الكتابَ: مفعول به منصوب وعلامة نصبه الفتحة.\n\n"
        ),
    },

}

"naat": {
        "title": "🟡 النعت",
        "text": (
            "📚 النعت (الصفة)\n\n"
            "🔹 التعريف:\n"
            "النعت كلمة تصف اسماً قبلها يسمى المنعوت.\n\n"

            "🔹 القاعدة المهمة:\n"
            "النعت يتبع المنعوت في:\n"
            "1. الإعراب.\n"
            "2. التعريف والتنكير.\n"
            "3. التذكير والتأنيث.\n"
            "4. الإفراد والتثنية والجمع.\n\n"

            "🔹 مثال:\n"
            "جاءَ الطالبُ المجتهدُ.\n\n"

            "الطالبُ: منعوت مرفوع.\n"
            "المجتهدُ: نعت مرفوع.\n\n"

            "🔹 مثال منصوب:\n"
            "رأيتُ الطالبَ المجتهدَ.\n\n"

            "الطالبَ: مفعول به منصوب.\n"
            "المجتهدَ: نعت منصوب."
        ),
    },

    "hal": {
        "title": "🟤 الحال",
        "text": (
            "📚 الحال\n\n"
            "🔹 التعريف:\n"
            "الحال اسم نكرة يبين هيئة صاحبه وقت حدوث الفعل.\n\n"

            "🔹 القاعدة:\n"
            "الحال منصوب غالباً.\n\n"

            "🔹 مثال:\n"
            "جاءَ الطالبُ مسروراً.\n\n"

            "الطالبُ: فاعل مرفوع.\n"
            "مسروراً: حال منصوب.\n\n"

            "🔹 طريقة اكتشافه:\n"
            "اسأل: كيف حدث الفعل؟\n\n"

            "مثال:\n"
            "عادَ المسافرُ متعباً.\n"
            "كيف عادَ المسافر؟\n"
            "متعباً."
        ),
    },

    "tamyiz": {
        "title": "🟢 التمييز",
        "text": (
            "📚 التمييز\n\n"
            "🔹 التعريف:\n"
            "اسم نكرة يوضح كلمة أو جملة مبهمة قبله.\n\n"

            "🔹 القاعدة:\n"
            "التمييز يكون منصوباً غالباً.\n\n"

            "🔹 مثال:\n"
            "اشتريتُ كيلوغراماً تفاحاً.\n\n"

            "تفاحاً: تمييز منصوب.\n\n"

            "🔹 مثال آخر:\n"
            "ازدادَ الطالبُ علماً.\n\n"

            "علماً: تمييز منصوب."
        ),
    },

    "mudaf": {
        "title": "🔵 المضاف والمضاف إليه",
        "text": (
            "📚 المضاف والمضاف إليه\n\n"
            "🔹 التعريف:\n"
            "المضاف اسم يأتي قبل اسم آخر، والمضاف إليه اسم يأتي بعده ويكون مجروراً.\n\n"

            "🔹 القاعدة:\n"
            "المضاف إليه مجرور دائماً.\n\n"

            "🔹 مثال:\n"
            "كتابُ الطالبِ جديدٌ.\n\n"

            "كتابُ: مضاف.\n"
            "الطالبِ: مضاف إليه مجرور.\n\n"

            "💡 ملاحظة:\n"
            "المضاف لا يأخذ التنوين."
        ),
    },

    "jar": {
        "title": "🟣 حروف الجر",
        "text": (
            "📚 حروف الجر\n\n"
            "🔹 من أشهر حروف الجر:\n"
            "من، إلى، عن، على، في، الباء، الكاف، اللام.\n\n"

            "🔹 القاعدة:\n"
            "الاسم الذي يأتي بعد حرف الجر يكون مجروراً.\n\n"

            "🔹 مثال:\n"
            "ذهبتُ إلى المدرسةِ.\n\n"

            "المدرسةِ: اسم مجرور بإلى وعلامة جره الكسرة.\n\n"

            "🔹 مثال آخر:\n"
            "جلستُ في البيتِ.\n\n"

            "البيتِ: اسم مجرور بفي."
        ),
    },

    "future": {
        "title": "🟠 أدوات نصب المضارع",
        "text": (
            "📚 أدوات نصب الفعل المضارع\n\n"
            "من أشهرها: أن، لن، كي، حتى.\n\n"

            "🔹 مثال:\n"
            "لن أهملَ دروسي.\n\n"

            "أهملَ: فعل مضارع منصوب بلن.\n\n"

            "🔹 مثال:\n"
            "أدرسُ كي أنجحَ.\n\n"

            "أنجحَ: فعل مضارع منصوب بكي."
        ),
    },

    "jazm": {
        "title": "🔴 أدوات جزم المضارع",
        "text": (
            "📚 أدوات جزم الفعل المضارع\n\n"
            "من أشهرها: لم، لما، لا الناهية، لام الأمر.\n\n"

            "🔹 مثال:\n"
            "لم يذهبْ الطالبُ.\n\n"

            "يذهبْ: فعل مضارع مجزوم بلم وعلامة جزمه السكون.\n\n"

            "🔹 مثال:\n"
            "لا تهملْ دروسك.\n\n"

            "تهملْ: فعل مضارع مجزوم بلا الناهية."
        ),
    },

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

if name == "main":

    main()
