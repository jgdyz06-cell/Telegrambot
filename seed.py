# -*- coding: utf-8 -*-
"""يقرأ الملخصات والأسئلة من مجلد content ويضيفها للقاعدة عند كل تشغيل."""
import re
import unicodedata
from pathlib import Path

import db
from config import logger

CONTENT_DIR = Path(__file__).with_name("content")
REPORT = []  # تقرير آخر قراءة (يظهر بأمر /content)


def norm(s):
    return unicodedata.normalize("NFC", s).strip()


def split_content(text):
    summaries, rest = [], []
    for line in text.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^\s*ملخص\s*[:：]\s*(.+)$", line)
        if m:
            summaries.append(m.group(1).strip())
        else:
            rest.append(line)
    return summaries, "\n".join(rest)


def parse_summary_line(line):
    parts = [p.strip() for p in line.split("|")]
    url = parts[-1]
    title = parts[0] if len(parts) > 1 and parts[0] else "ملخص"
    return title[:60], url


def apply_file(path):
    name = norm(path.stem)
    if not name:
        return
    sid = next((s["id"] for s in db.subjects() if norm(s["name"]) == name), None)
    if sid is None:
        sid = db.add_subject(name)
    sum_lines, body = split_content(path.read_text(encoding="utf-8-sig"))

    have_urls = {x["url"] for x in db.summaries(sid) if x["url"]}
    added_sum = 0
    for line in sum_lines:
        title, url = parse_summary_line(line)
        if not url.lower().startswith("http"):
            REPORT.append(f"⚠️ {name}: سطر ملخص بدون رابط: {line[:40]}")
            continue
        if url not in have_urls:
            db.add_summary(sid, title, url=url)
            have_urls.add(url)
            added_sum += 1

    good, errors = db.parse_questions(body) if body.strip() else ([], [])
    seen = {q["question"] for q in db.questions(sid)}
    new = []
    for q in good:
        if q["question"] not in seen:
            seen.add(q["question"])
            new.append(q)
    if new:
        db.add_questions(sid, new)
    total = db.count_questions(sid)
    REPORT.append(f"✅ {name}: {total} سؤال، {len(db.summaries(sid))} ملخص")
    REPORT.extend(f"⚠️ {name} — {e}" for e in errors)


def sync():
    REPORT.clear()
    if not CONTENT_DIR.is_dir():
        REPORT.append("ما في مجلد content بالريبو.")
        return
    files = sorted(CONTENT_DIR.glob("*.txt"))
    if not files:
        REPORT.append("مجلد content فاضي.")
    for path in files:
        try:
            apply_file(path)
        except Exception:
            logger.exception("خطأ بقراءة %s", path.name)
            REPORT.append(f"❌ خطأ بقراءة الملف {path.name}")
    for line in REPORT:
        logger.info(line)
