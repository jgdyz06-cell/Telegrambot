# -*- coding: utf-8 -*-
"""سير الاختبار: الإجابة، التالي، النتيجة."""
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup

import db
from quiz import options_markup, question_text
from ui import back_markup, show


async def answer(q, context, arg):
    try:
        qi, oi = (int(x) for x in arg.split(":"))
    except ValueError:
        return await q.answer()
    sess = context.user_data.get("quiz")
    if not sess:
        await q.answer()
        return await show(
            q,
            "⚠️ انتهت الجلسة (غالباً البوت انعمل له إعادة تشغيل). ابدأ الاختبار من جديد.",
            back_markup("qm", "🔙 الاختبارات"),
        )
    if sess["i"] != qi or sess["answered"]:
        return await q.answer("تم الجواب على هذا السؤال")
    await q.answer()

    item = sess["qs"][qi]
    ok = oi == item["answer"]
    sess["answered"] = True
    if ok:
        sess["correct"] += 1
    else:
        sess["wrong"].append(item["id"])

    text = question_text(sess, reveal=oi)
    text += "\n\n" + ("✅ إجابة صحيحة!" if ok else "❌ إجابة خاطئة.")
    if item["explanation"]:
        text += f"\n💡 {item['explanation']}"
    last = qi + 1 >= len(sess["qs"])
    label = "🏁 عرض النتيجة" if last else "التالي ⬅️"
    await show(q, text, back_markup("n", label))


async def next_question(q, context):
    sess = context.user_data.get("quiz")
    if not sess or not sess["answered"]:
        return
    sess["i"] += 1
    sess["answered"] = False
    if sess["i"] >= len(sess["qs"]):
        return await finish_quiz(q, context)
    await show(q, question_text(sess), options_markup(sess))


def comment(pct):
    if pct >= 90:
        return "ممتاز 🌟"
    if pct >= 70:
        return "جيد جداً 👏"
    if pct >= 50:
        return "جيد، كمّل مراجعة 💪"
    return "راجع الملخص وأعد المحاولة 📚"


async def finish_quiz(q, context):
    sess = context.user_data.pop("quiz")
    user = q.from_user
    total, correct = len(sess["qs"]), sess["correct"]
    pct = round(correct * 100 / total)
    lines = [
        f"🏁 انتهى الاختبار — {sess['name']}",
        "",
        f"نتيجتك: {correct} من {total} ({pct}%)",
        comment(pct),
    ]
    if sess["retry"]:
        lines.append("\n(إعادة الأسئلة الغلط ما تنحسب بالنتائج)")
    else:
        db.save_result(user.id, user.full_name, sess["sid"], correct, total)
        lines.append(f"\nأفضل نتيجة لك: {db.best_for(user.id, sess['sid'])}%")

    rows = []
    if sess["wrong"]:
        context.user_data["retry"] = {"sid": sess["sid"], "ids": sess["wrong"]}
        rows.append(
            [Btn(f"🔁 أعد الأسئلة الغلط ({len(sess['wrong'])})", callback_data="rw")]
        )
    else:
        context.user_data.pop("retry", None)
    rows.append([Btn("🔄 اختبار جديد", callback_data=f"qs:{sess['sid']}")])
    rows.append([Btn("🔙 المواد", callback_data="qm")])
    await show(q, "\n".join(lines), Markup(rows))
