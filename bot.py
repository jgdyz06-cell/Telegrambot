# -*- coding: utf-8 -*-
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from data import SUBJECTS, SUMMARY_LINKS, QUIZZES

BOT_TOKEN = "8759023385:AAGJ4d_pFGXAegKKbjPzl2xnUArtt9vbCWI"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

user_quiz_state = {}


def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📄 الملخصات", callback_data="menu_summaries")],
        [InlineKeyboardButton("📝 الاختبارات", callback_data="menu_quizzes")],
    ]
    return InlineKeyboardMarkup(keyboard)


def subjects_keyboard(prefix: str):
    keyboard = []
    for subject in SUBJECTS:
        keyboard.append(
            [InlineKeyboardButton(subject, callback_data=f"{prefix}_{subject}")]
        )
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)


def quiz_options_keyboard(subject, q_index, options):
    keyboard = []
    for i, opt in enumerate(options):
        keyboard.append(
            [InlineKeyboardButton(opt, callback_data=f"ans_{subject}_{q_index}_{i}")]
        )
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بيك 👋\nاختر من القائمة:",
        reply_markup=main_menu_keyboard(),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "back_main":
        await query.edit_message_text(
            "اختر من القائمة:", reply_markup=main_menu_keyboard()
        )
        return

    if data == "menu_summaries":
        await query.edit_message_text(
            "اختر المادة (الملخصات):",
            reply_markup=subjects_keyboard("sum"),
        )
        return

    if data == "menu_quizzes":
        await query.edit_message_text(
            "اختر المادة (الاختبارات):",
            reply_markup=subjects_keyboard("quiz"),
        )
        return

    if data.startswith("sum_"):
        subject = data[len("sum_"):]
        link = SUMMARY_LINKS.get(subject, "")
        if link:
            text = f"📄 ملخص مادة {subject}:\n{link}"
        else:
            text = f"⚠️ لا يوجد رابط مضاف بعد لمادة {subject}."
        back_keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 رجوع للمواد", callback_data="menu_summaries")]]
        )
        await query.edit_message_text(text, reply_markup=back_keyboard)
        return

    if data.startswith("quiz_"):
        subject = data[len("quiz_"):]
        questions = QUIZZES.get(subject, [])
        if not questions:
            back_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 رجوع للمواد", callback_data="menu_quizzes")]]
            )
            await query.edit_message_text(
                f"⚠️ لا توجد أسئلة مضافة بعد لمادة {subject}.",
                reply_markup=back_keyboard,
            )
            return

        user_quiz_state[user_id] = {"subject": subject, "q_index": 0, "correct": 0}
        await send_question(query, subject, 0)
        return

    if data.startswith("ans_"):
        parts = data.split("_")
        option_index = int(parts[-1])
        q_index = int(parts[-2])
        subject = "_".join(parts[1:-2])

        state = user_quiz_state.get(user_id)
        if not state or state["subject"] != subject or state["q_index"] != q_index:
            await query.edit_message_text("⚠️ حدث خطأ، ابدأ الاختبار من جديد.")
            return

        questions = QUIZZES.get(subject, [])
        current_q = questions[q_index]
        is_correct = option_index == current_q["answer"]
        if is_correct:
            state["correct"] += 1

        next_index = q_index + 1

        if next_index < len(questions):
            state["q_index"] = next_index
            feedback = "✅ إجابة صحيحة!" if is_correct else "❌ إجابة خاطئة."
            await query.edit_message_text(feedback)
            await send_question(query, subject, next_index, edit=False)
        else:
            total = len(questions)
            correct = state["correct"]
            feedback = "✅ إجابة صحيحة!" if is_correct else "❌ إجابة خاطئة."
            back_keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 رجوع للمواد", callback_data="menu_quizzes")]]
            )
            await query.edit_message_text(
                f"{feedback}\n\n🎉 انتهى الاختبار!\nنتيجتك: {correct} من {total}",
                reply_markup=back_keyboard,
            )
            user_quiz_state.pop(user_id, None)
        return


async def send_question(query, subject, q_index, edit=True):
    questions = QUIZZES.get(subject, [])
    q = questions[q_index]
    text = f"📝 {subject} - السؤال {q_index + 1} من {len(questions)}\n\n{q['question']}"
    keyboard = quiz_options_keyboard(subject, q_index, q["options"])
    if edit:
        await query.edit_message_text(text, reply_markup=keyboard)
    else:
        await query.message.reply_text(text, reply_markup=keyboard)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ البوت شغال... اضغط Ctrl+C للإيقاف")
    app.run_polling()


if __name__ == "__main__":
    main()
