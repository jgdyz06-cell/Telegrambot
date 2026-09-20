# -*- coding: utf-8 -*-
"""التواصل وطلب التقارير."""
import time

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup

from config import ADMIN_IDS, OWNER_TG, OWNER_WA_LOCAL, REPORT_PRICE, logger
from ui import contact_buttons, show


async def show_contact(q):
    text = (
        "📞 للتواصل مع الإدارة:\n\n"
        f"✈️ تلقرام: @{OWNER_TG}\n"
        f"🟢 واتساب: {OWNER_WA_LOCAL}"
    )
    rows = contact_buttons() + [[Btn("🔙 رجوع", callback_data="m")]]
    await show(q, text, Markup(rows))


async def show_report_info(q):
    text = (
        "📑 خدمة إعداد التقارير حسب الطلب\n\n"
        "نسوي لك تقرير عن أي موضوع تحتاجه.\n"
        f"💰 السعر: {REPORT_PRICE}\n\n"
        "اضغط «اكتب طلبك» وأرسل برسالة وحدة:\n"
        "• الموضوع\n• عدد الصفحات\n• موعد التسليم\n• أي ملاحظات"
    )
    rows = [[Btn("✍️ اكتب طلبك", callback_data="rp1")]] + contact_buttons()
    rows.append([Btn("🔙 رجوع", callback_data="m")])
    await show(q, text, Markup(rows))


async def ask_report(q, context):
    context.user_data["await"] = {"type": "report"}
    await show(
        q,
        "✍️ اكتب طلبك بالتفصيل برسالة وحدة:\n"
        "الموضوع، عدد الصفحات، موعد التسليم، ملاحظاتك.\n\nللإلغاء: /cancel",
    )


async def handle_report_request(update, context):
    msg = update.message
    user = update.effective_user
    text = (msg.text or "").strip()
    if not text:
        return await msg.reply_text("أرسل طلبك كنص.")
    if len(text) > 1500:
        return await msg.reply_text("⚠️ الطلب طويل، اختصره (أقل من 1500 حرف).")
    if time.time() - context.user_data.get("last_report", 0) < 60:
        return await msg.reply_text("⏳ انتظر دقيقة قبل ما ترسل طلب ثاني.")

    handle = f"@{user.username}" if user.username else "بدون يوزر"
    admin_text = (
        "📑 طلب تقرير جديد\n\n"
        f"👤 {user.full_name}\n🔗 {handle}\n🆔 {user.id}\n\n{text}"
    )
    markup = None
    if user.username:
        markup = Markup([[Btn("💬 تواصل مع الطالب", url=f"https://t.me/{user.username}")]])
    sent = 0
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, admin_text, reply_markup=markup)
            sent += 1
        except Exception:
            logger.exception("ما قدرت أرسل الطلب للأدمن %s (لازم يسوي /start للبوت)", admin_id)

    rows = contact_buttons() + [[Btn("🔙 القائمة الرئيسية", callback_data="m")]]
    if not sent:
        return await msg.reply_text(
            "⚠️ صار خطأ بإرسال الطلب. تواصل معنا مباشرة:", reply_markup=Markup(rows)
        )
    context.user_data.pop("await", None)
    context.user_data["last_report"] = time.time()
    await msg.reply_text(
        "✅ وصل طلبك، راح نتواصل وياك قريباً.\nتقدر تتواصل معنا مباشرة:",
        reply_markup=Markup(rows),
    )
