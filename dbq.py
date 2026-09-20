# -*- coding: utf-8 -*-
"""الأسئلة والنتائج + قراءة الأسئلة من نص."""
import json
import re

from dbcore import connect, sql_all, sql_one, sql_run


def questions(sid):
    rows = sql_all("SELECT * FROM questions WHERE subject_id = ? ORDER BY id", (sid,))
    for r in rows:
        r["options"] = json.loads(r["options"])
    return rows


def count_questions(sid):
    return sql_one("SELECT COUNT(*) AS n FROM questions WHERE subject_id = ?", (sid,))["n"]


def add_questions(sid, items):
    data = [
        (sid, it["question"], json.dumps(it["options"], ensure_ascii=False),
         it["answer"], it.get("explanation", ""))
        for it in items
    ]
    c = connect()
    try:
        with c:
            c.executemany(
                "INSERT INTO questions(subject_id, question, options, answer, explanation)"
                " VALUES (?,?,?,?,?)",
                data,
            )
    finally:
        c.close()
    return len(items)


def clear_questions(sid):
    sql_run("DELETE FROM questions WHERE subject_id = ?", (sid,))


def save_result(user_id, name, sid, score, total):
    sql_run(
        "INSERT INTO results(user_id, name, subject_id, score, total) VALUES (?,?,?,?,?)",
        (user_id, name, sid, score, total),
    )


def best_for(user_id, sid):
    r = sql_one(
        "SELECT MAX(score * 100.0 / total) AS b FROM results"
        " WHERE user_id = ? AND subject_id = ?",
        (user_id, sid),
    )
    return None if not r or r["b"] is None else round(r["b"])


def user_stats(user_id):
    rows = sql_all(
        "SELECT s.name AS name, MAX(r.score * 100.0 / r.total) AS best, COUNT(*) AS attempts"
        " FROM results r JOIN subjects s ON s.id = r.subject_id"
        " WHERE r.user_id = ? GROUP BY r.subject_id ORDER BY s.id",
        (user_id,),
    )
    for r in rows:
        r["best"] = round(r["best"])
    return rows


def top(sid, n=5):
    rows = sql_all(
        "SELECT name, MAX(score * 100.0 / total) AS pct FROM results"
        " WHERE subject_id = ? GROUP BY user_id ORDER BY pct DESC LIMIT ?",
        (sid, n),
    )
    for r in rows:
        r["pct"] = round(r["pct"])
    return rows


def parse_questions(text):
    """يقرأ الأسئلة من نص. يرجع (الصحيح, الأخطاء)."""
    good, errors = [], []
    blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    for n, block in enumerate(blocks, 1):
        q_lines, options, expl = [], [], []
        stars, answer, in_expl, bad = 0, None, False, None
        for raw in block.splitlines():
            line = raw.strip()
            if not line:
                continue
            m = re.match(r"^(?:الشرح|شرح)\s*[:：]\s*(.*)$", line)
            if m:
                in_expl = True
                if m.group(1):
                    expl.append(m.group(1))
            elif in_expl:
                expl.append(line)
            elif line.startswith("-"):
                opt = line[1:].strip()
                if opt.endswith("*"):
                    opt = opt[:-1].strip()
                    stars += 1
                    if answer is None:
                        answer = len(options)
                if not opt:
                    bad = "في خيار فاضي"
                options.append(opt)
            elif options:
                bad = f"سطر غير مفهوم بعد الخيارات: «{line[:30]}»"
            else:
                q_lines.append(line)
        question = " ".join(q_lines).strip()
        if not bad:
            if not question:
                bad = "ما في نص للسؤال"
            elif not 2 <= len(options) <= 6:
                bad = "لازم من 2 إلى 6 خيارات (كل خيار يبدأ بـ -)"
            elif stars != 1:
                bad = "لازم تعلّم إجابة وحدة صحيحة بنجمة *"
        if bad:
            errors.append(f"السؤال رقم {n}: {bad}")
            continue
        good.append(
            {"question": question, "options": options, "answer": answer,
             "explanation": " ".join(expl).strip()}
        )
    return good, errors
