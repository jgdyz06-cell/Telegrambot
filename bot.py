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
