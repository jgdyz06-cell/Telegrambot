# -*- coding: utf-8 -*-
"""قاعدة البيانات: المواد والملخصات + إنشاء الجداول."""
import sqlite3

from dbcore import connect, sql_all, sql_one, sql_run
from dbq import (  # noqa: F401
    add_questions, best_for, clear_questions, count_questions,
    parse_questions, questions, save_result, top, user_stats,
)

DEFAULT_SUBJECTS = [
    "النحو", "الصرف", "البلاغة", "الأدب الإسلامي", "الحاسوب",
    "الإنكليزي", "أسس تربية", "جرائم حزب البعث", "نصوص قديمة", "العروض والقافية",
]
SEED_SUMMARIES = {
    "النحو": (
        "ملخص النحو",
        "https://drive.google.com/file/d/11vHek92zyJfhSXD9fIUdJadSCgyRwZ6l/view?usp=drivesdk",
    ),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    title TEXT NOT NULL, url TEXT, file_id TEXT);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    question TEXT NOT NULL, options TEXT NOT NULL,
    answer INTEGER NOT NULL, explanation TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, name TEXT NOT NULL,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    score INTEGER NOT NULL, total INTEGER NOT NULL,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, section TEXT);
"""


def init():
    c = connect()
    try:
        with c:
            c.executescript(SCHEMA)
    finally:
        c.close()
    if not sql_all("SELECT id FROM subjects LIMIT 1"):
        for name in DEFAULT_SUBJECTS:
            sid = add_subject(name)
            if name in SEED_SUMMARIES and sid:
                title, url = SEED_SUMMARIES[name]
                add_summary(sid, title, url=url)


def subjects():
    return sql_all("SELECT id, name FROM subjects ORDER BY id")


def subjects_with_counts():
    return sql_all(
        "SELECT s.id, s.name,"
        " (SELECT COUNT(*) FROM questions WHERE subject_id = s.id) AS q_count,"
        " (SELECT COUNT(*) FROM summaries WHERE subject_id = s.id) AS s_count"
        " FROM subjects s ORDER BY s.id"
    )


def get_subject(sid):
    return sql_one("SELECT id, name FROM subjects WHERE id = ?", (sid,))


def add_subject(name):
    try:
        return s
