# -*- coding: utf-8 -*-
"""لوحة الأدمن: القوائم والأزرار."""

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup

import db
from ui import back_markup, show


ACTIONS = {"ad", "ap", "ak", "ay", "ds", "users", "userspage"}


PICKER_TITLES = {
    "sum": "🔗 اختر المادة لإضافة ملخص:",
    "q": "❓ اختر المادة لإضافة أسئلة:",
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


# ============================================================
# لوحة الأدمن
# ============================================================

def panel_markup():
    return Markup(
        [
            [Btn("➕ مادة جديدة", callback_data="ad:newsubj")],
            [Btn("🔗 إضافة ملخص", callback_data="ap:sum")],
            [Btn("❓ إضافة أسئلة", callback_data="ap:q")],
            [Btn("🗑 حذف ملخص", callback_data="ap:dsum")],
            [Btn("🧹 مسح أسئلة مادة", callback_data="ap:cq")],
            [Btn("🗑 حذف مادة", callback_data="ap:dsub")],

            # المستخدمون
            [Btn("👥 المستخدمون", callback_data="users")],

            [Btn("🔙 القائمة الرئيسية", callback_data="m")],
        ]
    )


# ============================================================
# تأكيد العمليات
# ============================================================

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


# ============================================================
# المستخدمون
# ============================================================

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

    rows = []

    if page > 0:
        rows.append(
            [
                Btn(
                    "⬅️ السابق",
                    callback_data=f"userspage:{page - 1}",
                )
            ]
        )

    if page < pages - 1:
        if page > 0:
            rows[-1].append(
                Btn(
                    "التالي ➡️",
                    callback_data=f"userspage:{page + 1}",
                )
            )
        else:
            rows.append(
                [
                    Btn(
                        "التالي ➡️",
                        callback_data=f"userspage:{page + 1}",
                    )
                ]
            )

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

    text = f"👤 {name}\n"
    text += f"🆔 {user_id}\n"

    if username:
        text += f"🔗 @{username}\n"

    if section:
        text += f"📚 القسم: {section}\n"

    if last_seen:
        text += f"🕐 آخر استخدام: {last_seen}"

    return text


async def show_users(q, page=0):
    total = db.get_users_count()

    if total == 0:
        return await show(
            q,
            "👥 المستخدمون\n\n"
            "لا يوجد مستخدمون مسجلون حالياً.",
            users_markup(0),
        )

    users = db.get_users_page(
        limit=USERS_PER_PAGE,
        offset=page * USERS_PER_PAGE,
    )

    pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE

    lines = [
        "👥 **المستخدمون**",
        "",
        f"📊 العدد الكلي: **{total}**",
        f"📄 الصفحة: **{page + 1} / {pages}**",
        "",
    ]

    for index, user in enumerate(users, start=1):
        lines.append(
            f"**{index + page * USERS_PER_PAGE}.** "
            + format_user(user)
        )
        lines.append("")

    return await show(
        q,
        "\n".join(lines).strip(),
        users_markup(page),
        parse_mode="Markdown",
    )


# ============================================================
# Router
# ============================================================

async def router(q, context, action, arg):

    # لوحة الأدمن
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

        context.user_data.pop("await", None)

        return await show(
            q,
            "⚙️ لوحة الأدمن:",
            panel_markup(),
        )

    # المستخدمون
    if action == "users":
        context.user_data.pop("await", None)
        return await show_users(q, 0)

    # صفحات المستخدمين
    if action == "userspage":
        try:
            page = int(arg)
        except (TypeError, ValueError):
            page = 0

        if page < 0:
            page = 0

        return await show_users(q, page)

    # اختيار مادة
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

    # اختيار مادة وتنفيذ الإجراء
    if action == "ak":
        kind, _, sid_s = arg.partition(":")

        return await pick_subject(
            q,
            context,
            kind,
            int(sid_s),
        )

    # تأكيد الحذف
    if action == "ay":
        kind, _, sid_s = arg.partition(":")

        sid = int(sid_s)

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

    # حذف ملخص
    if action == "ds":
        db.delete_summary(int(arg))

        await show(
            q,
            "✅ انحذف الملخص.",
            back_markup(
                "ad",
                "⚙️ لوحة الأدمن",
            ),
        )


# ============================================================
# اختيار المادة
# ============================================================

async def pick_subject(q, context, kind, sid):

    subj = db.get_subject(sid)

    if not subj:
        return await show(
            q,
            "⚠️ المادة غير موجودة.",
            back_markup("ad"),
        )

    name = subj["name"]

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

    if kind == "dsub":
        return await show(
            q,
            f"متأكد تبي تحذف مادة {name} بكل محتواها ونتائجها؟",
            confirm_markup(
                "dsub",
                sid,
            ),
        )
