# -*- coding: utf-8 -*-
"""عرض الاختبار: بناء الجلسة والأسئلة والإحصائيات."""
import random

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup

import db
from config import QUIZ_SIZE
from ui import back_markup, show

NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]


def is_true_false(options):
    return {o.strip() for o in options} == {"صح", "خطأ"}


def build_session(subject, questions, retry=False):
    qs = []
    for item in random.sample(questions, len(questions)):
        opts = list(enumerate(item["options"]))  # (الفهرس الأصلي, النص)
        if not is_true_false(item["options"]):
            random.shuffle(opts)
        new_answer = next(i for i, (orig, _) in enumerate(opts) if orig == item["answer"])
        qs.append(
            {
                "id": item["id"],
                "question": item["question"],
                "options": [t for _, t in opts],
                "answer": new_answer,
                "explanation": item["explanation"],
            }
        )
    return {
        "sid": subject["id"], "name": subject["name"], "qs": qs, "i": 0,
        "correct": 0, "wrong": [], "retry": retry, "answered": False,
    }


def question_text(sess, reveal=None):
    i = sess["i"]
    item = sess["qs"][i]
    lines = [f"📝 {sess['name']} — السؤال {i + 1} من {len(sess['qs'])}", "", item["question"], ""]
    for k, opt in enumerate(item["options"]):
        mark = NUMS[k]
        if reveal is not None:
            if k == item["answer"]:
                mark = "✅"
            elif k == reveal:
                mark = "❌"
        lines.append(f"{mark} {opt}")
    return "\n".join(lines)


def options_markup(sess):
    i = sess["i"]
    opts = sess["qs"][i]["options"]
    short = all(len(o) <= 12 for o in opts)
    buttons = [
        Btn(o if short else str(k + 1), callback_data=f"a:{i}:{k}") for k, o in enumerate(opts)
    ]
    return Markup([buttons[j : j + 3] for j in range(0, len(buttons), 3)])


async def show_subject_quiz(q, uid, sid):
    subj = db.get_subject(sid)
    if not subj:
        return await show(q, "⚠️ المادة غير موجودة.", back_markup("qm"))
    n = db.count_questions(sid)
    lines = [f"📝 {subj['name']}", f"عدد الأسئلة: {n}"]
    best = db.best_for(uid, sid)
    if best is not None:
        lines.append(f"أفضل نتيجة لك: {best}%")
    top = db.top(sid)
    if top:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        lines += ["", "🏆 أفضل النتائج:"]
        lines += [f"{medals[i]} {t['name']} — {t['pct']}%" for i, t in enumerate(top)]
    rows = []
    if n:
        rows.append([Btn("▶️ ابدأ الاختبار", callback_data=f"qs:{sid}")])
    else:
        lines.append("\n⚠️ ما في أسئلة مضافة بعد.")
    rows.append([Btn("🔙 رجوع للمواد", callback_data="qm")])
    await show(q, "\n".join(lines), Markup(rows))


async def start_quiz(q, context, sid):
    subj = db.get_subject(sid)
    qs = db.questions(sid) if subj else []
    if not qs:
        return await show(q, "⚠️ ما في أسئلة لهذي المادة.", back_markup("qm"))
    if 0 < QUIZ_SIZE < len(qs):
        qs = random.sample(qs, QUIZ_SIZE)
    sess = build_session(subj, qs)
    context.user_data["quiz"] = sess
    await show(q, question_text(sess), options_markup(sess))


async def retry_wrong(q, context):
    info = context.user_data.get("retry")
    subj = db.get_subject(info["sid"]) if info else None
    ids = set(info["ids"]) if info else set()
    qs = [x for x in db.questions(info["sid"]) if x["id"] in ids] if subj else []
    if not qs:
        return await show(q, "⚠️ ما في أسئلة للإعادة.", back_markup("qm", "🔙 الاختبارات"))
    sess = build_session(subj, qs, retry=True)
    context.user_data["quiz"] = sess
    await show(q, question_text(sess), options_markup(sess))


async def show_stats(q, uid):
    rows = db.user_stats(uid)
    if not rows:
        text = "📊 ما عندك نتائج بعد. جرّب أول اختبار!"
    else:
        text = "📊 نتائجك:\n\n" + "\n".join(
            f"• {r['name']}: أفضل نتيجة {r['best']}% ({r['attempts']} محاولة)" for r in rows
        )
    await show(q, text, back_markup("m"))
