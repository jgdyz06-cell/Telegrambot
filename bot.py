# -*- coding: utf-8 -*-
import datetime as dt

from telegram import Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
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
from config import BOT_TOKEN, logger
from ui import (
    SUB_TEXT, is_admin, is_subscribed, main_menu, send_summary, show,
    sub_markup, subjects_markup, summaries_list,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("quiz", None)
    context.user_data.pop("await", None)
    db.upsert_user(update.effective_user.id, update.effective_user.full_name)
    if not await is_subscribed(context, update.effective_user.id):
        return await update.message.reply_text(SUB_TEXT, reply_markup=sub_markup())
    await update.message.reply_text(
        "أهلاً بيك 👋\nاختر من القائمة:", reply_markup=main_menu(update.effective_user.id)
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"آيديك: {update.effective_user.id}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("await", None)
    await update.message.reply_text(
        "تم الإلغاء ✅", reply_markup=main_menu(update.effective_user.id)
    )


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return await update.message.reply_text(
            f"هذا الأمر للأدمن فقط.\nآيديك: {uid}\n(ضيفه في ADMIN_IDS)"
        )
    await update.message.reply_text("⚙️ لوحة الأدمن:", reply_markup=admin.panel_markup())


async def content_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = "\n".join(seed.REPORT) or "ما في تقرير."
    tail = f"\n\n🗄 القاعدة: {backup.counts()}\n♻️ آخر استعادة: {backup.LAST_RESTORE}"
    await update.message.reply_text("📂 المحتوى المحمّل من الملفات:\n\n" + text[:3200] + tail)


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        st = await backup.send_backup(context.bot, force=True)
    except Exception:
        logger.exception("backup")
        st = "error"
    names = {
        "ok": "✅ انحفظت النسخة (مثبّتة بأعلى هذي المحادثة)",
        "no_chat": "⚠️ ما في أدمن مسجّل بـ ADMIN_IDS",
        "error": "❌ فشل الحفظ، شوف Deploy Logs",
    }
    await update.message.reply_text(f"{names.get(st, st)}\n🗄 {backup.counts()}")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aw = context.user_data.get("await")
    if aw and aw["type"] == "report":
        return await reports.handle_report_request(update, context)
    if aw and is_admin(update.effective_user.id):
        return await admin_msg.handle_admin_message(update, context, aw)
    await update.message.reply_text("اكتب /start لفتح القائمة 👇")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    action, _, arg = q.data.partition(":")

    if action == "chk":
        if await is_subscribed(context, uid, force=True):
            await q.answer()
            return await show(q, "أهلاً بيك 👋\nاختر من القائمة:", main_menu(uid))
        return await q.answer("لسا ما اشتركت بالقناة ❌", show_alert=True)

    if not await is_subscribed(context, uid):
        await q.answer()
        return await show(q, SUB_TEXT, sub_markup())

    if action == "a":
        return await quiz_flow.answer(q, context, arg)

    await q.answer()

    if action in admin.ACTIONS:
        if not is_admin(uid):
            return await q.message.reply_text("هذا للأدمن فقط.")
        return await admin.router(q, context, action, arg)

    if action == "m":
        context.user_data.pop("await", None)
        await show(q, "اختر من القائمة:", main_menu(uid))
    elif action == "sm":
        await show(q, "📄 اختر المادة (الملخصات):", subjects_markup("s", "s_count"))
    elif action == "s":
        await summaries_list(q, int(arg))
    elif action == "sd":
        await send_summary(q, int(arg))
    elif action == "qm":
        await show(q, "📝 اختر المادة (الاختبارات):", subjects_markup("q", "q_count"))
    elif action == "q":
        await quiz.show_subject_quiz(q, uid, int(arg))
    elif action == "qs":
        await quiz.start_quiz(q, context, int(arg))
    elif action == "rw":
        await quiz.retry_wrong(q, context)
    elif action == "n":
        await quiz_flow.next_question(q, context)
    elif action == "me":
        await quiz.show_stats(q, uid)
    elif action == "ct":
        await reports.show_contact(q)
    elif action == "rp":
        await reports.show_report_info(q)
    elif action == "rp1":
        await reports.ask_report(q, context)
    elif action == "sc":
        await timetable.open_menu(q, uid)
    elif action == "scset":
        await timetable.set_section(q, context, arg)
    elif action == "scday":
        await timetable.show_day(q, uid, arg)
    elif action == "scchg":
        aw
