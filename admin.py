-- coding: utf-8 --

"""لوحة الأدمن: القوائم والأزرار."""

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup

import db
from ui import back_markup, show

ACTIONS = {
"ad",
"ap",
"ak",
"ay",
"ds",
"users",
"userspage",
"mi",
}

PICKER_TITLES = {
"sum": "🔗 اختر المادة لإضافة ملخص:",
"q": "❓ اختر المادة لإضافة أسئلة:",
"mi": "🖼️ اختر المادة لإضافة أسئلة شهرية:",
"dsum": "🗑 اختر المادة لحذف ملخص منها:",
"cq": "🧹 اختر المادة لمسح كل أسئلتها:",
"dsub": "🗑 اختر المادة لحذفها (بكل ملخصاتها وأسئلتها):",
}

QUESTIONS_HELP = (
"أرسل الأسئلة بهذا الشكل (سطر فاضي بين كل سؤال):\n\n"
"ما علامة رفع المثنى؟\n- الألف *\n- الواو\n- الياء\n"
"شرح: المثنى يرفع بالألف.\n\n"
"الفاعل دائماً مرفوع؟\n- صح *\n- خطأ\n\n"
"• النجمة * بعد الخيار الصحيح\n"
"• سطر «شرح:» اختياري\n"
"• تقدر ترسل عدة أسئلة بنفس الرسالة\n\n"
"للإلغاء: /cancel"
)

============================================================

لوحة الأدمن

============================================================

def panel_markup():
return Markup(
[
[Btn("➕ مادة جديدة", callback_data="ad:newsubj")],
[Btn("🔗 إضافة ملخص", callback_data="ap:sum")],
[Btn("❓ إضافة أسئلة", callback_data="ap:q")],
[Btn("🖼️ إضافة أسئلة شهرية", callback_data="ap:mi")],
[Btn("🗑 حذف ملخص", callback_data="ap:dsum")],
[Btn("🧹 مسح أسئلة مادة", callback_data="ap:cq")],
[Btn("🗑 حذف مادة", callback_data="ap:dsub")],
[Btn("👥 المستخدمون", callback_data="users")],
[Btn("🔙 القائمة الرئيسية", callback_data="m")],
]
)

============================================================

قائمة نوع الأسئلة الشهرية

============================================================

def monthly_type_markup():
return Markup(
[
[
Btn(
"📚 أسئلة شهرية سابقة",
callback_data="mi:previous",
)
],
[
Btn(
"📝 أسئلة الشهر الحالي",
callback_data="mi:current",
)
],
[
Btn(
"🔙 رجوع",
callback_data="ad",
)
],
]
)

def monthly_section_markup():
return Markup(
[
[
Btn(
"☀️ صباحي",
callback_data="mis:morning",
),
Btn(
"🌙 مسائي",
callback_data="mis:evening",
),
],
[
Btn(
"🔙 رجوع",
callback_data="ap:mi",
)
],
]
)

============================================================

تأكيد العمليات

============================================================

def confirm_markup(kind, sid):
return Markup(
[
[
Btn(
"✅ نعم",
callback_data=f"ay:{kind}:{sid}",
),
Btn(
"❌ لا",
callback_data="ad",
),
]
]
)

============================================================

المستخدمون

============================================================

USERS_PER_PAGE = 8

def users_markup(page=0):
total = db.get_users_count()

if total <= 0:
    return Markup(
        [
            [
                Btn(
                    "🔄 تحديث",
                    callback_data="users",
                )
            ],
            [
                Btn(
                    "🔙 لوحة الأدمن",
                    callback_data="ad",
                )
            ],
        ]
    )

pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE

if page >= pages:
    page = pages - 1

rows = []

navigation = []

if page > 0:
    navigation.append(
        Btn(
            "⬅️ السابق",
            callback_data=f"userspage:{page - 1}",
        )
    )

if page < pages - 1:
    navigation.append(
        Btn(
            "التالي ➡️",
            callback_data=f"userspage:{page + 1}",
        )
    )

if navigation:
    rows.append(navigation)

rows.append(
    [
        Btn(
            "🔄 تحديث",
            callback_data=f"userspage:{page}",
        )
    ]
)

rows.append(
    [
        Btn(
            "🔙 لوحة الأدمن",
            callback_data="ad",
        )
    ]
)

return Markup(rows)

def format_user(user):
user_id = user["user_id"]
name = user["name"] or "بدون اسم"
username = user["username"]
section = user["section"]
last_seen = user["last_seen"]

lines = [
    f"👤 {name}",
    f"🆔 {user_id}",
]

if username:
    lines.append(f"🔗 @{username}")

if section:
    lines.append(f"📚 القسم: {section}")

if last_seen:
    lines.append(f"🕐 آخر استخدام: {last_seen}")

return "\n".join(lines)

async def show_users(q, page=0):
total = db.get_users_count()

if total == 0:
    return await show(
        q,
        "👥 المستخدمون\n\n"
        "لا يوجد مستخدمون مسجلون حالياً.",
        users_markup(0),
    )

pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE

if page < 0:
    page = 0

if page >= pages:
    page = pages - 1

users = db.get_users_page(
    limit=USERS_PER_PAGE,
    offset=page * USERS_PER_PAGE,
)

lines = [
    "👥 المستخدمون",
    "",
    f"📊 العدد الكلي: {total}",
    f"📄 الصفحة: {page + 1} / {pages}",
    "",
]

user_buttons = []

for index, user in enumerate(users, start=1):
    number = index + page * USERS_PER_PAGE

    lines.append(
        f"{number}. {format_user(user)}"
    )

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    user_id = user["user_id"]

    user_buttons.append(
        [
            Btn(
                f"👤 فتح حساب المستخدم {number}",
                url=f"tg://user?id={user_id}",
            )
        ]
    )

text = "\n".join(lines).strip()

keyboard = user_buttons

navigation = []

if page > 0:
    navigation.append(
        Btn(
            "⬅️ السابق",
            callback_data=f"userspage:{page - 1}",
        )
    )

if page < pages - 1:
    navigation.append(
        Btn(
            "التالي ➡️",
            callback_data=f"userspage:{page + 1}",
        )
    )

if navigation:
    keyboard.append(navigation)

keyboard.append(
    [
        Btn(
            "🔄 تحديث",
            callback_data=f"userspage:{page}",
        )
    ]
)

keyboard.append(
    [
        Btn(
            "🔙 لوحة الأدمن",
            callback_data="ad",
        )
    ]
)

return await show(
    q,
    text,
    Markup(keyboard),
)

============================================================

Router

============================================================

async def router(q, context, action, arg):

# --------------------------------------------------------
# لوحة الأدمن
# --------------------------------------------------------

if action == "ad":

    if arg == "newsubj":

        context.user_data["await"] = {
            "type": "subject"
        }

        return await show(
            q,
            "اكتب اسم المادة الجديدة:\n\n"
            "للإلغاء: /cancel",
        )

    context.user_data.pop(
        "await",
        None,
    )

    return await show(
        q,
        "⚙️ لوحة الأدمن:",
        panel_markup(),
    )

# --------------------------------------------------------
# المستخدمون
# --------------------------------------------------------

if action == "users":

    context.user_data.pop(
        "await",
        None,
    )

    return await show_users(
        q,
        0,
    )

# --------------------------------------------------------
# صفحات المستخدمين
# --------------------------------------------------------

if action == "userspage":

    try:
        page = int(arg)
    except (TypeError, ValueError):
        page = 0

    if page < 0:
        page = 0

    return await show_users(
        q,
        page,
    )

# --------------------------------------------------------
# اختيار مادة
# --------------------------------------------------------

if action == "ap":

    rows = [
        [
            Btn(
                s["name"],
                callback_data=f"ak:{arg}:{s['id']}",
            )
        ]
        for s in db.subjects()
    ]

    rows.append(
        [
            Btn(
                "🔙 رجوع",
                callback_data="ad",
            )
        ]
    )

    return await show(
        q,
        PICKER_TITLES.get(
            arg,
            "اختر المادة:",
        ),
        Markup(rows),
    )

# --------------------------------------------------------
# اختيار نوع الأسئلة الشهرية
# --------------------------------------------------------

if action == "mi":

    if arg == "previous":

        context.user_data["monthly_kind"] = {
            "quiz_type": db.MONTHLY_PREVIOUS,
            "section": db.SECTION_SHARED,
        }

        return await show(
            q,
            "📚 أسئلة شهرية سابقة\n\n"
            "أرسل الآن صورة الأسئلة.\n\n"
            "🖼️ أرسلها كصورة من Telegram.\n"
            "ويمكنك إضافة وصف أو اسم للامتحان في الـ Caption.\n\n"
            "للإلغاء: /cancel",
        )

    if arg == "current":

        return await show(
            q,
            "📝 أسئلة الشهر الحالي\n\n"
            "اختر القسم:",
            monthly_section_markup(),
        )

    return await show(
        q,
        "📝 اختر نوع الأسئلة الشهرية:",
        monthly_type_markup(),
    )

# --------------------------------------------------------
# اختيار قسم الأسئلة الحالية
# --------------------------------------------------------

if action == "mis":

    if arg not in ("morning", "evening"):
        return await show(
            q,
            "⚠️ القسم غير صالح.",
            back_markup("ad"),
        )

    context.user_data["monthly_kind"] = {
        "quiz_type": db.MONTHLY_CURRENT,
        "section": (
            db.SECTION_MORNING
            if arg == "morning"
            else db.SECTION_EVENING
        ),
    }

    section_name = (
        "☀️ الصباحي"
        if arg == "morning"
        else "🌙 المسائي"
    )

    return await show(
        q,
        f"📝 أسئلة الشهر الحالي — {section_name}\n\n"
        "أرسل الآن صورة الأسئلة.\n\n"
        "🖼️ أرسلها كصورة من Telegram.\n"
        "ويمكنك إضافة وصف أو اسم للامتحان في الـ Caption.\n\n"
        "للإلغاء: /cancel",
    )

# --------------------------------------------------------
# اختيار مادة وتنفيذ الإجراء
# --------------------------------------------------------

if action == "ak":

    kind, _, sid_s = arg.partition(":")

    try:
        sid = int(sid_s)
    except (TypeError, ValueError):
        return await show(
            q,
            "⚠️ رقم المادة غير صالح.",
            back_markup("ad"),
        )

    return await pick_subject(
        q,
        context,
        kind,
        sid,
    )

# --------------------------------------------------------
# تأكيد الحذف
# --------------------------------------------------------

if action == "ay":

    kind, _, sid_s = arg.partition(":")

    try:
        sid = int(sid_s)
    except (TypeError, ValueError):
        return await show(
            q,
            "⚠️ رقم المادة غير صالح.",
            back_markup("ad"),
        )

    if kind == "cq":

        db.clear_questions(sid)

        msg = "✅ انمسحت الأسئلة."

    elif kind == "dsub":

        db.delete_subject(sid)

        msg = "✅ انحذفت المادة."

    else:
        return

    return await show(
        q,
        msg,
        back_markup(
            "ad",
            "⚙️ لوحة الأدمن",
        ),
    )

# --------------------------------------------------------
# حذف ملخص
# --------------------------------------------------------

if action == "ds":

    try:
        sum_id = int(arg)
    except (TypeError, ValueError):
        return await show(
            q,
            "⚠️ رقم الملخص غير صالح.",
            back_markup("ad"),
        )

    db.delete_summary(sum_id)

    return await show(
        q,
        "✅ انحذف الملخص.",
        back_markup(
            "ad",
            "⚙️ لوحة الأدمن",
        ),
    )

============================================================

اختيار المادة

============================================================

async def pick_subject(q, context, kind, sid):

subj = db.get_subject(sid)

if not subj:

    return await show(
        q,
        "⚠️ المادة غير موجودة.",
        back_markup("ad"),
    )

name = subj["name"]

# --------------------------------------------------------
# إضافة ملخص
# --------------------------------------------------------

if kind == "sum":

    context.user_data["await"] = {
        "type": "summary",
        "sid": sid,
    }

    return await show(
        q,
        f"أرسل ملخص مادة {name}:\n\n"
        "• رابط (تقدر تكتب عنوان بالسطر الأول والرابط بالسطر الثاني)\n"
        "• أو ملف PDF (العنوان يكون بالتعليق caption)\n\n"
        "للإلغاء: /cancel",
    )

# --------------------------------------------------------
# إضافة أسئلة عادية
# --------------------------------------------------------

if kind == "q":

    context.user_data["await"] = {
        "type": "questions",
        "sid": sid,
    }

    return await show(
        q,
        f"❓ أسئلة مادة {name}\n\n"
        f"{QUESTIONS_HELP}",
    )

# --------------------------------------------------------
# إضافة أسئلة شهرية
# --------------------------------------------------------

if kind == "mi":

    return await show(
        q,
        f"🖼️ أسئلة شهرية — {name}\n\n"
        "اختر نوع الأسئلة:",
        monthly_type_markup(),
    )

# --------------------------------------------------------
# حذف ملخص
# --------------------------------------------------------

if kind == "dsum":

    items = db.summaries(sid)

    if not items:

        return await show(
            q,
            "ما في ملخصات لهذي المادة.",
            back_markup("ad"),
        )

    rows = [
        [
            Btn(
                f"🗑 {it['title']}",
                callback_data=f"ds:{it['id']}",
            )
        ]
        for it in items
    ]

    rows.append(
        [
            Btn(
                "🔙 رجوع",
                callback_data="ad",
            )
        ]
    )

    return await show(
        q,
        "اضغط على الملخص اللي تبي تحذفه:",
        Markup(rows),
    )

# --------------------------------------------------------
# مسح الأسئلة
# --------------------------------------------------------

if kind == "cq":

    n = db.count_questions(sid)

    return await show(
        q,
        f"متأكد تبي تمسح {n} سؤال من {name}؟",
        confirm_markup(
            "cq",
            sid,
        ),
    )

# --------------------------------------------------------
# حذف المادة
# --------------------------------------------------------

if kind == "dsub":

    return await show(
        q,
        f"متأكد تبي تحذف مادة {name} بكل محتواها ونتائجها؟",
        confirm_markup(
            "dsub",
            sid,
        ),
    )
