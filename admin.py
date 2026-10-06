"""لوحة الأدمن: القوائم والأزرار."""
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup
import db
from ui import back_markup, show


def cb_style(i):
    return ("primary", "success", "danger")[i % 3]

ACTIONS = {"ad", "ap", "ak", "ay", "ds", "users", "userspage", "mi", "mis", "mmanage", "mdelete"}

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

def panel_markup():
    return Markup([
        [Btn("➕ مادة جديدة", callback_data="ad:newsubj", style=cb_style(0))],
        [Btn("🔗 إضافة ملخص", callback_data="ap:sum", style=cb_style(1))],
        [Btn("❓ إضافة أسئلة", callback_data="ap:q", style=cb_style(2))],
        [Btn("🖼️ إضافة أسئلة شهرية", callback_data="ap:mi", style=cb_style(3))],
        [Btn("🗑️ إدارة الأسئلة الشهرية", callback_data="ap:mmanage", style=cb_style(4))],
        [Btn("🗑 حذف ملخص", callback_data="ap:dsum", style=cb_style(5))],
        [Btn("🧹 مسح أسئلة مادة", callback_data="ap:cq", style=cb_style(6))],
        [Btn("🗑 حذف مادة", callback_data="ap:dsub", style=cb_style(7))],
        [Btn("👥 المستخدمون", callback_data="users", style=cb_style(8))],
        [Btn("🔙 القائمة الرئيسية", callback_data="m", style=cb_style(9))],
    ])

def monthly_type_markup():
    return Markup([
        [Btn("📚 الأسئلة الشهرية للأعوام السابقة", callback_data="mi:previous", style=cb_style(10))],
        [Btn("📝 أسئلة الشهر الحالي", callback_data="mi:current", style=cb_style(11))],
        [Btn("🔙 رجوع", callback_data="ad", style=cb_style(12))],
    ])


def monthly_manage_markup():
    return Markup([
        [Btn("☀️ إدارة الأسئلة الشهرية الصباحية", callback_data="mmanage:morning", style=cb_style(13))],
        [Btn("🌙 إدارة الأسئلة الشهرية المسائية", callback_data="mmanage:evening", style=cb_style(14))],
        [Btn("📚 إدارة الأسئلة الشهرية للأعوام السابقة", callback_data="mmanage:previous", style=cb_style(15))],
        [Btn("🔙 رجوع", callback_data="ad", style=cb_style(16))],
    ])


def confirm_markup(kind, sid):
    return Markup([[
        Btn("✅ نعم", callback_data=f"ay:{kind}:{sid}", style=cb_style(17)),
        Btn("❌ لا", callback_data="ad", style=cb_style(18)),
    ]])

USERS_PER_PAGE = 8

def users_markup(page=0):
    total = db.get_users_count()
    if total <= 0:
        return Markup([[Btn("🔄 تحديث", callback_data="users", style=cb_style(19))], [Btn("🔙 لوحة الأدمن", callback_data="ad", style=cb_style(20))]])
    pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE
    if page >= pages:
        page = pages - 1
    rows = []
    navigation = []
    if page > 0:
        navigation.append(Btn("⬅️ السابق", callback_data=f"userspage:{page - 1}", style=cb_style(21)))
    if page < pages - 1:
        navigation.append(Btn("التالي ➡️", callback_data=f"userspage:{page + 1}", style=cb_style(22)))
    if navigation:
        rows.append(navigation)
    rows.append([Btn("🔄 تحديث", callback_data=f"userspage:{page}", style=cb_style(23))])
    rows.append([Btn("🔙 لوحة الأدمن", callback_data="ad", style=cb_style(24))])
    return Markup(rows)

def format_user(user):
    user_id = user["user_id"]
    name = user["name"] or "بدون اسم"
    username = user["username"]
    section = user["section"]
    last_seen = user["last_seen"]
    lines = [f"👤 {name}", f"🆔 {user_id}"]
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
        return await show(q, "👥 المستخدمون\n\nلا يوجد مستخدمون مسجلون حالياً.", users_markup(0))
    pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE
    page = max(0, min(page, pages - 1))
    users = db.get_users_page(limit=USERS_PER_PAGE, offset=page * USERS_PER_PAGE)
    lines = ["👥 المستخدمون", "", f"📊 العدد الكلي: {total}", f"📄 الصفحة: {page + 1} / {pages}", ""]
    user_buttons = []
    for index, user in enumerate(users, start=1):
        number = index + page * USERS_PER_PAGE
        lines.append(f"{number}. {format_user(user)}")
        lines.append("━━━━━━━━━━━━━━")
        user_buttons.append([Btn(f"👤 فتح حساب المستخدم {number}", url=f"tg://user?id={user['user_id']}", style=cb_style(25))])
    keyboard = user_buttons
    navigation = []
    if page > 0:
        navigation.append(Btn("⬅️ السابق", callback_data=f"userspage:{page - 1}", style=cb_style(26)))
    if page < pages - 1:
        navigation.append(Btn("التالي ➡️", callback_data=f"userspage:{page + 1}", style=cb_style(27)))
    if navigation:
        keyboard.append(navigation)
    keyboard.append([Btn("🔄 تحديث", callback_data=f"userspage:{page}", style=cb_style(28))])
    keyboard.append([Btn("🔙 لوحة الأدمن", callback_data="ad", style=cb_style(29))])
    return await show(q, "\n".join(lines).strip(), Markup(keyboard))

async def router(q, context, action, arg):
    if action == "ad":
        if arg == "newsubj":
            context.user_data["await"] = {"type": "subject"}
            return await show(q, "اكتب اسم المادة الجديدة:\n\nللإلغاء: /cancel")
        context.user_data.pop("await", None)
        return await show(q, "⚙️ لوحة الأدمن:", panel_markup())

    if action == "users":
        context.user_data.pop("await", None)
        return await show_users(q, 0)

    if action == "userspage":
        try:
            page = int(arg)
        except (TypeError, ValueError):
            page = 0
        return await show_users(q, max(0, page))

    if action == "ap":
        if arg == "mmanage":
            return await show(q, "🗑️ إدارة الأسئلة الشهرية\n\nاختر القسم:", monthly_manage_markup())
        rows = [[Btn(s["name"], callback_data=f"ak:{arg}:{s['id']}", style=cb_style(30))] for s in db.subjects()]
        rows.append([Btn("🔙 رجوع", callback_data="ad", style=cb_style(31))])
        return await show(q, PICKER_TITLES.get(arg, "اختر المادة:"), Markup(rows))

    if action == "mi":
        sid = context.user_data.get("monthly_sid")
        if not sid:
            return await show(q, "⚠️ انتهت جلسة اختيار المادة. ابدأ من لوحة الأدمن من جديد.", back_markup("ad"))

        if arg == "previous":
            upload_state = {
                "type": "monthly_image",
                "sid": sid,
                "quiz_type": db.MONTHLY_PREVIOUS,
                "section": db.SECTION_SHARED,
            }
            context.user_data["await"] = upload_state.copy()
            context.user_data["monthly_image_upload"] = upload_state.copy()
            return await show(
                q,
                "📚 أسئلة شهرية سابقة\n\n"
                "أرسل الآن صورة الأسئلة.\n\n"
                "🖼️ أرسلها كصورة من Telegram.\n"
                "ويمكنك إضافة وصف أو اسم للامتحان في الـ Caption.\n\n"
                "للإلغاء: /cancel"
            )

        if arg == "current":
            return await show(q, "📝 أسئلة الشهر الحالي\n\nاختر القسم:", monthly_section_markup())

        return await show(q, "📝 اختر نوع الأسئلة الشهرية:", monthly_type_markup())

    if action == "mis":
        if arg not in ("morning", "evening"):
            return await show(q, "⚠️ القسم غير صالح.", back_markup("ad"))

        sid = context.user_data.get("monthly_sid")
        if not sid:
            return await show(q, "⚠️ انتهت جلسة اختيار المادة. ابدأ من لوحة الأدمن من جديد.", back_markup("ad"))

        section = db.SECTION_MORNING if arg == "morning" else db.SECTION_EVENING
        upload_state = {
            "type": "monthly_image",
            "sid": sid,
            "quiz_type": db.MONTHLY_CURRENT,
            "section": section,
        }
        context.user_data["await"] = upload_state.copy()
        context.user_data["monthly_image_upload"] = upload_state.copy()

        section_name = "☀️ الصباحي" if arg == "morning" else "🌙 المسائي"
        return await show(
            q,
            f"📝 أسئلة الشهر الحالي — {section_name}\n\n"
            "أرسل الآن صورة الأسئلة.\n\n"
            "🖼️ أرسلها كصورة من Telegram.\n"
            "ويمكنك إضافة وصف أو اسم للامتحان في الـ Caption.\n\n"
            "للإلغاء: /cancel"
        )

    if action == "mmanage":
        if arg == "morning":
            quiz_type, section, title = db.MONTHLY_CURRENT, db.SECTION_MORNING, "☀️ الأسئلة الشهرية الصباحية"
        elif arg == "evening":
            quiz_type, section, title = db.MONTHLY_CURRENT, db.SECTION_EVENING, "🌙 الأسئلة الشهرية المسائية"
        elif arg == "previous":
            quiz_type, section, title = db.MONTHLY_PREVIOUS, db.SECTION_SHARED, "📚 الأسئلة الشهرية للأعوام السابقة"
        else:
            return await show(q, "⚠️ القسم غير صالح.", back_markup("ad"))

        context.user_data["monthly_manage"] = {"quiz_type": quiz_type, "section": section}
        rows = []
        for subject in db.subjects():
            sid = int(subject["id"])
            try:
                count = db.count_monthly_question_images(sid, quiz_type, section)
            except Exception:
                count = 0
            rows.append([Btn(f"{subject['name']}" + (f" ({count})" if count else ""), callback_data=f"mdelete:{quiz_type}:{section}:{sid}")])
        rows.append([Btn("🔙 رجوع", callback_data="ap:mmanage", style=cb_style(32))])
        return await show(q, f"🗑️ {title}\n\nاختر المادة:", Markup(rows))

    if action == "mdelete":
        parts = arg.split(":")
        if len(parts) != 3:
            return await show(q, "⚠️ بيانات الحذف غير صالحة.", back_markup("ad"))
        quiz_type, section, sid_s = parts
        try:
            sid = int(sid_s)
        except ValueError:
            return await show(q, "⚠️ رقم المادة غير صالح.", back_markup("ad"))
        items = db.monthly_question_images(sid, quiz_type, section)
        if not items:
            return await show(q, "❌ ماكو صور محفوظة لهذه المادة.", back_markup("ap:mmanage"))
        rows = []
        for item in items:
            image_id = int(item["id"])
            caption = (item["caption"] or "بدون اسم").strip()
            rows.append([Btn(f"🗑️ {image_id} — {caption[:45]}", callback_data=f"mdeleteone:{image_id}:{quiz_type}:{section}:{sid}", style=cb_style(33))])
        rows.append([Btn("🔙 رجوع", callback_data=f"mmanage:{'morning' if section == db.SECTION_MORNING else 'evening' if section == db.SECTION_EVENING else 'previous' if quiz_type == db.MONTHLY_PREVIOUS else 'final'}", style=cb_style(34))])
        return await show(q, "🗑️ اختر الصورة التي تريد حذفها:", Markup(rows))

    if action == "mdeleteone":
        parts = arg.split(":")
        if len(parts) != 4:
            return await show(q, "⚠️ بيانات الحذف غير صالحة.", back_markup("ad"))
        image_id, quiz_type, section, sid_s = parts
        try:
            image_id = int(image_id); sid = int(sid_s)
        except ValueError:
            return await show(q, "⚠️ رقم الصورة أو المادة غير صالح.", back_markup("ad"))
        try:
            from dbcore import connect
            c = connect()
            try:
                with c:
                    cur = c.execute("DELETE FROM monthly_question_images WHERE id = ?", (image_id,))
                    deleted = cur.rowcount
            finally:
                c.close()
        except Exception:
            logger.exception("Could not delete monthly question image")
            return await show(q, "❌ ما قدرت أحذف الصورة حالياً.", back_markup("ad"))
        if not deleted:
            return await show(q, "⚠️ الصورة غير موجودة.", back_markup("ad"))
        return await show(q, "✅ انحذفت الصورة بنجاح.", Markup([[Btn("🗑️ حذف صورة ثانية", callback_data=f"mdelete:{quiz_type}:{section}:{sid}", style=cb_style(35))], [Btn("⚙️ لوحة الأدمن", callback_data="ad", style=cb_style(36))]]))

    if action == "ak":
        kind, _, sid_s = arg.partition(":")
        try:
            sid = int(sid_s)
        except (TypeError, ValueError):
            return await show(q, "⚠️ رقم المادة غير صالح.", back_markup("ad"))
        return await pick_subject(q, context, kind, sid)

    if action == "ay":
        kind, _, sid_s = arg.partition(":")
        try:
            sid = int(sid_s)
        except (TypeError, ValueError):
            return await show(q, "⚠️ رقم المادة غير صالح.", back_markup("ad"))
        if kind == "cq":
            db.clear_questions(sid)
            msg = "✅ انمسحت الأسئلة."
        elif kind == "dsub":
            db.delete_subject(sid)
            msg = "✅ انحذفت المادة."
        else:
            return
        return await show(q, msg, back_markup("ad", "⚙️ لوحة الأدمن"))

    if action == "ds":
        try:
            sum_id = int(arg)
        except (TypeError, ValueError):
            return await show(q, "⚠️ رقم الملخص غير صالح.", back_markup("ad"))
        db.delete_summary(sum_id)
        return await show(q, "✅ انحذف الملخص.", back_markup("ad", "⚙️ لوحة الأدمن"))

async def pick_subject(q, context, kind, sid):
    subj = db.get_subject(sid)
    if not subj:
        return await show(q, "⚠️ المادة غير موجودة.", back_markup("ad"))
    name = subj["name"]

    if kind == "sum":
        context.user_data["await"] = {"type": "summary", "sid": sid}
        return await show(q, f"أرسل ملخص مادة {name}:\n\n• رابط (تقدر تكتب عنوان بالسطر الأول والرابط بالسطر الثاني)\n• أو ملف PDF (العنوان يكون بالتعليق caption)\n\nللإلغاء: /cancel")

    if kind == "q":
        context.user_data["await"] = {"type": "questions", "sid": sid}
        return await show(q, f"❓ أسئلة مادة {name}\n\n{QUESTIONS_HELP}")

    if kind == "mi":
        context.user_data["monthly_sid"] = sid
        return await show(q, f"🖼️ أسئلة شهرية — {name}\n\nاختر نوع الأسئلة:", monthly_type_markup())

    if kind == "dsum":
        items = db.summaries(sid)
        if not items:
            return await show(q, "ما في ملخصات لهذي المادة.", back_markup("ad"))
        rows = [[Btn(f"🗑 {it['title']}", callback_data=f"ds:{it['id']}", style=cb_style(37))] for it in items]
        rows.append([Btn("🔙 رجوع", callback_data="ad", style=cb_style(38))])
        return await show(q, "اضغط على الملخص اللي تبي تحذفه:", Markup(rows))

    if kind == "cq":
        n = db.count_questions(sid)
        return await show(q, f"متأكد تبي تمسح {n} سؤال من {name}؟", confirm_markup("cq", sid))

    if kind == "dsub":
        return await show(q, f"متأكد تبي تحذف مادة {name} بكل محتواها ونتائجها؟", confirm_markup("dsub", sid))
