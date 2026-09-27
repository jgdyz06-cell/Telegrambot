# -*- coding: utf-8 -*-
"""نسخة احتياطية للقاعدة داخل تلقرام نفسه: تحفظ وتستعيد بدون Volume."""
import asyncio
import os
import shutil
import sqlite3
import tempfile

from telegram import InputMediaDocument

import db
import dbcore
import seed
from config import ADMIN_IDS, logger

INTERVAL = 300  # كل 5 دقايق، وبس إذا تغيّر شي
FILENAME = "bot-backup.db"
CAPTION = "🗄 نسخة القاعدة الاحتياطية. لا تحذف هذي الرسالة"
TABLES = ("subjects", "summaries", "questions", "results", "users")

LAST_RESTORE = "لسا ما صار"
_state = {"sig": None, "msg": None}


def backup_chat():
    raw = os.environ.get("BACKUP_CHAT", "").strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    return min(ADMIN_IDS) if ADMIN_IDS else None


def counts():
    r = {t: dbcore.sql_one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in TABLES}
    return (
        f"{r['subjects']} مادة، {r['questions']} سؤال، "
        f"{r['summaries']} ملخص، {r['results']} نتيجة"
    )


def signature():
    return tuple(
        tuple(dbcore.sql_one(
            f"SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS m FROM {t}"
        ).values())
        for t in TABLES
    )


def snapshot():
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    src = dbcore.connect()
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return tmp


async def send_backup(bot, force=False):
    chat = backup_chat()
    if chat is None:
        return "no_chat"
    sig = signature()
    if not force and sig == _state["sig"]:
        return "unchanged"
    tmp = snapshot()
    try:
        if _state["msg"]:
            try:
                with open(tmp, "rb") as f:
                    await bot.edit_message_media(
                        chat_id=chat,
                        message_id=_state["msg"],
                        media=InputMediaDocument(f, filename=FILENAME, caption=CAPTION),
                    )
                _state["sig"] = sig
                return "ok"
            except Exception:
                logger.warning("تعديل رسالة النسخة فشل، أرسل نسخة جديدة", exc_info=True)
        with open(tmp, "rb") as f:
            msg = await bot.send_document(
                chat_id=chat, document=f, filename=FILENAME,
                caption=CAPTION, disable_notification=True,
            )
        await bot.pin_chat_message(
            chat_id=chat, message_id=msg.message_id, disable_notification=True
        )
        old = _state["msg"]
        _state["msg"], _state["sig"] = msg.message_id, sig
        if old:
            try:
                await bot.delete_message(chat_id=chat, message_id=old)
            except Exception:
                pass
        return "ok"
    finally:
        os.remove(tmp)


async def restore(bot):
    chat = backup_chat()
    if chat is None:
        return "no_chat"
    info = a
