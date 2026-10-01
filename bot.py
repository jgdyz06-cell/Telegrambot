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

            "💡 ملاحظة:\n"
            "الجملة الاسمية الأساسية تتكون غالباً من مبتدأ وخبر."
        ),
    },

    "kana": {
        "title": "🔵 كان وأخواتها",
        "text": (
            "📚 كان وأخواتها\n\n"
            "🔹 التعريف:\n"
            "أفعال ناسخة تدخل على الجملة الاسمية، فترفع المبتدأ "
            "ويسمى اسمها، وتنصب الخبر ويسمى خبرها.\n\n"

            "🔹 من أخوات كان:\n"
            "كان، أصبح، أمسى، أضحى، ظل، بات، صار، ليس، "
            "ما زال، ما دام.\n\n"

            "🔹 القاعدة:\n"
            "اسم كان وأخواتها: مرفوع.\n"
            "خبر كان وأخواتها: منصوب.\n\n"

            "🔹 مثال:\n"
            "كانَ الجوُّ جميلاً.\n\n"

            "الجوُّ: اسم كان مرفوع.\n"
            "جميلاً: خبر كان منصوب.\n\n"

            "💡 احفظها:\n"
            "كان وأخواتها = ترفع الأول وتنصب الثاني."
        ),
    },

    "inna": {
        "title": "🟢 إن وأخواتها",
        "text": (
            "📚 إن وأخواتها\n\n"
            "🔹 التعريف:\n"
            "حروف ناسخة تدخل على الجملة الاسمية، فتنصب المبتدأ "
            "ويسمى اسمها، وترفع الخبر ويسمى خبرها.\n\n"

            "🔹 من أخوات إن:\n"
            "إنَّ، أنَّ، كأنَّ، لكنَّ، ليتَ، لعلَّ.\n\n"

            "🔹 القاعدة:\n"
            "اسم إن وأخواتها: منصوب.\n"
            "خبر إن وأخواتها: مرفوع.\n\n"

            "🔹 مثال:\n"
            "إنَّ الطالبَ مجتهدٌ.\n\n"

            "الطالبَ: اسم إن منصوب.\n"
            "مجتهدٌ: خبر إن مرفوع.\n\n"

"💡 احفظها:\n"
            "إن وأخواتها = تنصب الأول وترفع الثاني."
        ),
    },

    "fael": {
        "title": "🔴 الفاعل",
        "text": (
            "📚 الفاعل\n\n"
            "🔹 التعريف:\n"
            "الفاعل هو الاسم الذي قام بالفعل أو اتصف به.\n\n"

            "🔹 القاعدة:\n"
            "الفاعل مرفوع دائماً.\n\n"

            "🔹 مثال:\n"
            "كتبَ الطالبُ الدرسَ.\n\n"

            "الطالبُ: فاعل مرفوع وعلامة رفعه الضمة.\n\n"

            "🔹 مثال آخر:\n"
            "نجحَ الطالبانِ.\n\n"

            "الطالبانِ: فاعل مرفوع وعلامة رفعه الألف لأنه مثنى.\n\n"

            "💡 طريقة اكتشافه:\n"
            "اسأل: من الذي قام بالفعل؟"
        ),
    },

    "naeb": {
        "title": "🟠 نائب الفاعل",
        "text": (
            "📚 نائب الفاعل\n\n"
            "🔹 التعريف:\n"
            "اسم يأتي بعد الفعل المبني للمجهول، ويحل محل الفاعل المحذوف.\n\n"

            "🔹 القاعدة:\n"
            "نائب الفاعل مرفوع دائماً.\n\n"

            "🔹 مثال:\n"
            "كُتِبَ الدرسُ.\n\n"

            "الدرسُ: نائب فاعل مرفوع.\n\n"

            "🔹 مثال آخر:\n"
            "كُرِّمَ الطالبانِ.\n\n"

            "الطالبانِ: نائب فاعل مرفوع بالألف لأنه مثنى.\n\n"

            "💡 ملاحظة:\n"
            "عند بناء الفعل للمجهول يُحذف الفاعل ويأتي نائب الفاعل مكانه."
        ),
    },

    "mafool": {
        "title": "🟣 المفعول به",
        "text": (
            "📚 المفعول به\n\n"
            "🔹 التعريف:\n"
            "اسم يدل على من وقع عليه فعل الفاعل.\n\n"

            "🔹 القاعدة:\n"
            "المفعول به منصوب.\n\n"

            "🔹 مثال:\n"
            "قرأَ الطالبُ الكتابَ.\n\n"

            "الكتابَ: مفعول به منصوب وعلامة نصبه الفتحة.\n\n"

            "🔹 طريقة اكتشافه:\n"
            "اسأل: ماذا فعل الفاعل؟ أو وقع الفعل على ماذا؟\n\n"

            "💡 مثال:\n"
            "شربَ الطفلُ الماءَ.\n"
            "الماءَ هو الشيء الذي وقع عليه فعل الشرب."
        ),
    },

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
            "عادَ الطالبُ مسروراً.\n\n"

            "مسروراً: حال منصوب، يبين هيئة الطالب عند عودته.\n\n"

            "🔹 طريقة اكتشافه:\n"
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
            "📚 التمييز\n\n"
            "🔹 التعريف:\n"
            "اسم نكرة يوضح كلمة أو معنى مبهماً قبله.\n\n"

            "🔹 القاعدة:\n"
            "التمييز يكون منصوباً في كثير من استعمالاته.\n\n"

            "🔹 مثال:\n"
            "اشتريتُ عشرينَ كتاباً.\n\n"

            "كتاباً: تمييز منصوب.\n"
            "وهو يوضح المقصود بالعدد عشرين.\n\n"

            "🔹 مثال آخر:\n"
            "ازدادَ الطالبُ علماً.\n\n"

            "علماً: تمييز منصوب.\n\n"

            "💡 ملاحظة:\n"
            "التمييز يزيل الإبهام عن كلمة أو جملة قبله."
        ),
    },

"mafool_mutlaq": {
        "title": "🟦 المفعول المطلق",
        "text": (
            "📚 المفعول المطلق\n\n"
            "🔹 التعريف:\n"
            "مصدر منصوب يأتي من لفظ الفعل، ويستخدم للتوكيد "
            "أو بيان النوع أو العدد.\n\n"

            "🔹 أنواعه:\n"
            "1. مؤكد للفعل.\n"
            "2. مبين للنوع.\n"
            "3. مبين للعدد.\n\n"

            "🔹 مثال:\n"
            "نجحَ الطالبُ نجاحاً.\n\n"

            "نجاحاً: مفعول مطلق منصوب، مؤكد للفعل.\n\n"

            "🔹 مثال:\n"
            "سارَ الجنديُّ سيرَ الأبطالِ.\n\n"

            "سيرَ: مفعول مطلق مبين للنوع."
        ),
    },

    "mafool_liajlih": {
        "title": "🟥 المفعول لأجله",
        "text": (
            "📚 المفعول لأجله\n\n"
            "🔹 التعريف:\n"
            "مصدر منصوب يبين سبب حدوث الفعل.\n\n"

            "🔹 القاعدة:\n"
            "يجيب غالباً عن سؤال: لماذا؟\n\n"

            "🔹 مثال:\n"
            "درستُ طلباً للنجاح.\n\n"

            "طلباً: مفعول لأجله منصوب، لأنه يبين سبب الدراسة.\n\n"

            "🔹 مثال آخر:\n"
            "سافرتُ طلباً للعلم.\n\n"

            "طلباً: مفعول لأجله منصوب.\n\n"

            "💡 طريقة اكتشافه:\n"
            "اسأل: لماذا حدث الفعل؟"
        ),
    },

    "asmaa_khamsa": {
        "title": "🟪 الأسماء الخمسة",
        "text": (
            "📚 الأسماء الخمسة\n\n"
            "🔹 هي:\n"
            "أب، أخ، حم، فو، ذو.\n\n"

            "🔹 علامات إعرابها:\n"
            "ترفع بالواو.\n"
            "تنصب بالألف.\n"
            "تجر بالياء.\n\n"

            "🔹 مثال الرفع:\n"
            "جاءَ أبوك.\n"
            "أبوك: فاعل مرفوع بالواو.\n\n"

            "🔹 مثال النصب:\n"
            "رأيتُ أباك.\n"
            "أباك: مفعول به منصوب بالألف.\n\n"

            "🔹 مثال الجر:\n"
            "مررتُ بأبيك.\n"
            "أبيك: اسم مجرور بالياء.\n\n"

            "💡 ملاحظة:\n"
            "لها شروط خاصة حتى تعرب بالحروف."
        ),
    },

    "dual": {
        "title": "🟩 المثنى",
        "text": (
            "📚 المثنى\n\n"
            "🔹 التعريف:\n"
            "اسم يدل على اثنين أو اثنتين بزيادة ألف ونون "
            "أو ياء ونون في آخره.\n\n"

            "🔹 علامات الإعراب:\n"
            "يرفع بالألف.\n"
            "ينصب بالياء.\n"
            "يجر بالياء.\n\n"

            "🔹 مثال الرفع:\n"
            "جاءَ الطالبانِ.\n"
            "الطالبانِ: فاعل مرفوع بالألف.\n\n"

            "🔹 مثال النصب:\n"
            "رأيتُ الطالبينِ.\n"
            "الطالبينِ: مفعول به منصوب بالياء.\n\n"

            "🔹 مثال الجر:\n"
            "مررتُ بالطالبينِ.\n"
            "الطالبينِ: اسم مجرور بالياء."
        ),
    },

    "masculine_plural": {
        "title": "🟧 جمع المذكر السالم",
        "text": (
            "📚 جمع المذكر السالم\n\n"
            "🔹 التعريف:\n"
            "ما دل على أكثر من اثنين بزيادة واو ونون أو ياء ونون "
            "مع بقاء مفرده سالماً.\n\n"

            "🔹 علامات الإعراب:\n"
            "يرفع بالواو.\n"
            "ينصب بالياء.\n"
            "يجر بالياء.\n\n"

            "🔹 مثال الرفع:\n"
            "حضرَ المعلمونَ.\n"
            "المعلمونَ: فاعل مرفوع بالواو.\n\n"

            "🔹 مثال النصب:\n"
            "كرّمتُ المعلمينَ.\n"
            "المعلمينَ: مفعول به منصوب بالياء.\n\n"

            "🔹 مثال الجر:\n"
            "سلّمتُ على المعلمينَ.\n"
            "المعلمينَ: اسم مجرور بالياء."
        ),
    },

    "feminine_plural": {
        "title": "🟥 جمع المؤنث السالم",
        "text": (
            "📚 جمع المؤنث السالم\n\n"
            "🔹 التعريف:\n"
            "ما دل على أكثر من اثنتين بزيادة ألف وتاء على مفرده.\n\n"

            "🔹 علامات الإعراب:\n"
            "يرفع بالضمة.\n"
            "ينصب بالكسرة نيابة عن الفتحة.\n"
            "يجر بالكسرة.\n\n"

            "🔹 مثال الرفع:\n"
            "حضرتِ الطالباتُ.\n"
            "الطالباتُ: فاعل مرفوع بالضمة.\n\n"

"🔹 مثال النصب:\n"
            "رأيتُ الطالباتِ.\n"
            "الطالباتِ: مفعول به منصوب بالكسرة نيابة عن الفتحة.\n\n"

            "🔹 مثال الجر:\n"
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


async def check_access(update, context):

    user = update.effective_user

    if not user:
        return False

    user_id = user.id

    if is_admin(user_id):
        return True

    try:
        allowed = await is_subscribed(
            context.bot,
            user_id,
        )
    except Exception:
        logger.exception(
            "Subscription check failed."
        )
        allowed = False

    if allowed:
        return True

    if update.callback_query:
        target = update.callback_query.message
    else:
        target = update.message

    if target:
        await target.reply_text(
            SUB_TEXT,
            reply_markup=sub_markup(),
        )

    return False


def user_name(user):

    if not user:
        return "صديقي"

    if getattr(user, "first_name", None):
        return user.first_name

    if getattr(user, "username", None):
        return f"@{user.username}"

    return "صديقي"


def normalize_text(value):

    return " ".join(
        str(value or "").strip().split()
    )


def now_iraq():

    try:
        return dt.datetime.now(
            ZoneInfo("Asia/Baghdad")
        )

    except Exception:
        return dt.datetime.now()


def safe_int(value, default=0):

    try:
        return int(value)

    except Exception:
        return default


def safe_float(value, default=0.0):

    try:
        return float(value)

    except Exception:
        return default


def chunk_text(text, size=3900):

    text = str(text or "")

    if not text:
        return []

    return [
        text[i:i + size]
        for i in range(0, len(text), size)
    ]


# ============================================================
# Library Handler
# ============================================================

async def handle_library(update, context):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔎 بحث في نور",
                callback_data="library_noor",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔎 بحث في الشاملة",
                callback_data="library_shamela",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 رجوع",
                callback_data="back_main",
            ),
        ],
    ])

    await show(
        q,
        "📚 <b>مكتبة الكتب</b>\n\n"
        "اختر المصدر الذي تريد البحث فيه:",
        keyboard,
    )


async def handle_library_search(update, context, source):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

query = normalize_text(
        context.user_data.get(
            "library_query",
            "",
        )
    )

    if not query:

        await show(
            q,
            "❌ ما عندي كلمة بحث.\n\n"
            "أرسل اسم الكتاب أو المؤلف أولاً.",
            main_menu(
                q.from_user.id
            ),
        )

        return

    if source == "noor":

        url = library.build_noor_search_url(
            query
        )

        label = "نور"

    else:

        url = library.build_shamela_search_url(
            query
        )

        label = "المكتبة الشاملة"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"📚 فتح البحث في {label}",
                url=url,
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 رجوع",
                callback_data="library",
            ),
        ],
    ])

    await show(
        q,
        library.format_search_result(query),
        keyboard,
    )


# ============================================================
# Character Handler
# ============================================================

async def handle_character(update, context):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "الجاحظ",
                callback_data="character:الجاحظ",
            ),
            InlineKeyboardButton(
                "المتنبي",
                callback_data="character:المتنبي",
            ),
        ],
        [
            InlineKeyboardButton(
                "سيبويه",
                callback_data="character:سيبويه",
            ),
            InlineKeyboardButton(
                "الخليل بن أحمد",
                callback_data="character:الخليل بن أحمد",
            ),
        ],
        [
            InlineKeyboardButton(
                "ابن منظور",
                callback_data="character:ابن منظور",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 رجوع",
                callback_data="back_main",
            ),
        ],
    ])

    await show(
        q,
        "🏺 <b>سير الأعلام</b>\n\n"
        "اختر الشخصية التي تريد معرفة نبذة عنها:",
        keyboard,
    )


async def handle_character_detail(update, context, name):

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
        "⏳ جاري تجهيز السيرة...",
    )

    ok, result = await character.get_character(
        name
    )

    if not ok:
        await show(
            q,
            result,
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 رجوع",
                        callback_data="character",
                    ),
                ],
            ]),
        )
        return

    await show(
        q,
        result,
        InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 السيرة التفصيلية",
                    callback_data=f"character_detail:{name}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 رجوع",
                    callback_data="character",
                ),
            ],
        ]),
    )


async def handle_character_full(update, context, name):

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
        "⏳ جاري تجهيز السيرة التفصيلية...",
    )

    result = await character.get_character_detail(
        name
    )

    await send_long_message(
        q.message,
        result,
    )

await q.message.reply_text(
        "🔙 رجوع",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🏺 سير الأعلام",
                    callback_data="character",
                ),
            ],
        ]),
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

            "💡 ملاحظة:\n"
            "الجملة الاسمية الأساسية تتكون غالباً من مبتدأ وخبر."
        ),
    },

    "kana": {
        "title": "🔵 كان وأخواتها",
        "text": (
            "📚 كان وأخواتها\n\n"
            "🔹 التعريف:\n"
            "أفعال ناسخة تدخل على الجملة الاسمية، فترفع المبتدأ "
            "ويسمى اسمها، وتنصب الخبر ويسمى خبرها.\n\n"

            "🔹 من أخوات كان:\n"
            "كان، أصبح، أمسى، أضحى، ظل، بات، صار، ليس، "
            "ما زال، ما دام.\n\n"

            "🔹 القاعدة:\n"
            "اسم كان وأخواتها: مرفوع.\n"
            "خبر كان وأخواتها: منصوب.\n\n"

            "🔹 مثال:\n"
            "كانَ الجوُّ جميلاً.\n\n"

            "الجوُّ: اسم كان مرفوع.\n"
            "جميلاً: خبر كان منصوب.\n\n"

            "💡 احفظها:\n"
            "كان وأخواتها = ترفع الأول وتنصب الثاني."
        ),
    },

    "inna": {
        "title": "🟢 إن وأخواتها",
        "text": (
            "📚 إن وأخواتها\n\n"
            "🔹 التعريف:\n"
            "حروف ناسخة تدخل على الجملة الاسمية، فتنصب المبتدأ "
            "ويسمى اسمها، وترفع الخبر ويسمى خبرها.\n\n"

            "🔹 من أخوات إن:\n"
            "إنَّ، أنَّ، كأنَّ، لكنَّ، ليتَ، لعلَّ.\n\n"

            "🔹 القاعدة:\n"
            "اسم إن وأخواتها: منصوب.\n"
            "خبر إن وأخواتها: مرفوع.\n\n"

            "🔹 مثال:\n"
            "إنَّ العلمَ نافعٌ.\n\n"

            "العلمَ: اسم إن منصوب.\n"
            "نافعٌ: خبر إن مرفوع.\n\n"

            "💡 احفظها:\n"
            "إن وأخواتها = تنصب الأول وترفع الثاني."
        ),
    },

    "mafool_bih": {
        "title": "🟠 المفعول به",
        "text": (
            "📚 المفعول به\n\n"
            "🔹 التعريف:\n"
            "اسم منصوب يدل على من وقع عليه فعل الفاعل.\n\n"

            "🔹 مثال:\n"
            "قرأَ الطالبُ الكتابَ.\n\n"

            "الطالبُ: فاعل مرفوع.\n"
            "الكتابَ: مفعول به منصوب.\n\n"

            "🔹 مثال آخر:\n"
            "كتبَ الطالبُ الدرسَ.\n\n"

            "الدرسَ: مفعول به منصوب وعلامة نصبه الفتحة.\n\n"

            "💡 طريقة معرفته:\n"
            "اسأل: ماذا فعل الفاعل؟ أو على من وقع الفعل؟"
        ),
    },

    "fael": {
        "title": "🔵 الفاعل",
        "text": (
            "📚 الفاعل\n\n"
            "🔹 التعريف:\n"
            "اسم مرفوع يدل على من قام بالفعل أو اتصف به.\n\n"

            "🔹 مثال:\n"
            "نجحَ الطالبُ.\n\n"

            "الطالبُ: فاعل مرفوع.\n\n"

            "🔹 مثال آخر:\n"
            "كتبَ المعلمُ الدرسَ.\n\n"

            "المعلمُ: فاعل مرفوع.\n"
            "الدرسَ: مفعول به منصوب.\n\n"

            "💡 تذكر:\n"
            "الفاعل دائماً مرفوع في الأصل."
        ),
    },

    "naib_fael": {
        "title": "🟣 نائب الفاعل",
        "text": (
            "📚 نائب الفاعل\n\n"
            "🔹 التعريف:\n"
            "اسم مرفوع يحل محل الفاعل بعد بناء الفعل للمجهول.\n\n"

"🔹 مثال:\n"
            "كُتِبَ الدرسُ.\n\n"

            "الدرسُ: نائب فاعل مرفوع.\n\n"

            "🔹 مثال آخر:\n"
            "كُرِّمَ الطالبُ.\n\n"

            "الطالبُ: نائب فاعل مرفوع.\n\n"

            "💡 ملاحظة:\n"
            "عند بناء الفعل للمجهول يُحذف الفاعل ويحل محله نائب الفاعل."
        ),
    },

    "haal": {
        "title": "🟡 الحال",
        "text": (
            "📚 الحال\n\n"
            "🔹 التعريف:\n"
            "اسم نكرة منصوب يبين هيئة صاحبه وقت وقوع الفعل.\n\n"

            "🔹 مثال:\n"
            "جاءَ الطالبُ مسروراً.\n\n"

            "الطالبُ: فاعل.\n"
            "مسروراً: حال منصوب.\n\n"

            "🔹 مثال آخر:\n"
            "عادَ الجنديُّ منتصراً.\n\n"

            "منتصرًا: حال منصوب.\n\n"

            "💡 السؤال الذي يكشف الحال:\n"
            "كيف حدث الفعل؟"
        ),
    },

    "tamyiz": {
        "title": "🟤 التمييز",
        "text": (
            "📚 التمييز\n\n"
            "🔹 التعريف:\n"
            "اسم نكرة منصوب يزيل الإبهام عن كلمة أو جملة قبله.\n\n"

            "🔹 مثال:\n"
            "اشتريتُ عشرين كتاباً.\n\n"

            "كتاباً: تمييز منصوب.\n\n"

            "🔹 مثال آخر:\n"
            "محمدٌ أكثرُ علماً.\n\n"

            "علماً: تمييز منصوب.\n\n"

            "💡 ملاحظة:\n"
            "التمييز يوضح المقصود ويزيل الغموض."
        ),
    },

    "mafool_mutlaq": {
        "title": "🟢 المفعول المطلق",
        "text": (
            "📚 المفعول المطلق\n\n"
            "🔹 التعريف:\n"
            "مصدر منصوب يأتي بعد فعل من لفظه لتوكيده أو بيان نوعه أو عدده.\n\n"

            "🔹 مثال التوكيد:\n"
            "نجحَ الطالبُ نجاحاً.\n\n"

            "نجاحاً: مفعول مطلق للتوكيد.\n\n"

            "🔹 مثال النوع:\n"
            "سارَ الجنديُّ سيراً سريعاً.\n\n"

            "سيراً: مفعول مطلق لبيان النوع.\n\n"

            "🔹 مثال العدد:\n"
            "طرقتُ البابَ طرقتين.\n\n"

            "طرقتين: مفعول مطلق لبيان العدد."
        ),
    },

    "mafool_fih": {
        "title": "🔷 المفعول فيه",
        "text": (
            "📚 المفعول فيه\n\n"
            "🔹 التعريف:\n"
            "اسم منصوب يدل على زمان أو مكان وقوع الفعل، ويسمى ظرفاً.\n\n"

            "🔹 ظرف الزمان:\n"
            "سافرتُ صباحاً.\n\n"

            "صباحاً: ظرف زمان منصوب.\n\n"

            "🔹 ظرف المكان:\n"
            "جلستُ أمامَ المعلمِ.\n\n"

            "أمامَ: ظرف مكان منصوب.\n\n"

            "💡 السؤال:\n"
            "متى حدث الفعل؟ أو أين حدث؟"
        ),
    },

    "naat": {
        "title": "🟠 النعت",
        "text": (
            "📚 النعت\n\n"
            "🔹 التعريف:\n"
            "تابع يذكر لبيان صفة في اسم قبله يسمى المنعوت.\n\n"

            "🔹 مثال:\n"
            "جاءَ الطالبُ المجتهدُ.\n\n"

            "الطالبُ: منعوت.\n"
            "المجتهدُ: نعت مرفوع.\n\n"

            "🔹 مثال آخر:\n"
            "رأيتُ الطالبَ المجتهدَ.\n\n"

            "المجتهدَ: نعت منصوب.\n\n"

            "💡 قاعدة:\n"
            "النعت يتبع المنعوت في الإعراب والتعريف والتنكير والجنس والعدد."
        ),
    },

    "atf": {
        "title": "🔵 العطف",
        "text": (
            "📚 العطف\n\n"
            "🔹 التعريف:\n"
            "تابع يتوسط بينه وبين متبوعه أحد حروف العطف.\n\n"

            "🔹 من حروف العطف:\n"
            "الواو، الفاء، ثم، أو، أم، بل، لكن، لا.\n\n"

            "🔹 مثال:\n"
            "جاءَ محمدٌ وعليٌّ.\n\n"

            "محمدٌ: معطوف عليه.\n"
            "عليٌّ: معطوف مرفوع.\n\n"

            "💡 قاعدة:\n"
            "المعطوف يتبع المعطوف عليه في الإعراب."
        ),
    },

    "badal": {
        "title": "🟣 البدل",
        "text": (
            "📚 البدل\n\n"
            "🔹 التعريف:\n"
            "تابع مقصود بالحكم بلا واسطة، ويمكن أن يحل محل المبدل منه.\n\n"

            "🔹 مثال:\n"
            "جاءَ الخليفةُ عمرُ.\n\n"

            "عمرُ: بدل مرفوع.\n\n"

            "🔹 مثال آخر:\n"
            "رأيتُ أخاكَ محمداً.\n\n"

            "محمداً: بدل منصوب.\n\n"

"💡 قاعدة:\n"
            "البدل يتبع المبدل منه في الإعراب."
        ),
    },

    "jar": {
        "title": "🟢 حروف الجر",
        "text": (
            "📚 حروف الجر\n\n"
            "🔹 من أشهرها:\n"
            "من، إلى، عن، على، في، الباء، الكاف، اللام، ربَّ.\n\n"

            "🔹 مثال:\n"
            "ذهبتُ إلى المدرسةِ.\n\n"

            "المدرسةِ: اسم مجرور بـ «إلى» وعلامة جره الكسرة.\n\n"

            "🔹 مثال آخر:\n"
            "جلستُ في البيتِ.\n\n"

            "البيتِ: اسم مجرور بـ «في»."
        ),
    },

    "majzoom": {
        "title": "🟡 الفعل المضارع المجزوم",
        "text": (
            "📚 الفعل المضارع المجزوم\n\n"
            "🔹 من أدوات الجزم:\n"
            "لم، لما، لام الأمر، لا الناهية.\n\n"

            "🔹 مثال:\n"
            "لم يذهبْ الطالبُ.\n\n"

            "يذهبْ: فعل مضارع مجزوم بـ «لم» وعلامة جزمه السكون.\n\n"

            "🔹 مثال آخر:\n"
            "لا تهملْ دروسك.\n\n"

            "تهملْ: فعل مضارع مجزوم بـ «لا الناهية»."
        ),
    },

    "mansub": {
        "title": "🔴 الفعل المضارع المنصوب",
        "text": (
            "📚 الفعل المضارع المنصوب\n\n"
            "🔹 من أدوات النصب:\n"
            "أن، لن، كي، حتى، لام التعليل.\n\n"

            "🔹 مثال:\n"
            "لن يهملَ الطالبُ دروسه.\n\n"

            "يهملَ: فعل مضارع منصوب بـ «لن» وعلامة نصبه الفتحة.\n\n"

            "🔹 مثال:\n"
            "أدرسُ كي أنجحَ.\n\n"

            "أنجحَ: فعل مضارع منصوب بـ «كي»."
        ),
    },

    "marfoo": {
        "title": "🔵 الفعل المضارع المرفوع",
        "text": (
            "📚 الفعل المضارع المرفوع\n\n"
            "🔹 القاعدة:\n"
            "الفعل المضارع يكون مرفوعاً إذا لم يسبقه ناصب ولا جازم.\n\n"

            "🔹 مثال:\n"
            "يكتبُ الطالبُ الدرسَ.\n\n"

            "يكتبُ: فعل مضارع مرفوع وعلامة رفعه الضمة.\n\n"

            "🔹 مثال آخر:\n"
            "الطلابُ يدرسونَ.\n\n"

            "يدرسونَ: فعل مضارع مرفوع بثبوت النون لأنه من الأفعال الخمسة."
        ),
    },

    "afaal_khamsa": {
        "title": "🟠 الأفعال الخمسة",
        "text": (
            "📚 الأفعال الخمسة\n\n"
            "🔹 التعريف:\n"
            "كل فعل مضارع اتصلت به ألف الاثنين أو واو الجماعة "
            "أو ياء المخاطبة.\n\n"

            "🔹 أمثلتها:\n"
            "يفعلان، تفعلان، يفعلون، تفعلون، تفعلين.\n\n"

            "🔹 علامة رفعها:\n"
            "ثبوت النون.\n\n"

            "🔹 علامة نصبها وجزمها:\n"
            "حذف النون.\n\n"

            "🔹 مثال:\n"
            "الطلابُ يدرسونَ.\n"
            "لن يدرسوا.\n"
            "لم يدرسوا."
        ),
    },

    "mabni": {
        "title": "🟣 المبني والمعرب",
        "text": (
            "📚 المبني والمعرب\n\n"
            "🔹 المعرب:\n"
            "ما يتغير آخره بتغير موقعه في الجملة.\n\n"

            "🔹 المبني:\n"
            "ما يلزم آخره حالة واحدة مهما تغير موقعه.\n\n"

            "🔹 مثال المعرب:\n"
            "جاءَ محمدٌ.\n"
            "رأيتُ محمداً.\n"
            "مررتُ بمحمدٍ.\n\n"

            "نلاحظ تغير آخر «محمد» حسب موقعه.\n\n"

            "🔹 مثال المبني:\n"
            "هذا طالبٌ.\n"
            "رأيتُ هذا الطالبَ.\n"
            "مررتُ بهذا الطالبِ."
        ),
    },

    "ism_mawsul": {
        "title": "🟢 الاسم الموصول",
        "text": (
            "📚 الاسم الموصول\n\n"
            "🔹 التعريف:\n"
            "اسم يحتاج إلى جملة بعده تسمى صلة الموصول لتتميم معناه.\n\n"

            "🔹 من الأسماء الموصولة:\n"
            "الذي، التي، اللذان، اللتان، الذين، اللاتي، من، ما.\n\n"

            "🔹 مثال:\n"
            "جاءَ الطالبُ الذي نجحَ.\n\n"

            "الذي: اسم موصول.\n"
            "نجحَ: صلة الموصول.\n\n"

            "💡 ملاحظة:\n"
            "صلة الموصول لا محل لها من الإعراب."
        ),
    },

    "ism_ishara": {
        "title": "🔵 أسماء الإشارة",
        "text": (
            "📚 أسماء الإشارة\n\n"
            "🔹 للمفرد المذكر:\n"
            "هذا.\n\n"

"🔹 للمفرد المؤنث:\n"
            "هذه.\n\n"

            "🔹 للمثنى:\n"
            "هذان، هاتان.\n\n"

            "🔹 للجمع:\n"
            "هؤلاء.\n\n"

            "🔹 مثال:\n"
            "هذا طالبٌ مجتهدٌ.\n\n"

            "هذا: اسم إشارة."
        ),
    },

    "ism_tafdeel": {
        "title": "🟡 اسم التفضيل",
        "text": (
            "📚 اسم التفضيل\n\n"
            "🔹 التعريف:\n"
            "اسم يدل على اشتراك شيئين في صفة وزيادة أحدهما فيها على الآخر.\n\n"

            "🔹 أمثلة:\n"
            "أكبر، أصغر، أفضل، أجمل، أسرع، أقوى.\n\n"

            "🔹 مثال:\n"
            "العلمُ أفضلُ من المالِ.\n\n"

            "أفضلُ: اسم تفضيل.\n\n"

            "💡 ملاحظة:\n"
            "غالباً يأتي على وزن «أفعل»."
        ),
    },

    "masdar": {
        "title": "🟠 المصدر",
        "text": (
            "📚 المصدر\n\n"
            "🔹 التعريف:\n"
            "اسم يدل على الحدث مجرداً من الزمن.\n\n"

            "🔹 أمثلة:\n"
            "كتبَ ← كتابة.\n"
            "قرأَ ← قراءة.\n"
            "نجحَ ← نجاح.\n"
            "جلسَ ← جلوس.\n\n"

            "🔹 مثال في جملة:\n"
            "أحبُّ القراءةَ.\n\n"

            "القراءةَ: مصدر."
        ),
    },

    "ism_fael": {
        "title": "🟣 اسم الفاعل",
        "text": (
            "📚 اسم الفاعل\n\n"
            "🔹 التعريف:\n"
            "اسم مشتق يدل على من قام بالفعل أو اتصف به.\n\n"

            "🔹 من الفعل الثلاثي:\n"
            "على وزن فاعل.\n\n"

            "كتب ← كاتب.\n"
            "قرأ ← قارئ.\n"
            "جلس ← جالس.\n\n"

            "🔹 مثال:\n"
            "جاءَ الطالبُ المجتهدُ.\n\n"

            "المجتهدُ: اسم فاعل."
        ),
    },

    "ism_mafool": {
        "title": "🔴 اسم المفعول",
        "text": (
            "📚 اسم المفعول\n\n"
            "🔹 التعريف:\n"
            "اسم مشتق يدل على من وقع عليه الفعل.\n\n"

            "🔹 من الفعل الثلاثي:\n"
            "على وزن مفعول.\n\n"

            "كتب ← مكتوب.\n"
            "قرأ ← مقروء.\n"
            "حفظ ← محفوظ.\n\n"

            "🔹 مثال:\n"
            "قرأتُ الكتابَ المكتوبَ بعناية.\n\n"

            "المكتوبَ: اسم مفعول."
        ),
    },

    "mubalaghah": {
        "title": "🟢 صيغ المبالغة",
        "text": (
            "📚 صيغ المبالغة\n\n"
            "🔹 التعريف:\n"
            "أسماء تدل على كثرة وقوع الفعل أو قوته.\n\n"

            "🔹 من أوزانها:\n"
            "فعّال، مفعال، فعول، فعيل، فَعِل.\n\n"

            "🔹 أمثلة:\n"
            "غفّار، مقدام، صبور، رحيم، حذر.\n\n"

            "🔹 مثال:\n"
            "الله غفّارٌ للذنوب.\n\n"

            "غفّار: صيغة مبالغة."
        ),
    },

    "ism_alat": {
        "title": "🔵 اسم الآلة",
        "text": (
            "📚 اسم الآلة\n\n"
            "🔹 التعريف:\n"
            "اسم يدل على الأداة التي يقع بها الفعل.\n\n"

            "🔹 أمثلة:\n"
            "مفتاح، منشار، مكنسة، مطرقة، محراث.\n\n"

            "🔹 مثال:\n"
            "فتحتُ البابَ بالمفتاحِ.\n\n"

            "المفتاح: اسم آلة."
        ),
    },

    "zamir": {
        "title": "🟣 الضمائر",
        "text": (
            "📚 الضمائر\n\n"
            "🔹 التعريف:\n"
            "أسماء تدل على متكلم أو مخاطب أو غائب.\n\n"

            "🔹 ضمائر المتكلم:\n"
            "أنا، نحن.\n\n"

            "🔹 ضمائر المخاطب:\n"
            "أنتَ، أنتِ، أنتما، أنتم، أنتن.\n\n"

            "🔹 ضمائر الغائب:\n"
            "هو، هي، هما، هم، هن.\n\n"

            "🔹 مثال:\n"
            "هو طالبٌ مجتهدٌ.\n"
            "أنا أحبُّ العلمَ."
        ),
    },

    "jumlah_feliah": {
        "title": "🟠 الجملة الفعلية",
        "text": (
            "📚 الجملة الفعلية\n\n"
            "🔹 التعريف:\n"
            "هي الجملة التي تبدأ بفعل غالباً.\n\n"

            "🔹 عناصرها الأساسية:\n"
            "الفعل، والفاعل، وقد يأتي المفعول به.\n\n"

            "🔹 مثال:\n"
            "كتبَ الطالبُ الدرسَ.\n\n"

"كتبَ: فعل.\n"
            "الطالبُ: فاعل.\n"
            "الدرسَ: مفعول به.\n\n"

            "💡 ملاحظة:\n"
            "قد تكون الجملة الفعلية فعلًا وفاعلًا فقط."
        ),
    },

    "jumlah_ismiah": {
        "title": "🔵 الجملة الاسمية",
        "text": (
            "📚 الجملة الاسمية\n\n"
            "🔹 التعريف:\n"
            "هي الجملة التي تبدأ باسم غالباً وتتكون أساساً من مبتدأ وخبر.\n\n"

            "🔹 مثال:\n"
            "العلمُ نورٌ.\n\n"

            "العلمُ: مبتدأ.\n"
            "نورٌ: خبر.\n\n"

            "🔹 مثال آخر:\n"
            "الطلابُ مجتهدون.\n\n"

            "الطلابُ: مبتدأ.\n"
            "مجتهدون: خبر."
        ),
    },

    "ism_zaman": {
        "title": "🟡 اسم الزمان",
        "text": (
            "📚 اسم الزمان\n\n"
            "🔹 التعريف:\n"
            "اسم مشتق يدل على زمان وقوع الفعل.\n\n"

            "🔹 أمثلة:\n"
            "موعد، مولد، مغرب، مشرق.\n\n"

            "🔹 مثال:\n"
            "هذا موعدُ السفرِ.\n\n"

            "موعد: اسم زمان."
        ),
    },

    "ism_makan": {
        "title": "🟢 اسم المكان",
        "text": (
            "📚 اسم المكان\n\n"
            "🔹 التعريف:\n"
            "اسم مشتق يدل على مكان وقوع الفعل.\n\n"

            "🔹 أمثلة:\n"
            "مجلس، ملعب، مكتب، مسجد، مدرسة.\n\n"

            "🔹 مثال:\n"
            "ذهبتُ إلى الملعبِ.\n\n"

            "الملعب: اسم مكان."
        ),
    },

    "hamza_wasl_qata": {
        "title": "🔴 همزة الوصل والقطع",
        "text": (
            "📚 همزة الوصل والقطع\n\n"
            "🔹 همزة القطع:\n"
            "تنطق في بداية الكلام ووسطه، وتكتب همزة ظاهرة.\n\n"

            "أحمد، إن، أكرم، أخذ.\n\n"

            "🔹 همزة الوصل:\n"
            "تنطق في بداية الكلام وتسقط في درج الكلام.\n\n"

            "ابن، اسم، استخرج، اكتب.\n\n"

            "💡 ملاحظة:\n"
            "معرفة نوع الهمزة تساعد في الكتابة الصحيحة."
        ),
    },

    "taa_marbuta": {
        "title": "🟣 التاء المربوطة والمفتوحة",
        "text": (
            "📚 التاء المربوطة والمفتوحة\n\n"
            "🔹 التاء المربوطة:\n"
            "تأتي غالباً في آخر الأسماء المؤنثة.\n\n"

            "مدرسة، شجرة، جميلة.\n\n"

            "🔹 التاء المفتوحة:\n"
            "تبقى تاء عند الوقف والوصل.\n\n"

            "بيت، بنت، كتبت.\n\n"

            "💡 طريقة مفيدة:\n"
            "عند الوقف على التاء المربوطة تنطق هاء غالباً."
        ),
    },

    "alef_layina": {
        "title": "🟠 الألف اللينة",
        "text": (
            "📚 الألف اللينة\n\n"
            "🔹 التعريف:\n"
            "ألف تأتي في آخر الكلمة وتكتب بصورة الألف أو الياء غير المنقوطة.\n\n"

            "🔹 أمثلة:\n"
            "دعا، سما، رمى، سعى.\n\n"

            "🔹 ملاحظة:\n"
            "معرفة أصل الألف يساعد في معرفة طريقة كتابتها."
        ),
    },

    "hamza_middle": {
        "title": "🔵 الهمزة المتوسطة",
        "text": (
            "📚 الهمزة المتوسطة\n\n"
            "🔹 القاعدة العامة:\n"
            "ينظر في كتابة الهمزة المتوسطة إلى أقوى الحركتين: "
            "حركة الهمزة وحركة ما قبلها.\n\n"

            "🔹 ترتيب قوة الحركات:\n"
            "الكسرة، ثم الضمة، ثم الفتحة، ثم السكون.\n\n"

            "🔹 أمثلة:\n"
            "سُئِلَ، سَأَلَ، يَؤُمُّ.\n\n"

            "💡 ملاحظة:\n"
            "هناك حالات تفصيلية كثيرة، والأفضل تطبيق قاعدة قوة الحركة."
        ),
    },

    "hamza_end": {
        "title": "🟢 الهمزة المتطرفة",
        "text": (
            "📚 الهمزة المتطرفة\n\n"
            "🔹 القاعدة:\n"
            "ينظر في كتابة الهمزة المتطرفة إلى حركة الحرف الذي قبلها.\n\n"

            "🔹 أمثلة:\n"
            "بدأ، يجرؤ، يستهزئ، شيء.\n\n"

            "💡 ملاحظة:\n"
            "تختلف صورتها بحسب حركة ما قبلها."
        ),
    },

"marfooat": {
        "title": "🟡 المرفوعات",
        "text": (
            "📚 المرفوعات في النحو\n\n"
            "من أشهر المرفوعات:\n\n"
            "🔹 المبتدأ.\n"
            "🔹 الخبر.\n"
            "🔹 الفاعل.\n"
            "🔹 نائب الفاعل.\n"
            "🔹 اسم كان وأخواتها.\n"
            "🔹 خبر إن وأخواتها.\n\n"

            "💡 ملاحظة:\n"
            "الرفع له علامات أصلية وفرعية بحسب نوع الاسم أو الفعل."
        ),
    },

    "mansubat": {
        "title": "🔴 المنصوبات",
        "text": (
            "📚 المنصوبات في النحو\n\n"
            "من أشهر المنصوبات:\n\n"
            "🔹 المفعول به.\n"
            "🔹 المفعول المطلق.\n"
            "🔹 المفعول فيه.\n"
            "🔹 المفعول لأجله.\n"
            "🔹 الحال.\n"
            "🔹 التمييز.\n"
            "🔹 خبر كان.\n"
            "🔹 اسم إن.\n\n"

            "💡 ملاحظة:\n"
            "ليست كل المنصوبات علامة نصبها الفتحة، فهناك علامات فرعية."
        ),
    },

    "majrurat": {
        "title": "🟣 المجرورات",
        "text": (
            "📚 المجرورات\n\n"
            "🔹 أهمها:\n"
            "الاسم المجرور بحرف الجر، والمضاف إليه، والتابع للمجرور.\n\n"

            "🔹 مثال:\n"
            "ذهبتُ إلى المدرسةِ.\n\n"

            "المدرسةِ: اسم مجرور بحرف الجر.\n\n"

            "🔹 مثال:\n"
            "كتابُ الطالبِ جديدٌ.\n\n"

            "الطالبِ: مضاف إليه مجرور."
        ),
    },

    "addition": {
        "title": "🟢 المضاف والمضاف إليه",
        "text": (
            "📚 المضاف والمضاف إليه\n\n"
            "🔹 التعريف:\n"
            "المضاف اسم يأتي قبل اسم آخر يوضحه أو يخصصه، "
            "والاسم الثاني يسمى مضافاً إليه ويكون مجروراً.\n\n"

            "🔹 مثال:\n"
            "كتابُ الطالبِ مفيدٌ.\n\n"

            "كتابُ: مضاف.\n"
            "الطالبِ: مضاف إليه مجرور.\n\n"

            "💡 ملاحظة:\n"
            "المضاف لا ينون غالباً، والمضاف إليه مجرور."
        ),
    },

    "tanween": {
        "title": "🟠 التنوين",
        "text": (
            "📚 التنوين\n\n"
            "🔹 التعريف:\n"
            "نون ساكنة زائدة تلحق آخر الاسم لفظاً لا خطاً.\n\n"

            "🔹 أنواعه:\n"
            "تنوين الضم: كتابٌ.\n"
            "تنوين الفتح: كتاباً.\n"
            "تنوين الكسر: كتابٍ.\n\n"

            "💡 ملاحظة:\n"
            "التنوين من علامات الاسم."
        ),
    },

    "alam": {
        "title": "🔵 العلم",
        "text": (
            "📚 العَلَم\n\n"
            "🔹 التعريف:\n"
            "اسم يدل على معين بذاته دون حاجة إلى قرينة.\n\n"

            "🔹 أمثلة:\n"
            "محمد، بغداد، العراق، دجلة.\n\n"

            "🔹 مثال:\n"
            "زارَ محمدٌ بغدادَ.\n\n"

            "محمد وبغداد: اسما علم."
        ),
    },

    "nakira_marifa": {
        "title": "🟣 النكرة والمعرفة",
        "text": (
            "📚 النكرة والمعرفة\n\n"
            "🔹 النكرة:\n"
            "ما دل على شيء غير معين.\n\n"

            "كتاب، طالب، مدينة.\n\n"

            "🔹 المعرفة:\n"
            "ما دل على شيء معين.\n\n"

            "الكتاب، الطالب، بغداد.\n\n"

            "💡 من المعارف:\n"
            "العلم، الضمير، اسم الإشارة، الاسم الموصول، المعرف بـ «أل»، والمضاف إلى معرفة."
        ),
    },

    "istifham": {
        "title": "🟡 أسلوب الاستفهام",
        "text": (
            "📚 أسلوب الاستفهام\n\n"
            "🔹 التعريف:\n"
            "أسلوب يستخدم لطلب معرفة شيء مجهول.\n\n"

            "🔹 أدواته:\n"
            "هل، الهمزة، من، ما، ماذا، متى، أين، كيف، كم، أي.\n\n"

            "🔹 مثال:\n"
            "أينَ ذهبتَ؟\n"
            "هل درستَ؟\n"
            "من حضرَ؟\n\n"

            "💡 ملاحظة:\n"
            "تختلف أداة الاستفهام بحسب المطلوب معرفته."
        ),
    },

    "nida": {
        "title": "🟢 أسلوب النداء",
        "text": (
            "📚 أسلوب النداء\n\n"
            "🔹 التعريف:\n"
            "أسلوب يستخدم لطلب إقبال المنادى أو تنبيهه.\n\n"

            "🔹 من أدواته:\n"
            "يا، أيا، هيا، أي.\n\n"

"🔹 مثال:\n"
            "يا طالبُ، اجتهد.\n\n"

            "طالب: منادى.\n\n"

            "💡 ملاحظة:\n"
            "للمنادى أحكام إعرابية تختلف حسب نوعه."
        ),
    },

    "amr": {
        "title": "🔴 أسلوب الأمر",
        "text": (
            "📚 أسلوب الأمر\n\n"
            "🔹 التعريف:\n"
            "أسلوب يطلب به حصول الفعل.\n\n"

            "🔹 مثال:\n"
            "اجتهدْ في دراستك.\n"
            "اقرأْ كتابك.\n"
            "احفظْ دروسك.\n\n"

            "💡 ملاحظة:\n"
            "فعل الأمر مبني غالباً."
        ),
    },

    "nahy": {
        "title": "🟣 أسلوب النهي",
        "text": (
            "📚 أسلوب النهي\n\n"
            "🔹 التعريف:\n"
            "أسلوب يطلب به الكف عن فعل شيء.\n\n"

            "🔹 أداته الأساسية:\n"
            "لا الناهية.\n\n"

            "🔹 مثال:\n"
            "لا تهملْ دروسك.\n\n"

            "تهملْ: فعل مضارع مجزوم بـ «لا الناهية»."
        ),
    },

    "taajjub": {
        "title": "🟠 أسلوب التعجب",
        "text": (
            "📚 أسلوب التعجب\n\n"
            "🔹 التعريف:\n"
            "أسلوب يدل على استغراب أو إعجاب بصفة في شيء.\n\n"

            "🔹 صيغته المشهورة:\n"
            "ما أفعلَه!\n"
            "أفعلْ به!\n\n"

            "🔹 مثال:\n"
            "ما أجملَ السماءَ!\n"
            "أجملْ بالسماءِ!\n\n"

            "💡 ملاحظة:\n"
            "للتعجب شروط وصياغة صرفية خاصة."
        ),
    },

    "madh_zamm": {
        "title": "🔵 أسلوب المدح والذم",
        "text": (
            "📚 أسلوب المدح والذم\n\n"
            "🔹 أدوات المدح:\n"
            "نِعم، حبذا.\n\n"

            "🔹 أدوات الذم:\n"
            "بئس، لا حبذا.\n\n"

            "🔹 مثال:\n"
            "نِعمَ الطالبُ المجتهدُ.\n"
            "بئسَ الخلقُ الكذبُ.\n\n"

            "💡 ملاحظة:\n"
            "لهذا الأسلوب أحكام إعرابية خاصة."
        ),
    },

    "qasam": {
        "title": "🟢 أسلوب القسم",
        "text": (
            "📚 أسلوب القسم\n\n"
            "🔹 التعريف:\n"
            "أسلوب يستخدم لتوكيد الكلام.\n\n"

            "🔹 من أدوات القسم:\n"
            "الواو، الباء، التاء.\n\n"

            "🔹 مثال:\n"
            "واللهِ لأجتهدنَّ.\n\n"

            "والله: اسم مجرور بواو القسم.\n\n"

            "💡 ملاحظة:\n"
            "جواب القسم قد يقترن بلام التوكيد أو نون التوكيد."
        ),
    },

    "tawkid": {
        "title": "🟣 التوكيد",
        "text": (
            "📚 التوكيد\n\n"
            "🔹 التعريف:\n"
            "تابع يذكر لتقوية المعنى وإزالة الشك.\n\n"

            "🔹 نوعاه:\n"
            "توكيد لفظي وتوكيد معنوي.\n\n"

            "🔹 التوكيد اللفظي:\n"
            "جاءَ جاءَ الطالبُ.\n\n"

            "🔹 التوكيد المعنوي:\n"
            "جاءَ الطالبُ نفسهُ.\n\n"

            "💡 من ألفاظه:\n"
            "نفس، عين، كل، جميع، عامة، كلا، كلتا."
        ),
    },

    "istithna": {
        "title": "🟡 الاستثناء",
        "text": (
            "📚 أسلوب الاستثناء\n\n"
            "🔹 التعريف:\n"
            "إخراج ما بعد أداة الاستثناء من حكم ما قبلها.\n\n"

            "🔹 أركانه:\n"
            "المستثنى منه، أداة الاستثناء، المستثنى.\n\n"

            "🔹 أشهر أداة:\n"
            "إلا.\n\n"

            "🔹 مثال:\n"
            "حضرَ الطلابُ إلا طالباً.\n\n"

            "طالباً: مستثنى."
        ),
    },

    "shart": {
        "title": "🟠 أسلوب الشرط",
        "text": (
            "📚 أسلوب الشرط\n\n"
            "🔹 التعريف:\n"
            "أسلوب يربط حصول شيء بحصول شيء آخر.\n\n"

            "🔹 من أدواته:\n"
            "إن، من، ما، مهما، متى، أينما، حيثما.\n\n"

            "🔹 مثال:\n"
            "إن تجتهدْ تنجحْ.\n\n"

            "تجتهدْ: فعل الشرط مجزوم.\n"
            "تنجحْ: جواب الشرط مجزوم."
        ),
    },

    "la_nafia": {
        "title": "🔵 لا النافية",
        "text": (
            "📚 لا النافية\n\n"
            "🔹 التعريف:\n"
            "حرف يستخدم لنفي حدوث الفعل أو وجود الشيء بحسب نوعه.\n\n"

"🔹 مثال:\n"
            "لا أهملُ دروسي.\n\n"

            "لا هنا نافية، والفعل المضارع بعدها مرفوع.\n\n"

            "💡 انتبه:\n"
            "لا النافية تختلف عن لا الناهية."
        ),
    },

    "la_nahy": {
        "title": "🔴 الفرق بين لا النافية والناهية",
        "text": (
            "📚 لا النافية والناهية\n\n"
            "🔹 لا النافية:\n"
            "تنفي ولا تطلب الكف.\n"
            "مثال: لا أهملُ دروسي.\n\n"

            "🔹 لا الناهية:\n"
            "تطلب الكف عن الفعل وتجزم المضارع.\n"
            "مثال: لا تهملْ دروسك.\n\n"

            "💡 الفرق المهم:\n"
            "الناهية = طلب + جزم.\n"
            "النافية = نفي."
        ),
    },

    "ma_nafia": {
        "title": "🟢 ما النافية",
        "text": (
            "📚 ما النافية\n\n"
            "🔹 التعريف:\n"
            "أداة تستخدم لنفي الجملة.\n\n"

            "🔹 مثال:\n"
            "ما حضرَ الطالبُ.\n\n"

            "أي: لم يحضر الطالب.\n\n"

            "💡 ملاحظة:\n"
            "لـ «ما» استعمالات أخرى بحسب السياق."
        ),
    },

    "la_nasikhah": {
        "title": "🟣 لا النافية للجنس",
        "text": (
            "📚 لا النافية للجنس\n\n"
            "🔹 التعريف:\n"
            "تدخل على الجملة الاسمية لنفي الجنس نفياً شاملاً.\n\n"

            "🔹 مثال:\n"
            "لا طالبَ مهملٌ.\n\n"

            "طالبَ: اسم لا النافية للجنس.\n"
            "مهملٌ: خبرها.\n\n"

            "💡 ملاحظة:\n"
            "لها أحكام خاصة في إعراب اسمها بحسب نوعه."
        ),
    },

    "kana_zanna": {
        "title": "🔵 أفعال القلوب",
        "text": (
            "📚 أفعال القلوب\n\n"
            "🔹 التعريف:\n"
            "أفعال تدخل على المبتدأ والخبر فتنصبهما مفعولين لها.\n\n"

            "🔹 منها:\n"
            "ظن، حسب، خال، علم، رأى، وجد، جعل.\n\n"

            "🔹 مثال:\n"
            "ظننتُ الطالبَ مجتهداً.\n\n"

            "الطالبَ: مفعول به أول.\n"
            "مجتهداً: مفعول به ثانٍ."
        ),
    },

    "ism_mamnoo": {
        "title": "🟡 الممنوع من الصرف",
        "text": (
            "📚 الممنوع من الصرف\n\n"
            "🔹 التعريف:\n"
            "اسم لا يقبل التنوين ويجر بالفتحة نيابة عن الكسرة في حالات معينة.\n\n"

            "🔹 مثال:\n"
            "مررتُ بأحمدَ.\n\n"

            "أحمد: اسم ممنوع من الصرف.\n\n"

            "💡 ملاحظة:\n"
            "له أسباب متعددة، مثل العلمية ووزن الفعل وبعض صيغ الجموع."
        ),
    },

    "jam_takseer": {
        "title": "🟢 جمع التكسير",
        "text": (
            "📚 جمع التكسير\n\n"
            "🔹 التعريف:\n"
            "جمع تتغير فيه صورة المفرد عند الجمع.\n\n"

            "🔹 أمثلة:\n"
            "كتاب ← كتب.\n"
            "رجل ← رجال.\n"
            "قلم ← أقلام.\n\n"

            "💡 ملاحظة:\n"
            "له أوزان كثيرة ولا يقتصر على وزن واحد."
        ),
    },

    "jam_muzakkar": {
        "title": "🔵 جمع المذكر السالم",
        "text": (
            "📚 جمع المذكر السالم\n\n"
            "🔹 التعريف:\n"
            "ما دل على أكثر من اثنين بزيادة واو ونون أو ياء ونون "
            "مع سلامة مفرده من التغيير.\n\n"

            "🔹 مثال:\n"
            "معلم ← معلمون.\n"
            "معلمين.\n\n"

            "🔹 علاماته:\n"
            "يرفع بالواو.\n"
            "ينصب ويجر بالياء."
        ),
    },

    "jam_moannath": {
        "title": "🟣 جمع المؤنث السالم",
        "text": (
            "📚 جمع المؤنث السالم\n\n"
            "🔹 التعريف:\n"
            "ما دل على أكثر من اثنتين بزيادة ألف وتاء على مفرده غالباً.\n\n"

            "🔹 مثال:\n"
            "طالبة ← طالبات.\n\n"

            "🔹 علاماته:\n"
            "يرفع بالضمة.\n"
            "ينصب ويجر بالكسرة نيابة عن الفتحة في حالة النصب."
        ),
    },

    "muthanna": {
        "title": "🟠 المثنى",
        "text": (
            "📚 المثنى\n\n"
            "🔹 التعريف:\n"
            "ما دل على اثنين أو اثنتين بزيادة ألف ونون أو ياء ونون.\n\n"

            "🔹 مثال:\n"
            "طالبانِ، طالبينِ.\n\n"

"🔹 علاماته:\n"
            "يرفع بالألف.\n"
            "ينصب ويجر بالياء."
        ),
    },

    "adad": {
        "title": "🔴 العدد والمعدود",
        "text": (
            "📚 العدد والمعدود\n\n"
            "🔹 التعريف:\n"
            "العدد لفظ يدل على كمية الأشياء، وله أحكام مختلفة بحسب العدد.\n\n"

            "🔹 أمثلة:\n"
            "ثلاثةُ كتبٍ.\n"
            "خمسةُ طلابٍ.\n"
            "عشرُ طالباتٍ.\n\n"

            "💡 ملاحظة:\n"
            "أحكام العدد تختلف بين المفرد والمثنى والجمع، وبين الأعداد المختلفة."
        ),
    },

    "maful_li_ajlih": {
        "title": "🟢 المفعول لأجله",
        "text": (
            "📚 المفعول لأجله\n\n"
            "🔹 التعريف:\n"
            "مصدر منصوب يبين سبب وقوع الفعل.\n\n"

            "🔹 مثال:\n"
            "درستُ طلباً للنجاح.\n\n"

            "طلباً: مفعول لأجله.\n\n"

            "🔹 مثال آخر:\n"
            "سافرتُ رغبةً في العلم.\n\n"

            "رغبةً: مفعول لأجله."
        ),
    },

    "maful_maah": {
        "title": "🟡 المفعول معه",
        "text": (
            "📚 المفعول معه\n\n"
            "🔹 التعريف:\n"
            "اسم منصوب يأتي بعد واو بمعنى «مع» لبيان المصاحبة.\n\n"

            "🔹 مثال:\n"
            "سرتُ والنهرَ.\n\n"

            "النهرَ: مفعول معه.\n\n"

            "💡 ملاحظة:\n"
            "ليست كل واو بعدها اسم تكون واو معية."
        ),
    },

    "mustathna": {
        "title": "🟣 المستثنى",
        "text": (
            "📚 المستثنى\n\n"
            "🔹 التعريف:\n"
            "اسم يأتي بعد أداة استثناء ليخرج من حكم ما قبلها.\n\n"

            "🔹 مثال:\n"
            "نجحَ الطلابُ إلا طالباً.\n\n"

            "طالباً: مستثنى.\n\n"

            "💡 ملاحظة:\n"
            "إعرابه يتغير بحسب نوع الاستثناء وتركيب الجملة."
        ),
    },

    "badal_types": {
        "title": "🔵 أنواع البدل",
        "text": (
            "📚 أنواع البدل\n\n"
            "🔹 بدل كل من كل.\n"
            "🔹 بدل بعض من كل.\n"
            "🔹 بدل اشتمال.\n"
            "🔹 بدل الغلط.\n\n"

            "🔹 مثال كل من كل:\n"
            "جاءَ أخوكَ محمدٌ.\n\n"

            "🔹 مثال بعض من كل:\n"
            "أكلتُ الرغيفَ نصفَه.\n\n"

            "🔹 مثال الاشتمال:\n"
            "أعجبني الطالبُ أدبُه."
        ),
    },

    "tawabi": {
        "title": "🟢 التوابع",
        "text": (
            "📚 التوابع\n\n"
            "هي الكلمات التي تتبع ما قبلها في الإعراب.\n\n"

            "🔹 النعت.\n"
            "🔹 العطف.\n"
            "🔹 التوكيد.\n"
            "🔹 البدل.\n\n"

            "💡 قاعدة:\n"
            "التابع يأخذ حكم متبوعه الإعرابي."
        ),
    },

    "jumlah_shart": {
        "title": "🟠 جملة الشرط",
        "text": (
            "📚 جملة الشرط\n\n"
            "تتكون غالباً من:\n\n"
            "🔹 أداة الشرط.\n"
            "🔹 فعل الشرط.\n"
            "🔹 جواب الشرط.\n\n"

            "🔹 مثال:\n"
            "من يجتهدْ ينجحْ.\n\n"

            "من: أداة شرط.\n"
            "يجتهدْ: فعل الشرط.\n"
            "ينجحْ: جواب الشرط."
        ),
    },

    "fiil_madi": {
        "title": "🔵 الفعل الماضي",
        "text": (
            "📚 الفعل الماضي\n\n"
            "🔹 التعريف:\n"
            "فعل يدل على حدوث شيء في الزمن الماضي.\n\n"

            "🔹 أمثلة:\n"
            "كتبَ، قرأَ، ذهبَ، نجحَ.\n\n"

            "🔹 مثال:\n"
            "ذهبَ الطالبُ إلى المدرسةِ.\n\n"

            "ذهبَ: فعل ماضٍ."
        ),
    },

    "fiil_amr": {
        "title": "🟣 فعل الأمر",
        "text": (
            "📚 فعل الأمر\n\n"
            "🔹 التعريف:\n"
            "فعل يطلب به حصول الفعل في المستقبل.\n\n"

            "🔹 أمثلة:\n"
            "اكتبْ، اقرأْ، اجلسْ، ادرسْ.\n\n"

            "🔹 مثال:\n"
            "اقرأْ الكتابَ.\n\n"

            "اقرأْ: فعل أمر مبني على السكون."
        ),
    },

"fiil_mudari": {
        "title": "🟢 الفعل المضارع",
        "text": (
            "📚 الفعل المضارع\n\n"
            "🔹 التعريف:\n"
            "فعل يدل على حدث يقع في الحال أو الاستقبال.\n\n"

            "🔹 أمثلة:\n"
            "يكتبُ، يقرأُ، يذهبُ، ينجحُ.\n\n"

            "💡 ملاحظة:\n"
            "قد يكون مرفوعاً أو منصوباً أو مجزوماً."
        ),
    },

    "signs": {
        "title": "🔴 علامات الإعراب",
        "text": (
            "📚 علامات الإعراب\n\n"
            "🔹 الرفع:\n"
            "الضمة، الواو، الألف، ثبوت النون.\n\n"

            "🔹 النصب:\n"
            "الفتحة، الألف، الياء، الكسرة، حذف النون.\n\n"

            "🔹 الجر:\n"
            "الكسرة، الياء، الفتحة.\n\n"

            "🔹 الجزم:\n"
            "السكون، حذف حرف العلة، حذف النون."
        ),
    },

    "sentence_parse": {
        "title": "🟡 خطوات الإعراب",
        "text": (
            "📚 خطوات الإعراب\n\n"
            "1️⃣ حدد نوع الجملة.\n"
            "2️⃣ حدد الفعل إن وجد.\n"
            "3️⃣ ابحث عن الفاعل.\n"
            "4️⃣ حدد المفعول به إن وجد.\n"
            "5️⃣ ابحث عن المبتدأ والخبر في الجملة الاسمية.\n"
            "6️⃣ انتبه إلى النواسخ والتوابع وحروف الجر.\n"
            "7️⃣ حدد علامة الإعراب المناسبة.\n\n"

            "💡 نصيحة:\n"
            "لا تبدأ بعلامة الإعراب قبل معرفة وظيفة الكلمة في الجملة."
        ),
    },

    "rhetoric_intro": {
        "title": "🎨 مدخل إلى البلاغة",
        "text": (
            "📚 البلاغة\n\n"
            "هي العلم الذي يبحث في مطابقة الكلام لمقتضى الحال مع فصاحته.\n\n"

            "ومن أشهر علومها:\n"
            "🔹 علم المعاني.\n"
            "🔹 علم البيان.\n"
            "🔹 علم البديع.\n\n"

            "💡 الهدف:\n"
            "فهم جمال التعبير ودقة اختيار الألفاظ والأساليب."
        ),
    },

    "tashbih": {
        "title": "🟣 التشبيه",
        "text": (
            "📚 التشبيه\n\n"
            "🔹 التعريف:\n"
            "إلحاق شيء بشيء آخر في صفة مشتركة بينهما باستخدام أداة أو بدونها.\n\n"

            "🔹 مثال:\n"
            "العلمُ كالنورِ.\n\n"

            "العلم: مشبه.\n"
            "النور: مشبه به.\n"
            "الكاف: أداة التشبيه.\n"
            "النور/الإضاءة: وجه الشبه بحسب السياق."
        ),
    },

    "istiara": {
        "title": "🔵 الاستعارة",
        "text": (
            "📚 الاستعارة\n\n"
            "🔹 التعريف:\n"
            "تشبيه حذف أحد طرفيه.\n\n"

            "🔹 مثال:\n"
            "رأيتُ أسداً يخطبُ في الناس.\n\n"

            "إذا كان المقصود رجلاً شجاعاً، فقد استُعير لفظ «أسد» له.\n\n"

            "💡 ملاحظة:\n"
            "السياق هو الذي يحدد المقصود البلاغي."
        ),
    },

    "kinaya": {
        "title": "🟢 الكناية",
        "text": (
            "📚 الكناية\n\n"
            "🔹 التعريف:\n"
            "تعبير يقصد به معنى ملازم للمعنى الظاهر مع إمكان إرادة المعنى الظاهر.\n\n"

            "🔹 مثال:\n"
            "فلانٌ طويلُ النجاد.\n\n"

            "قد يراد بها طول القامة بحسب السياق.\n\n"

            "💡 ملاحظة:\n"
            "الكناية تعتمد على العلاقة واللازم بين المعنى الظاهر والمقصود."
        ),
    },

    "tibaq": {
        "title": "🟠 الطباق",
        "text": (
            "📚 الطباق\n\n"
            "🔹 التعريف:\n"
            "الجمع بين لفظين متضادين في المعنى.\n\n"

            "🔹 مثال:\n"
            "يحيي ويميت.\n\n"

            "يحيي ↔ يميت: طباق.\n\n"

            "💡 الفائدة البلاغية:\n"
            "تقوية المعنى وإبرازه بالمقابلة."
        ),
    },

    "muqabala": {
        "title": "🟣 المقابلة",
        "text": (
            "📚 المقابلة\n\n"
            "🔹 التعريف:\n"
            "الإتيان بمعانٍ متعددة ثم الإتيان بما يقابلها على الترتيب.\n\n"

            "🔹 الفائدة:\n"
            "توضيح المعنى وتقويته وإحداث تناسق بلاغي."
        ),
    },

    "jinas": {
        "title": "🔵 الجناس",
        "text": (
            "📚 الجناس\n\n"
            "🔹 التعريف:\n"
            "تشابه لفظين أو أكثر في النطق أو بعضه مع اختلاف المعنى.\n\n"

"🔹 الفائدة:\n"
            "إحداث جرْس موسيقي وجمال لفظي."
        ),
    },

    "saj": {
        "title": "🟢 السجع",
        "text": (
            "📚 السجع\n\n"
            "🔹 التعريف:\n"
            "توافق الفواصل في الكلام المنثور في الحرف الأخير غالباً.\n\n"

            "🔹 الفائدة:\n"
            "إضفاء موسيقى لفظية وجمال على النثر."
        ),
    },

    "qafiya": {
        "title": "🟡 القافية",
        "text": (
            "📚 القافية\n\n"
            "🔹 التعريف:\n"
            "الأصوات والحروف التي يختم بها البيت الشعري وفق قواعد علم العروض.\n\n"

            "🔹 أهميتها:\n"
            "تساعد في بناء الإيقاع الشعري والمحافظة على وحدة القصيدة."
        ),
    },

    "bahr": {
        "title": "🟣 بحور الشعر",
        "text": (
            "📚 بحور الشعر العربي\n\n"
            "من أشهر البحور:\n\n"
            "🔹 الطويل.\n"
            "🔹 البسيط.\n"
            "🔹 الكامل.\n"
            "🔹 الوافر.\n"
            "🔹 المتقارب.\n"
            "🔹 الرجز.\n"
            "🔹 الرمل.\n"
            "🔹 الخفيف.\n\n"

            "💡 ملاحظة:\n"
            "لكل بحر تفعيلات ونظام إيقاعي خاص."
        ),
    },

    "prosody_intro": {
        "title": "🪶 مدخل إلى العروض",
        "text": (
            "📚 علم العروض\n\n"
            "هو العلم الذي وضع قواعد أوزان الشعر العربي وتمييز صحيح الوزن من مكسوره.\n\n"

            "🔹 يعتمد على التفعيلات.\n"
            "🔹 يدرس الزحافات والعلل.\n"
            "🔹 يساعد في معرفة البحر الشعري.\n\n"

            "💡 ملاحظة:\n"
            "تقطيع البيت يحتاج إلى النطق الفعلي للكلمات لا إلى الكتابة الإملائية وحدها."
        ),
    },

    "dictionary_intro": {
        "title": "📖 المعجم",
        "text": (
            "📚 كيف نبحث عن معنى الكلمة؟\n\n"
            "1️⃣ حدد الكلمة في سياقها.\n"
            "2️⃣ ارجعها إلى أصلها إن كانت مشتقة.\n"
            "3️⃣ ابحث عن معناها المعجمي.\n"
            "4️⃣ قارن المعاني بحسب السياق.\n\n"

            "💡 ملاحظة:\n"
            "قد يكون للكلمة الواحدة أكثر من معنى."
        ),
    },

    "morphology_intro": {
        "title": "⚖️ مدخل إلى الصرف",
        "text": (
            "📚 علم الصرف\n\n"
            "يهتم ببنية الكلمة وما يطرأ عليها من تغييرات.\n\n"

            "🔹 الميزان الصرفي.\n"
            "🔹 الاشتقاق.\n"
            "🔹 المجرد والمزيد.\n"
            "🔹 الإعلال والإبدال.\n"
            "🔹 التصغير والنسب.\n\n"

            "💡 الهدف:\n"
            "فهم بنية الكلمة وعلاقتها بمعناها."
        ),
    },

    "mizan_sarfi": {
        "title": "🟠 الميزان الصرفي",
        "text": (
            "📚 الميزان الصرفي\n\n"
            "🔹 التعريف:\n"
            "مقياس وضعه علماء الصرف لمعرفة أصول الكلمة وزوائدها.\n\n"

            "🔹 أصله:\n"
            "فَعَلَ.\n\n"

            "🔹 مثال:\n"
            "كتب = فعل.\n"
            "كاتب = فاعل.\n"
            "مكتوب = مفعول.\n\n"

            "💡 ملاحظة:\n"
            "الميزان يساعد على معرفة الحروف الأصلية والزائدة."
        ),
    },

    "mujarrad_mazid": {
        "title": "🔵 المجرد والمزيد",
        "text": (
            "📚 الفعل المجرد والمزيد\n\n"
            "🔹 المجرد:\n"
            "ما كانت حروفه الأصلية دون زيادة.\n\n"

            "كتب، جلس، خرج.\n\n"

            "🔹 المزيد:\n"
            "ما زيد على حروفه الأصلية حرف أو أكثر.\n\n"

            "أكرم، استخرج، قاتل.\n\n"

            "💡 الفائدة:\n"
            "الزيادة في المبنى قد تدل على زيادة أو تغير في المعنى."
        ),
    },

    "ishtiqaq": {
        "title": "🟢 الاشتقاق",
        "text": (
            "📚 الاشتقاق\n\n"
            "🔹 التعريف:\n"
            "أخذ كلمة من أخرى مع وجود مناسبة في اللفظ والمعنى.\n\n"

            "🔹 مثال:\n"
            "كتب، كاتب، مكتوب، كتاب، مكتبة.\n\n"

            "💡 ملاحظة:\n"
            "تجمع الكلمات المشتقة عادةً مادة لغوية مشتركة."
        ),
    },

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

"i3lal": {
        "title": "🟣 الإعلال",
        "text": (
            "📚 الإعلال\n\n"
            "🔹 التعريف:\n"
            "تغييرات صرفية تطرأ على حروف العلة لأسباب صوتية وصرفية.\n\n"

            "🔹 حروف العلة:\n"
            "الألف، الواو، الياء.\n\n"

            "💡 ملاحظة:\n"
            "للإعلال أنواع وقواعد تفصيلية متعددة."
        ),
    },

    "ibdal": {
        "title": "🟡 الإبدال",
        "text": (
            "📚 الإبدال\n\n"
            "🔹 التعريف:\n"
            "تغيير حرف بحرف آخر وفق قاعدة صرفية.\n\n"

            "🔹 ملاحظة:\n"
            "له مواضع محددة في بنية بعض الكلمات."
        ),
    },

    "tas

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
        prompt = f"""
أنت مساعد أكاديمي عربي لقسم «سير الأعلام».
اكتب نبذة دقيقة ومختصرة عن الشخصية التالية: {name}

مهم:
- لا تخترع معلومات.
- إذا كان الاسم غامضاً أو لا تستطيع تحديد الشخصية بثقة، اذكر أن الاسم غير واضح واطلب تحديد الشخصية.
- اجعل الجواب مناسباً للطلاب.
- أخرج النص فقط.

التنسيق:
🏺 الاسم:
📅 العصر:
📚 المجال:

نبذة:
...

🪶 أبرز المؤلفات/الآثار:
...
"""
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
        prompt = f"""
اكتب سيرة أكاديمية عربية منظمة للشخصية: {name}

لا تخمّن. إذا كان الاسم غير واضح أو توجد شخصيات متعددة بالاسم، اذكر ذلك واطلب التحديد.
غطِّ فقط ما يمكن دعمه بثقة، وبالعناوين التالية:

📚 حياته وآثاره
🧬 نشأته ونسبه
🎓 طلبه للعلم وشيوخه
📚 علمه ومكانته
🪶 أبرز مؤلفاته
👥 تلاميذه ومن تأثر بهم
🏛️ أهم محطات حياته
💡 أبرز أفكاره وإسهاماته
🕊️ وفاته
📌 أثره في اللغة والأدب
📚 مصادر ومراجع للتوسع

اكتب بلغة عربية واضحة ومناسبة للطلاب، ولا تضع روابط مخترعة.
"""
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

            "💡 ملاحظة:\n"
            "الجملة الاسمية الأساسية تتكون غالباً من مبتدأ وخبر."
        ),
    },

    "kana": {
        "title": "🔵 كان وأخواتها",
        "text": (
            "📚 كان وأخواتها\n\n"
            "🔹 التعريف:\n"
            "أفعال ناسخة تدخل على الجملة الاسمية، فترفع المبتدأ "
            "ويسمى اسمها، وتنصب الخبر ويسمى خبرها.\n\n"

            "🔹 من أخوات كان:\n"
            "كان، أصبح، أمسى، أضحى، ظل، بات، صار، ليس، "
            "ما زال، ما دام.\n\n"

            "🔹 القاعدة:\n"
            "اسم كان وأخواتها: مرفوع.\n"
            "خبر كان وأخواتها: منصوب.\n\n"

            "🔹 مثال:\n"
            "كانَ الجوُّ جميلاً.\n\n"

            "الجوُّ: اسم كان مرفوع.\n"
            "جميلاً: خبر كان منصوب.\n\n"

            "💡 احفظها:\n"
            "كان وأخواتها = ترفع الأول وتنصب الثاني."
        ),
    },

    "inna": {
        "title": "🟢 إن وأخواتها",
        "text": (
            "📚 إن وأخواتها\n\n"
            "🔹 التعريف:\n"
            "حروف ناسخة تدخل على الجملة الاسمية، فتنصب المبتدأ "
            "ويسمى اسمها، وترفع الخبر ويسمى خبرها.\n\n"

            "🔹 من أخوات إن:\n"
            "إنَّ، أنَّ، كأنَّ، لكنَّ، ليتَ، لعلَّ.\n\n"

            "🔹 القاعدة:\n"
            "اسم إن وأخواتها: منصوب.\n"
            "خبر إن وأخواتها: مرفوع.\n\n"

            "🔹 مثال:\n"
            "إنَّ الطالبَ مجتهدٌ.\n\n"

            "الطالبَ: اسم إن منصوب.\n"
            "مجتهدٌ: خبر إن مرفوع.\n\n"

            "💡 احفظها:\n"
            "إن وأخواتها = تنصب الأول وترفع الثاني."
        ),
    },

    "fael": {
        "title": "🔴 الفاعل",
        "text": (
            "📚 الفاعل\n\n"
            "🔹 التعريف:\n"
            "الفاعل هو الاسم الذي قام بالفعل أو اتصف به.\n\n"

            "🔹 القاعدة:\n"
            "الفاعل مرفوع دائماً.\n\n"

            "🔹 مثال:\n"
            "كتبَ الطالبُ الدرسَ.\n\n"

            "الطالبُ: فاعل مرفوع وعلامة رفعه الضمة.\n\n"

            "🔹 مثال آخر:\n"
            "نجحَ الطالبانِ.\n\n"

            "الطالبانِ: فاعل مرفوع وعلامة رفعه الألف لأنه مثنى.\n\n"

            "💡 طريقة اكتشافه:\n"
            "اسأل: من الذي قام بالفعل؟"
        ),
    },

    "naeb": {
        "title": "🟠 نائب الفاعل",
        "text": (
            "📚 نائب الفاعل\n\n"
            "🔹 التعريف:\n"
            "اسم يأتي بعد الفعل المبني للمجهول، ويحل محل الفاعل المحذوف.\n\n"

"🔹 القاعدة:\n"
            "نائب الفاعل مرفوع دائماً.\n\n"

            "🔹 مثال:\n"
            "كُتِبَ الدرسُ.\n\n"

            "الدرسُ: نائب فاعل مرفوع.\n\n"

            "🔹 مثال آخر:\n"
            "كُرِّمَ الطالبانِ.\n\n"

            "الطالبانِ: نائب فاعل مرفوع بالألف لأنه مثنى.\n\n"

            "💡 ملاحظة:\n"
            "عند بناء الفعل للمجهول يُحذف الفاعل ويأتي نائب الفاعل مكانه."
        ),
    },

    "mafool": {
        "title": "🟣 المفعول به",
        "text": (
            "📚 المفعول به\n\n"
            "🔹 التعريف:\n"
            "اسم يدل على من وقع عليه فعل الفاعل.\n\n"

            "🔹 القاعدة:\n"
            "المفعول به منصوب.\n\n"

            "🔹 مثال:\n"
            "قرأَ الطالبُ الكتابَ.\n\n"

            "الكتابَ: مفعول به منصوب وعلامة نصبه الفتحة.\n\n"

            "🔹 طريقة اكتشافه:\n"
            "اسأل: ماذا فعل الفاعل؟ أو وقع الفعل على ماذا؟\n\n"

            "💡 مثال:\n"
            "شربَ الطفلُ الماءَ.\n"
            "الماءَ هو الشيء الذي وقع عليه فعل الشرب."
        ),
    },

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
            "عادَ الطالبُ مسروراً.\n\n"

            "مسروراً: حال منصوب، يبين هيئة الطالب عند عودته.\n\n"

            "🔹 طريقة اكتشافه:\n"
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
            "📚 التمييز\n\n"
            "🔹 التعريف:\n"
            "اسم نكرة يوضح كلمة أو معنى مبهماً قبله.\n\n"

            "🔹 القاعدة:\n"
            "التمييز يكون منصوباً في كثير من استعمالاته.\n\n"

            "🔹 مثال:\n"
            "اشتريتُ عشرينَ كتاباً.\n\n"

            "كتاباً: تمييز منصوب.\n"
            "وهو يوضح المقصود بالعدد عشرين.\n\n"

            "🔹 مثال آخر:\n"
            "ازدادَ الطالبُ علماً.\n\n"

            "علماً: تمييز منصوب.\n\n"

            "💡 ملاحظة:\n"
            "التمييز يزيل الإبهام عن كلمة أو جملة قبله."
        ),
    },

    "mafool_mutlaq": {
        "title": "🟦 المفعول المطلق",
        "text": (
            "📚 المفعول المطلق\n\n"
            "🔹 التعريف:\n"
            "مصدر منصوب يأتي من لفظ الفعل، ويستخدم للتوكيد "
            "أو بيان النوع أو العدد.\n\n"

            "🔹 أنواعه:\n"
            "1. مؤكد للفعل.\n"
            "2. مبين للنوع.\n"
            "3. مبين للعدد.\n\n"

            "🔹 مثال:\n"
            "نجحَ الطالبُ نجاحاً.\n\n"

            "نجاحاً: مفعول مطلق منصوب، مؤكد للفعل.\n\n"

            "🔹 مثال:\n"
            "سارَ الجنديُّ سيرَ الأبطالِ.\n\n"

            "سيرَ: مفعول مطلق مبين للنوع."
        ),
    },

    "mafool_liajlih": {
        "title": "🟥 المفعول لأجله",
        "text": (
            "📚 المفعول لأجله\n\n"
            "🔹 التعريف:\n"
            "مصدر منصوب يبين سبب حدوث الفعل.\n\n"

            "🔹 القاعدة:\n"
            "يجيب غالباً عن سؤال: لماذا؟\n\n"

            "🔹 مثال:\n"
            "درستُ طلباً للنجاح.\n\n"

"طلباً: مفعول لأجله منصوب، لأنه يبين سبب الدراسة.\n\n"

            "🔹 مثال آخر:\n"
            "سافرتُ طلباً للعلم.\n\n"

            "طلباً: مفعول لأجله منصوب.\n\n"

            "💡 طريقة اكتشافه:\n"
            "اسأل: لماذا حدث الفعل؟"
        ),
    },

    "asmaa_khamsa": {
        "title": "🟪 الأسماء الخمسة",
        "text": (
            "📚 الأسماء الخمسة\n\n"
            "🔹 هي:\n"
            "أب، أخ، حم، فو، ذو.\n\n"

            "🔹 علامات إعرابها:\n"
            "ترفع بالواو.\n"
            "تنصب بالألف.\n"
            "تجر بالياء.\n\n"

            "🔹 مثال الرفع:\n"
            "جاءَ أبوك.\n"
            "أبوك: فاعل مرفوع بالواو.\n\n"

            "🔹 مثال النصب:\n"
            "رأيتُ أباك.\n"
            "أباك: مفعول به منصوب بالألف.\n\n"

            "🔹 مثال الجر:\n"
            "مررتُ بأبيك.\n"
            "أبيك: اسم مجرور بالياء.\n\n"

            "💡 ملاحظة:\n"
            "لها شروط خاصة حتى تعرب بالحروف."
        ),
    },

    "dual": {
        "title": "🟩 المثنى",
        "text": (
            "📚 المثنى\n\n"
            "🔹 التعريف:\n"
            "اسم يدل على اثنين أو اثنتين بزيادة ألف ونون "
            "أو ياء ونون في آخره.\n\n"

            "🔹 علامات الإعراب:\n"
            "يرفع بالألف.\n"
            "ينصب بالياء.\n"
            "يجر بالياء.\n\n"

            "🔹 مثال الرفع:\n"
            "جاءَ الطالبانِ.\n"
            "الطالبانِ: فاعل مرفوع بالألف.\n\n"

            "🔹 مثال النصب:\n"
            "رأيتُ الطالبينِ.\n"
            "الطالبينِ: مفعول به منصوب بالياء.\n\n"

            "🔹 مثال الجر:\n"
            "مررتُ بالطالبينِ.\n"
            "الطالبينِ: اسم مجرور بالياء."
        ),
    },

    "masculine_plural": {
        "title": "🟧 جمع المذكر السالم",
        "text": (
            "📚 جمع المذكر السالم\n\n"
            "🔹 التعريف:\n"
            "ما دل على أكثر من اثنين بزيادة واو ونون أو ياء ونون "
            "مع بقاء مفرده سالماً.\n\n"

            "🔹 علامات الإعراب:\n"
            "يرفع بالواو.\n"
            "ينصب بالياء.\n"
            "يجر بالياء.\n\n"

            "🔹 مثال الرفع:\n"
            "حضرَ المعلمونَ.\n"
            "المعلمونَ: فاعل مرفوع بالواو.\n\n"

            "🔹 مثال النصب:\n"
            "كرّمتُ المعلمينَ.\n"
            "المعلمينَ: مفعول به منصوب بالياء.\n\n"

            "🔹 مثال الجر:\n"
            "سلّمتُ على المعلمينَ.\n"
            "المعلمينَ: اسم مجرور بالياء."
        ),
    },

    "feminine_plural": {
        "title": "🟥 جمع المؤنث السالم",
        "text": (
            "📚 جمع المؤنث السالم\n\n"
            "🔹 التعريف:\n"
            "ما دل على أكثر من اثنتين بزيادة ألف وتاء على مفرده.\n\n"

            "🔹 علامات الإعراب:\n"
            "يرفع بالضمة.\n"
            "ينصب بالكسرة نيابة عن الفتحة.\n"
            "يجر بالكسرة.\n\n"

            "🔹 مثال الرفع:\n"
            "حضرتِ الطالباتُ.\n"
            "الطالباتُ: فاعل مرفوع بالضمة.\n\n"

            "🔹 مثال النصب:\n"
            "رأيتُ الطالباتِ.\n"
            "الطالباتِ: مفعول به منصوب بالكسرة نيابة عن الفتحة.\n\n"

            "🔹 مثال الجر:\n"
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

async def check_access(
    update,
    context,
):

    user = update.effective_user

    if not user:
        return False

    try:
        user_id = user.id

        if is_admin(user_id):
            return True

        if await is_subscribed(user_id):
            return True

        markup = sub_markup()

        if update.callback_query:
            await show(
                update.callback_query,
                SUB_TEXT,
                markup,
            )

        elif update.message:
            await update.message.reply_text(
                SUB_TEXT,
                reply_markup=markup,
            )

        return False

    except Exception:

        logger.exception(
            "Access check failed."
        )

        return False


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

        "🔄 تريد تحليل النص بطريقة

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

            "💡 ملاحظة:\n"
            "الجملة الاسمية الأساسية تتكون غالباً من مبتدأ وخبر."
        ),
    },

    "kana": {
        "title": "🔵 كان وأخواتها",
        "text": (
            "📚 كان وأخواتها\n\n"
            "🔹 التعريف:\n"
            "أفعال ناسخة تدخل على الجملة الاسمية، فترفع المبتدأ "
            "ويسمى اسمها، وتنصب الخبر ويسمى خبرها.\n\n"

            "🔹 من أخوات كان:\n"
            "كان، أصبح، أمسى، أضحى، ظل، بات، صار، ليس، "
            "ما زال، ما دام.\n\n"

            "🔹 القاعدة:\n"
            "اسم كان وأخواتها: مرفوع.\n"
            "خبر كان وأخواتها: منصوب.\n\n"

            "🔹 مثال:\n"
            "كانَ الجوُّ جميلاً.\n\n"

            "الجوُّ: اسم كان مرفوع.\n"
            "جميلاً: خبر كان منصوب.\n\n"

            "💡 احفظها:\n"
            "كان وأخواتها = ترفع الأول وتنصب الثاني."
        ),
    },

"inna": {
        "title": "🟢 إن وأخواتها",
        "text": (
            "📚 إن وأخواتها\n\n"
            "🔹 التعريف:\n"
            "حروف ناسخة تدخل على الجملة الاسمية، فتنصب المبتدأ "
            "ويسمى اسمها، وترفع الخبر ويسمى خبرها.\n\n"

            "🔹 من أخوات إن:\n"
            "إنَّ، أنَّ، كأنَّ، لكنَّ، ليتَ، لعلَّ.\n\n"

            "🔹 القاعدة:\n"
            "اسم إن وأخواتها: منصوب.\n"
            "خبر إن وأخواتها: مرفوع.\n\n"

            "🔹 مثال:\n"
            "إنَّ الطالبَ مجتهدٌ.\n\n"

            "الطالبَ: اسم إن منصوب.\n"
            "مجتهدٌ: خبر إن مرفوع.\n\n"

            "💡 احفظها:\n"
            "إن وأخواتها = تنصب الأول وترفع الثاني."
        ),
    },

    "fael": {
        "title": "🔴 الفاعل",
        "text": (
            "📚 الفاعل\n\n"
            "🔹 التعريف:\n"
            "الفاعل هو الاسم الذي قام بالفعل أو اتصف به.\n\n"

            "🔹 القاعدة:\n"
            "الفاعل مرفوع دائماً.\n\n"

            "🔹 مثال:\n"
            "كتبَ الطالبُ الدرسَ.\n\n"

            "الطالبُ: فاعل مرفوع وعلامة رفعه الضمة.\n\n"

            "🔹 مثال آخر:\n"
            "نجحَ الطالبانِ.\n\n"

            "الطالبانِ: فاعل مرفوع وعلامة رفعه الألف لأنه مثنى.\n\n"

            "💡 طريقة اكتشافه:\n"
            "اسأل: من الذي قام بالفعل؟"
        ),
    },

    "naeb": {
        "title": "🟠 نائب الفاعل",
        "text": (
            "📚 نائب الفاعل\n\n"
            "🔹 التعريف:\n"
            "اسم يأتي بعد الفعل المبني للمجهول، ويحل محل الفاعل المحذوف.\n\n"

            "🔹 القاعدة:\n"
            "نائب الفاعل مرفوع دائماً.\n\n"

            "🔹 مثال:\n"
            "كُتِبَ الدرسُ.\n\n"

            "الدرسُ: نائب فاعل مرفوع.\n\n"

            "🔹 مثال آخر:\n"
            "كُرِّمَ الطالبانِ.\n\n"

            "الطالبانِ: نائب فاعل مرفوع بالألف لأنه مثنى.\n\n"

            "💡 ملاحظة:\n"
            "عند بناء الفعل للمجهول يُحذف الفاعل ويأتي نائب الفاعل مكانه."
        ),
    },

    "mafool": {
        "title": "🟣 المفعول به",
        "text": (
            "📚 المفعول به\n\n"
            "🔹 التعريف:\n"
            "اسم يدل على من وقع عليه فعل الفاعل.\n\n"

            "🔹 القاعدة:\n"
            "المفعول به منصوب.\n\n"

            "🔹 مثال:\n"
            "قرأَ الطالبُ الكتابَ.\n\n"

            "الكتابَ: مفعول به منصوب وعلامة نصبه الفتحة.\n\n"

            "🔹 طريقة اكتشافه:\n"
            "اسأل: ماذا فعل الفاعل؟ أو وقع الفعل على ماذا؟\n\n"

            "💡 مثال:\n"
            "شربَ الطفلُ الماءَ.\n"
            "الماءَ هو الشيء الذي وقع عليه فعل الشرب."
        ),
    },

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
            "عادَ الطالبُ مسروراً.\n\n"

            "مسروراً: حال منصوب، يبين هيئة الطالب عند عودته.\n\n"

            "🔹 طريقة اكتشافه:\n"
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
            "📚 التمييز\n\n"
            "🔹 التعريف:\n"
            "اسم نكرة يوضح كلمة أو معنى مبهماً قبله.\n\n"

            "🔹 القاعدة:\n"
            "التمييز يكون منصوباً في كثير من استعمالاته.\n\n"

            "🔹 مثال:\n"
            "اشتريتُ عشرينَ كتاباً.\n\n"

            "كتاباً: تمييز منصوب.\n"
            "وهو يوضح المقصود بالعدد عشرين.\n\n"

            "🔹 مثال آخر:\n"
            "ازدادَ الطالبُ علماً.\n\n"

            "علماً: تمييز منصوب.\n\n"

            "💡 ملاحظة:\n"
            "التمييز يزيل الإبهام عن كلمة أو جملة قبله."
        ),
    },

InlineKeyboardButton(
                    "🗑 حذف قطعة",
                    callback_data=f"outfit:delete:{gender}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "✨ تنسيق إطلالة",
                    callback_data=f"outfit:style:{gender}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="outfit",
                ),
            ],
        ]
    )


async def show_outfit_menu(
    q,
    gender,
):

    title = (
        "🖤 قسم For Him"
        if gender == "him"
        else "🤍 قسم For Her"
    )

    await show(
        q,
        (
            f"{title}\n\n"
            "اختر العملية التي تريد تنفيذها:"
        ),
        outfit_menu_markup(gender),
    )


async def handle_outfit(
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

    data = q.data or ""

    if data == "outfit":

        await show(
            q,
            (
                "👗 منسق الإطلالات\n\n"
                "اختر القسم المناسب:"
            ),
            outfit_gender_markup(),
        )

        return

    if data.startswith("outfit:him"):

        await show_outfit_menu(
            q,
            "him",
        )

        return

    if data.startswith("outfit:her"):

        await show_outfit_menu(
            q,
            "her",
        )

        return

    parts = data.split(":")

    if len(parts) < 3:
        return

    action = parts[1]
    gender = parts[2]

    if action == "add":

        context.user_data[
            "outfit_gender"
        ] = gender

        context.user_data[
            "outfit_waiting"
        ] = True

        await show(
            q,
            (
                "➕ إضافة قطعة ملابس\n\n"
                "أرسل اسم القطعة أو وصفها.\n\n"
                "مثال:\n"
                "قميص أبيض\n"
                "بنطلون أسود\n"
                "حذاء رياضي أبيض"
            ),
        )

        return

    if action == "list":

        try:

            items = db.get_outfits(
                q.from_user.id,
                gender,
            )

        except Exception:

            logger.exception(
                "Could not get outfits."
            )

            items = []

        if not items:

            await show(
                q,
                (
                    "👕 ملابسي\n\n"
                    "لا توجد قطع مضافة حالياً."
                ),
                outfit_menu_markup(gender),
            )

            return

        lines = [
            "👕 ملابسي\n"
        ]

        for index, item in enumerate(
            items,
            1,
        ):

            lines.append(
                f"{index}. {item}"
            )

        await show(
            q,
            "\n".join(lines),
            outfit_menu_markup(gender),
        )

        return

    if action == "delete":

        context.user_data[
            "outfit_gender"
        ] = gender

        context.user_data[
            "outfit_delete"
        ] = True

        await show(
            q,
            (
                "🗑 حذف قطعة\n\n"
                "أرسل رقم القطعة التي تريد حذفها."
            ),
            outfit_menu_markup(gender),
        )

        return

    if action == "style":

        context.user_data[
            "outfit_gender"
        ] = gender

        await show(
            q,
            (
                "✨ تنسيق إطلالة\n\n"
                "جاري تجهيز الإطلالة..."
            ),
        )

        try:

            items = db.get_outfits(
                q.from_user.id,
                gender,
            )

        except Exception:

            logger.exception(
                "Could not load outfit items."
            )

            items = []

        if not items:

await show(
                q,
                (
                    "❌ لا توجد قطع كافية.\n\n"
                    "أضف بعض الملابس أولاً."
                ),
                outfit_menu_markup(gender),
            )

            return

        if not GEMINI_API_KEY:

            await show(
                q,
                (
                    "❌ خدمة الذكاء الاصطناعي غير مفعلة حالياً."
                ),
                outfit_menu_markup(gender),
            )

            return

        prompt = (
            "نسّق إطلالة أنيقة ومتناسقة اعتماداً على "
            "قطع الملابس التالية:\n\n"
            + "\n".join(
                f"- {item}"
                for item in items
            )
            + "\n\n"
            "اذكر القطع المختارة، ولماذا تتناسق، "
            "وأضف نصيحة بسيطة للألوان والإكسسوارات."
        )

        try:

            result = await ask_gemini(
                prompt,
                model=OUTFIT_MODEL,
            )

        except Exception:

            logger.exception(
                "Outfit AI error."
            )

            result = (
                "❌ تعذر تنسيق الإطلالة حالياً.\n\n"
                "حاول مرة أخرى."
            )

        await show(
            q,
            "✨ الإطلالة المقترحة\n\n" + result,
            outfit_menu_markup(gender),
        )

        return


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
            (
                "❌ ما عندي نص للتحليل.\n\n"
                "أرسل نص أو صورة أو تسجيل صوتي أولاً."
            ),
            main_menu(
                q.from_user.id
            ),
        )

        return

    await show(
        q,
        (
            "⏳ جاري التحليل...\n\n"
            + AI_MODES[mode]
        ),
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
# AI Menu
# ============================================================

def ai_markup():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📌 الإعراب",
                    callback_data="ai:grammar",
                ),
                InlineKeyboardButton(
                    "🎨 البلاغة",
                    callback_data="ai:rhetoric",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⚖️ الصرف",
                    callback_data="ai:morphology",
                ),
                InlineKeyboardButton(
                    "📖 المعجم",
                    callback_data="ai:dictionary",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📝 الشرح",
                    callback_data="ai:explain",

),
                InlineKeyboardButton(
                    "🪶 العروض",
                    callback_data="ai:prosody",
                ),
            ],
            [
                InlineKeyboardButton(
                    "👤 الشاعر والعصر",
                    callback_data="ai:poet",
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


async def show_ai_menu(
    q,
):

    await show(
        q,
        (
            "🤖 التحليل بالذكاء الاصطناعي\n\n"
            "اختر نوع التحليل الذي تريده:"
        ),
        ai_markup(),
    )


# ============================================================
# Grammar Menu
# ============================================================

def grammar_markup():

    rows = []

    for key, value in ARABIC_RULES.items():

        rows.append(
            [
                InlineKeyboardButton(
                    value["title"],
                    callback_data=f"rule:{key}",
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

    return InlineKeyboardMarkup(
        rows
    )


async def show_grammar_menu(
    q,
):

    await show(
        q,
        (
            "📚 قواعد اللغة العربية\n\n"
            "اختر القاعدة التي تريد شرحها:"
        ),
        grammar_markup(),
    )


async def handle_rule(
    update,
    context,
    key,
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

    rule = ARABIC_RULES.get(key)

    if not rule:

        await show_grammar_menu(q)

        return

    await show(
        q,
        rule["text"],
        grammar_markup(),
    )

items = db.get_wardrobe_items(
            q.from_user.id,
            gender,
        )

    except Exception:

        logger.exception(
            "Could not get wardrobe items."
        )

        items = []

    title = (
        "🖤 For Him"
        if gender == "him"
        else "🤍 For Her"
    )

    if not items:

        await show(
            q,
            (
                "👕 ملابسي\n\n"
                f"{title}\n\n"
                "ما عندك قطع محفوظة حالياً."
            ),
            outfit_menu_markup(gender),
        )

        return

    lines = [
        "👕 ملابسي",
        "",
        title,
        "",
    ]

    for index, item in enumerate(
        items,
        1,
    ):

        if isinstance(item, dict):

            category = item.get(
                "category",
                "",
            )

            color = item.get(
                "color",
                "",
            )

            lines.append(
                f"{index}. {category} - {color}"
            )

        else:

            lines.append(
                f"{index}. {item}"
            )

    await show(
        q,
        "\n".join(lines),
        outfit_manage_markup(gender),
    )


async def outfit_manage(
    update,
    context,
    gender,
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
        (
            "🗑️ إدارة الملابس\n\n"
            "اختر العملية التي تريد تنفيذها:"
        ),
        outfit_manage_markup(gender),
    )


async def outfit_delete_menu(
    update,
    context,
    gender,
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

    try:

        items = db.get_wardrobe_items(
            q.from_user.id,
            gender,
        )

    except Exception:

        logger.exception(
            "Could not load wardrobe items."
        )

        items = []

    if not items:

        await show(
            q,
            "❌ لا توجد قطع لحذفها.",
            outfit_manage_markup(gender),
        )

        return

    rows = []

    for index, item in enumerate(
        items,
        1,
    ):

        if isinstance(item, dict):

            category = item.get(
                "category",
                "",
            )

            color = item.get(
                "color",
                "",
            )

            label = (
                f"{index}. {category} - {color}"
            )

        else:

            label = f"{index}. {item}"

        rows.append(
            [
                InlineKeyboardButton(
                    f"🗑️ {label}",
                    callback_data=(
                        f"outfit:delete_item:"
                        f"{gender}:{index - 1}"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                "⬅️ رجوع",
                callback_data=f"outfit:manage:{gender}",
            )
        ]
    )

    await show(
        q,
        (
            "🗑️ حذف قطعة\n\n"
            "اختر القطعة التي تريد حذفها:"
        ),
        InlineKeyboardMarkup(rows),
    )


async def outfit_delete_item(
    update,
    context,
    gender,
    index,
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

    try:

        items = db.get_wardrobe_items(
            q.from_user.id,
            gender,
        )

    except Exception:

        logger.exception(
            "Could not load wardrobe items."
        )

        await show(
            q,
            "❌ تعذر تحميل الملابس.",
            outfit_manage_markup(gender),
        )

        return

    try:

        index = int(index)

    except Exception:

await show(
            q,
            "❌ رقم القطعة غير صحيح.",
            outfit_manage_markup(gender),
        )

        return

    if index < 0 or index >= len(items):

        await show(
            q,
            "❌ القطعة غير موجودة.",
            outfit_manage_markup(gender),
        )

        return

    item = items[index]

    try:

        if isinstance(item, dict):

            item_id = item.get(
                "id"
            )

        else:

            item_id = None

        if item_id is not None:

            db.delete_wardrobe_item(
                q.from_user.id,
                item_id,
            )

        else:

            db.delete_wardrobe_item_by_index(
                q.from_user.id,
                gender,
                index,
            )

    except Exception:

        logger.exception(
            "Could not delete wardrobe item."
        )

        await show(
            q,
            (
                "❌ ما قدرت أحذف القطعة حالياً.\n\n"
                "حاول مرة ثانية."
            ),
            outfit_manage_markup(gender),
        )

        return

    await show(
        q,
        "✅ تم حذف القطعة بنجاح.",
        outfit_manage_markup(gender),
    )


async def outfit_clear(
    update,
    context,
    gender,
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
        (
            "⚠️ مسح كل الملابس\n\n"
            "هل أنت متأكد من حذف جميع القطع؟"
        ),
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ نعم، احذف الكل",
                        callback_data=(
                            f"outfit:clear_confirm:{gender}"
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "❌ إلغاء",
                        callback_data=(
                            f"outfit:manage:{gender}"
                        ),
                    ),
                ],
            ]
        ),
    )


async def outfit_clear_confirm(
    update,
    context,
    gender,
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

    try:

        db.clear_wardrobe(
            q.from_user.id,
            gender,
        )

    except Exception:

        logger.exception(
            "Could not clear wardrobe."
        )

        await show(
            q,
            "❌ تعذر مسح الملابس.",
            outfit_manage_markup(gender),
        )

        return

    await show(
        q,
        "✅ تم مسح جميع الملابس.",
        outfit_menu_markup(gender),
    )


# ============================================================
# Outfit AI Generation
# ============================================================

async def outfit_generate(
    update,
    context,
    gender,
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

    try:

        items = db.get_wardrobe_items(
            q.from_user.id,
            gender,
        )

    except Exception:

        logger.exception(
            "Could not load wardrobe items."
        )

        items = []

    if not items:

        await show(
            q,
            (
                "❌ ما عندك ملابس محفوظة بعد.\n\n"
                "أضف بعض القطع أولاً حتى أقدر "
                "أنسق لك إطلالة."
            ),
            outfit_menu_markup(gender),
        )

        return

    title = (
        "For Him"
        if gender == "him"
        else "For Her"
    )

    clothes = []

    for item in items:

        if isinstance(item, dict):

            category = item.get(
                "category",
                "",
            )

color = item.get(
                "color",
                "",
            )

            clothes.append(
                f"- {category}: {color}"
            )

        else:

            clothes.append(
                f"- {item}"
            )

    prompt = (
        "أنت خبير تنسيق أزياء.\n\n"
        f"القسم: {title}\n\n"
        "هذه الملابس المتوفرة لدى المستخدم:\n"
        + "\n".join(clothes)
        + "\n\n"
        "أنشئ إطلالة متناسقة باستخدام الملابس "
        "المتوفرة فقط.\n"
        "اذكر القطع المختارة، وتناسق الألوان، "
        "وأي ملاحظة مفيدة باختصار."
    )

    await show(
        q,
        "⏳ جاري تنسيق الإطلالة...",
    )

    try:

        result = await ask_gemini(
            prompt,
            model=OUTFIT_MODEL,
        )

    except Exception:

        logger.exception(
            "Outfit generation error."
        )

        result = (
            "❌ تعذر إنشاء التنسيق حالياً.\n\n"
            "حاول مرة ثانية."
        )

    await show(
        q,
        (
            "✨ التنسيق المقترح\n\n"
            + result
        ),
        outfit_menu_markup(gender),
    )

callback_data=f"outfit:manage:{gender}",
                    )
                ],
            ]
        ),
    )


async def outfit_clear_yes(
    update,
    context,
    gender,
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

    try:

        db.clear_wardrobe(
            q.from_user.id,
            gender,
        )

    except Exception:

        logger.exception(
            "Could not clear wardrobe."
        )

        await show(
            q,
            "❌ تعذر حذف الملابس حالياً.",
            outfit_manage_markup(gender),
        )

        return

    await show(
        q,
        (
            "✅ تم حذف جميع الملابس المحفوظة.\n\n"
            "يمكنك البدء بإضافة قطع جديدة."
        ),
        outfit_menu_markup(gender),
    )


# ============================================================
# AI Text Processing
# ============================================================

def build_ai_prompt(
    mode,
    text,
):

    mode_name = AI_MODES.get(
        mode,
        AI_MODES["explain"],
    )

    return (
        "أنت مساعد متخصص باللغة العربية.\n\n"
        f"نوع التحليل المطلوب: {mode_name}\n\n"
        "حلل النص التالي بدقة ووضوح، "
        "واجعل الإجابة منظمة وسهلة القراءة.\n\n"
        "النص:\n"
        f"{text}\n\n"
        "لا تخترع معلومات غير موجودة في النص."
    )


async def ask_ai(
    mode,
    text,
):

    prompt = build_ai_prompt(
        mode,
        text,
    )

    return await ask_gemini(
        prompt,
        model=TEXT_MODEL,
    )


# ============================================================
# Gemini Helpers
# ============================================================

async def ask_gemini(
    prompt,
    model=None,
):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    if genai is None:

        raise RuntimeError(
            "Gemini library is not available."
        )

    model_name = (
        model
        or TEXT_MODEL
    )

    def _run():

        client = genai.Client(
            api_key=GEMINI_API_KEY,
        )

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )

        text = getattr(
            response,
            "text",
            None,
        )

        if text:

            return text.strip()

        return str(response)

    return await asyncio.to_thread(
        _run
    )


# ============================================================
# Main Menu
# ============================================================

def main_menu(
    user_id=None,
):

    rows = [

        [
            InlineKeyboardButton(
                "🤖 الذكاء الاصطناعي",
                callback_data="ai",
            ),
        ],

        [
            InlineKeyboardButton(
                "📚 قواعد اللغة",
                callback_data="grammar",
            ),
        ],

        [
            InlineKeyboardButton(
                "👕 Outfit",
                callback_data="outfit",
            ),
        ],

        [
            InlineKeyboardButton(
                "🎯 تحدي القواعد",
                callback_data="challenge",
            ),
        ],

    ]

    if user_id is not None and is_admin(
        user_id
    ):

        rows.append(
            [
                InlineKeyboardButton(
                    "⚙️ لوحة الإدارة",
                    callback_data="admin",
                )
            ]
        )

    return InlineKeyboardMarkup(
        rows
    )


async def show_main_menu(
    update,
    context,
):

    q = update.callback_query

    if q:

        await safe_answer(q)

        await show(
            q,
            (
                "🏠 القائمة الرئيسية\n\n"
                "اختر الخدمة التي تريدها:"
            ),
            main_menu(
                q.from_user.id
            ),
        )

        return

    message = update.message

    if message:

await message.reply_text(
            (
                "🏠 القائمة الرئيسية\n\n"
                "اختر الخدمة التي تريدها:"
            ),
            reply_markup=main_menu(
                message.from_user.id
            ),
            parse_mode="Markdown",
        )


# ============================================================
# Start Command
# ============================================================

async def start(
    update,
    context,
):

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
            "Could not save start user."
        )

    await update.message.reply_text(
        (
            "👋 أهلاً وسهلاً بك.\n\n"
            "🤖 مساعدك الذكي للغة العربية\n\n"
            "اختر الخدمة من القائمة:"
        ),
        reply_markup=main_menu(
            user.id
        ),
        parse_mode="Markdown",
    )


# ============================================================
# Cancel
# ============================================================

async def cancel(
    update,
    context,
):

    context.user_data.clear()

    if update.message:

        await update.message.reply_text(
            "✅ تم إلغاء العملية.",
            reply_markup=main_menu(
                update.effective_user.id
            ),
        )

    elif update.callback_query:

        await safe_answer(
            update.callback_query
        )

        await show(
            update.callback_query,
            "✅ تم إلغاء العملية.",
            main_menu(
                update.effective_user.id
            ),
        )

async def outfit_clear_yes( update, context, gender, ):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    try:

        db.clear_wardrobe(
            q.from_user.id,
            gender,
        )

    except Exception:

        logger.exception(
            "Could not clear wardrobe."
        )

        await show(
            q,
            "❌ تعذر مسح الملابس حالياً.",
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ رجوع",
                            callback_data=f"outfit:{gender}",
                        )
                    ]
                ]
            ),
        )

        return

    await show(
        q,
        "✅ تم مسح جميع الملابس المحفوظة لهذا القسم.",
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "➕ إضافة ملابس",
                        callback_data=f"outfit:add:{gender}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع",
                        callback_data=f"outfit:{gender}",
                    )
                ],
            ]
        ),
    )


def _generate_outfit_sync( gender, items, ):

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY غير موجود."
        )

    if image_client is None:
        raise RuntimeError(
            "تعذر الاتصال بخدمة Gemini."
        )

    if not items:
        raise RuntimeError(
            "لا توجد ملابس محفوظة."
        )

    gender_name = (
        "رجل"
        if gender == "him"
        else "امرأة"
    )

    wardrobe_lines = []

    for item in items:

        wardrobe_lines.append(
            f"- {item['category']} | اللون: {item['color']}"
        )

    wardrobe_text = "\n".join(
        wardrobe_lines
    )

    prompt = f""" أنت مساعد متخصص بتنسيق الملابس. المستخدم يريد تنسيق ملابس لـ {gender_name}. هذه هي الملابس التي يملكها المستخدم فعلاً: {wardrobe_text} مهم جداً: - استخدم فقط القطع الموجودة في القائمة. - لا تخترع قطعة ملابس غير موجودة. - لا تضف لوناً غير اللون المسجل للقطعة. - يمكنك عدم استخدام بعض القطع إذا لم تكن مناسبة. - كوّن تنسيقاً عملياً ومتناسقاً. - إذا لم توجد قطع كافية، قل ذلك بوضوح ولا تخترع قطعاً. - لا تذكر أسعاراً أو ماركات غير موجودة. - لا تقترح شراء ملابس. - أجب بالعربية. - اجعل النتيجة مختصرة ومرتبة. أعطني: 👕 التنسيق المقترح - القطعة: - اللون: - القطعة: - اللون: ثم: 🎨 لماذا هذا التنسيق؟ سطران أو ثلاثة فقط. ثم: 👟 الإكسسوارات أو الحذاء: استخدم فقط ما هو موجود في القائمة، وإذا لم يوجد اكتب: لا توجد قطعة مناسبة محفوظة. مهم: لا تستخدم أي قطعة غير موجودة في القائمة. """

    interaction = image_client.interactions.create(
        model=OUTFIT_MODEL,
        input=prompt,
        generation_config={
            "thinking_level": "minimal",
            "max_output_tokens": 900,
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
            "Gemini لم يرجع تنسيقاً."
        )

    return result.strip()


async def generate_outfit( gender, items, ):

    return await asyncio.to_thread(
        _generate_outfit_sync,
        gender,
        items,
    )


async def outfit_generate( update, context, gender, ):

    q = update.callback_query

    if not q:
        return

    await safe_answer(q)

    if not await check_access(
        update,
        context,
    ):
        return

    try:

        items = db.get_wardrobe_items(
            q.from_user.id,
            gender,
        )

    except Exception:

        logger.exception(
            "Could not load wardrobe for outfit generation."
        )

await show(
            q,
            "❌ تعذر قراءة ملابسك حالياً.",
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ رجوع",
                            callback_data=f"outfit:{gender}",
                        )
                    ]
                ]
            ),
        )

        return

    if not items:

        await show(
            q,
            "👕 ما عندك ملابس محفوظة بعد.\n\n"
            "أضف القطع وألوانها أولاً حتى أقدر "
            "أسوي لك تنسيق.",
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "➕ إضافة قطعة",
                            callback_data=f"outfit:add:{gender}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ رجوع",
                            callback_data=f"outfit:{gender}",
                        )
                    ],
                ]
            ),
        )

        return

    await show(
        q,
        "✨ جاري تنسيق ملابسك...\n\n"
        "أستخدم فقط الملابس والألوان المحفوظة عندك.",
    )

    try:

        ok, result = await generate_outfit(
            q.from_user.id,
            gender,
        )

        if not ok:
            raise RuntimeError(result)

    except Exception as error:

        logger.exception(
            "Outfit generation failed."
        )

        error_text = str(error).upper()

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):

            message = (
                "⚠️ تم الوصول إلى حد الطلبات مؤقتاً.\n\n"
                "انتظر قليلاً وحاول مرة ثانية."
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
                "⏱️ Gemini تأخر بالاستجابة.\n\n"
                "حاول مرة ثانية 🔄"
            )

        else:

            message = (
                "❌ ما قدرت أجهز تنسيق الملابس حالياً.\n\n"
                "حاول مرة ثانية 🔄"
            )

        await show(
            q,
            message,
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 إعادة التنسيق",
                            callback_data=f"outfit:generate:{gender}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "👕 ملابسي",
                            callback_data=f"outfit:list:{gender}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ رجوع",
                            callback_data=f"outfit:{gender}",
                        )
                    ],
                ]
            ),
        )

        return

    context.user_data[
        "last_outfit_result"
    ] = result

    await show(
        q,
        result,
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✨ تنسيق ثاني",
                        callback_data=f"outfit:generate:{gender}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "👕 ملابسي",
                        callback_data=f"outfit:list:{gender}",

),
                    InlineKeyboardButton(
                        "➕ إضافة قطعة",
                        callback_data=f"outfit:add:{gender}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع",
                        callback_data=f"outfit:{gender}",
                    )
                ],
            ]
        ),
    )


# ============================================================
# Voice Transcription
# ============================================================

def _transcribe_voice_file( file_path ):

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


async def transcribe_voice( file_path ):

    return await asyncio.to_thread(
        _transcribe_voice_file,
        file_path,
    )


# ============================================================
# Voice Handler
# ============================================================

async def handle_voice( update: Update, context: ContextTypes.DEFAULT_TYPE, ):

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
        r"^
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*
$",
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

    prompt = """ أنت مولّد أسئلة لتحدي قواعد اللغة العربية للطلاب. أنشئ سؤال قواعد عربية واحد فقط. الشروط: - السؤال يجب أن يكون واضحاً ومناسباً للطالب. - استخدم قواعد عربية مدرسية صحيحة. - اجعل السؤال متوسط الصعوبة. - يجب أن يحتوي على 4 خيارات فقط. - خيار واحد فقط صحيح. - لا تجعل أكثر من خيار صحيحاً. - لا تستخدم معلومات غامضة أو خلافية. - بعد السؤال، اكتب شرحاً قصيراً جداً لسبب صحة الإجابة. أمثلة لأنواع الأسئلة: - تحديد المفعول به. - تحديد الفاعل. - تحديد المبتدأ والخبر. - علامة الإعراب. - نوع الجملة. - كان وأخواتها. - إن وأخواتها. - النعت. - الحال. - التمييز. - المفعول المطلق. - المفعول لأجله. - جمع المذكر السالم. - المثنى. - الأسماء الخمسة. أعد النتيجة بصيغة JSON فقط، بدون أي كلام خارج JSON. الشكل المطلوب بالضبط: { "question": "السؤال هنا", "options": [ "الخيار الأول", "الخيار الثاني", "الخيار الثالث", "الخيار الرابع" ], "correct": 0, "explanation": "شرح مختصر." } مهم: - correct يجب أن يكون رقماً من 0 إلى 3. - options يجب أن تحتوي على 4 عناصر بالضبط. - لا تستخدم Markdown. - لا تضع `json. """

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
            "🧠 تحدي قواعد اللغة العربية\n\n"
            "⏳ جاري تجهيز السؤال الأول...",
            parse_mode="Markdown",
        )

    else:

        try:

            await q.edit_message_text(
                "🧠 تحدي قواعد اللغة العربية\n\n"
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

        "🧠 تحدي قواعد اللغة العربية\n\n"

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

            "✅ إجابة صحيحة!\n\n"

f"إجابتك: {selected_text}\n\n"

            f"📚 الشرح:\n"
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

            "❌ إجابة غير صحيحة\n\n"

            f"إجابتك: {selected_text}\n\n"

            f"✅ الإجابة الصحيحة: {correct_text}\n\n"

            f"📚 الشرح:\n"
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

            + "🏁 انتهى التحدي!\n\n"

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

        "🧠 تحدي قواعد اللغة العربية\n\n"

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

        "📚 شرح قواعد اللغة العربية\n\n"
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
                            callback_data="m",
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
                    )
                ],
            ]),
        )

    # ========================================================
    # Character Biography - Detailed Life
    # ========================================================

    if data == "character:detail":

        await safe_answer(q)

        name = context.user_data.get(
            "character_name"
        )

        if not name:

            return await show(
                q,
                "❌ ما عندي اسم شخصية محفوظ حالياً.",
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🔎 البحث عن شخصية",
                            callback_data="character",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🏠 القائمة الرئيسية",
                            callback_data="m",
                        )
                    ],
                ]),
            )

        await show(
            q,
            "⏳ جاري تجهيز المعلومات التفصيلية...",
        )

        try:

            ok, result = await character.get_character_detail(
                name
            )

        except Exception:

            logger.exception(
                "Character detail failed."
            )

            ok = False

            result = (
                "❌ تعذر جلب المعلومات التفصيلية حالياً."
            )

        await show(
            q,
            result,
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔎 شخصية أخرى",
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
            ]),
        )

        return

    # ========================================================
    # Character Biography
    # ========================================================

    if data == "character":

        await safe_answer(q)

        context.user_data[
            "character_await"
        ] = True

        return await show(
            q,
            "👤 نبذة عن شخصية\n\n"
            "اكتب اسم الشخصية التي تريد معرفة نبذة عنها.\n\n"
            "مثال:\n"
            "الجاحظ\n"
            "المتنبي\n"
            "ابن خلدون",
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "❌ إلغاء",
                        callback_data="m",
                    )
                ],
            ]),
        )

    # ========================================================
    # Outfit
    # ========================================================

    if data.startswith("outfit"):

        parts = data.split(":")

        if len(parts) == 1:

            return await outfit_menu(
                update,
                context,
            )

        if len(parts) >= 2:

            action = parts[1]

            if action in (
                "him",
                "her",
            ):

                return await outfit_gender_menu(
                    update,
                    context,
                    action,
                )

            if action == "add":

                gender = (
                    parts[2]
                    if len(parts) > 2
                    else "him"
                )

return await outfit_add(
                    update,
                    context,
                    gender,
                )

            if action == "list":

                gender = (
                    parts[2]
                    if len(parts) > 2
                    else "him"
                )

                return await outfit_list(
                    update,
                    context,
                    gender,
                )

            if action == "manage":

                gender = (
                    parts[2]
                    if len(parts) > 2
                    else "him"
                )

                return await outfit_manage(
                    update,
                    context,
                    gender,
                )

            if action == "delete":

                gender = (
                    parts[2]
                    if len(parts) > 2
                    else "him"
                )

                return await outfit_delete_menu(
                    update,
                    context,
                    gender,
                )

            if action == "clear":

                gender = (
                    parts[2]
                    if len(parts) > 2
                    else "him"
                )

                return await outfit_clear(
                    update,
                    context,
                    gender,
                )

            if action == "clear_yes":

                gender = (
                    parts[2]
                    if len(parts) > 2
                    else "him"
                )

                return await outfit_clear_yes(
                    update,
                    context,
                    gender,
                )

            if action == "generate":

                gender = (
                    parts[2]
                    if len(parts) > 2
                    else "him"
                )

                return await outfit_generate(
                    update,
                    context,
                    gender,
                )

    # ========================================================
    # Admin Router
    # ========================================================

    if data.startswith("admin:"):

        if not is_admin(
            q.from_user.id
        ):

            await safe_answer(
                q,
                "غير مسموح."
            )

            return

        return await admin_router(
            update,
            context,
        )

    # ========================================================
    # Reports
    # ========================================================

    if data.startswith("report:"):

        return await reports.callback_router(
            update,
            context,
        )

    # ========================================================
    # Quiz
    # ========================================================

    if data.startswith("quiz:"):

        return await quiz.callback_router(
            update,
            context,
        )

    # ========================================================
    # Unknown callback
    # ========================================================

    await safe_answer(q)

    logger.warning(
        "Unknown callback data: %s",
        data,
    )


# ============================================================
# Error Handler
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        logger.error(
            "Unhandled exception: %s",
            context.error,
            exc_info=context.error,
        )

    except Exception:

        logger.exception(
            "Could not log application error."
        )

    try:

        if isinstance(
            update,
            Update,
        ):

            if update.callback_query:

await update.callback_query.answer(
                    "❌ حدث خطأ. حاول مرة ثانية.",
                    show_alert=False,
                )

            elif update.message:

                await update.message.reply_text(
                    "❌ حدث خطأ غير متوقع.\n\n"
                    "حاول مرة ثانية."
                )

    except Exception:

        pass


# ============================================================
# Main Application
# ============================================================

def build_application():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN غير موجود في Environment Variables."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
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
            handle_image,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Document.IMAGE,
            handle_image,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_document,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text,
        )
    )

    application.add_error_handler(
        error_handler
    )

    return application


def main():

    logger.info(
        "Starting Telegram bot..."
    )

    application = build_application()

    logger.info(
        "Bot application built successfully."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if name == "main":

    main()

name = str(context.user_data.get("character_name", "")).strip()
        if not name:
            return await show(
                q,
                "❌ لم أتمكن من تحديد اسم الشخصية.",
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ رجوع", callback_data="character")]
                ]),
            )

        await show(
            q,
            "📚 حياته وآثاره\n\n⏳ جاري إعداد السيرة التفصيلية...",
        )

        ok, result = await character.get_character_detail(name)

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
                [InlineKeyboardButton("❌ إلغاء", callback_data="m")],
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

if name == "main":

    main()
