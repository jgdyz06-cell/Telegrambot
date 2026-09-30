# -*- coding: utf-8 -*-

"""قاعدة البيانات: المواد والملخصات + المستخدمون + الملابس."""

import sqlite3

from dbcore import connect, sql_all, sql_one, sql_run
from dbq import (  # noqa: F401
    add_questions,
    best_for,
    clear_questions,
    count_questions,
    parse_questions,
    questions,
    save_result,
    top,
    user_stats,
)


DEFAULT_SUBJECTS = [
    "النحو",
    "الصرف",
    "البلاغة",
    "الأدب الإسلامي",
    "الحاسوب",
    "الإنكليزي",
    "أسس تربية",
    "جرائم حزب البعث",
    "نصوص قديمة",
    "العروض والقافية",
]


SEED_SUMMARIES = {
    "النحو": (
        "ملخص النحو",
        "https://drive.google.com/file/d/11vHek92zyJfhSXD9fIUdJadSCgyRwZ6l/view?usp=drivesdk",
    ),
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    url TEXT,
    file_id TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    options TEXT NOT NULL,
    answer INTEGER NOT NULL,
    explanation TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    section TEXT,
    username TEXT,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wardrobe_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    gender TEXT NOT NULL,
    category TEXT NOT NULL,
    color TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wardrobe_user
ON wardrobe_items(user_id);

CREATE INDEX IF NOT EXISTS idx_wardrobe_user_gender
ON wardrobe_items(user_id, gender);
"""


# ============================================================
# Database Initialization
# ============================================================

def init():
    c = connect()

    try:

        with c:

            c.executescript(SCHEMA)

            # ------------------------------------------------
            # ترقية قاعدة البيانات القديمة إذا كانت users موجودة
            # بدون حذف المستخدمين الحاليين.
            # ------------------------------------------------

            columns = {
                row[1]
                for row in c.execute(
                    "PRAGMA table_info(users)"
                ).fetchall()
            }

            if "username" not in columns:

                c.execute(
                    "ALTER TABLE users ADD COLUMN username TEXT"
                )

            if "first_seen" not in columns:

                c.execute(
                    "ALTER TABLE users ADD COLUMN "
                    "first_seen DATETIME"
                )

            if "last_seen" not in columns:

                c.execute(
                    "ALTER TABLE users ADD COLUMN "
                    "last_seen DATETIME"
                )

            # ------------------------------------------------
            # المستخدمون الموجودون مسبقاً يأخذون الوقت الحالي
            # إذا كانت أعمدة الوقت جديدة.
            # ------------------------------------------------

            c.execute(
                """
                UPDATE users
                SET first_seen = COALESCE(
                    first_seen,
                    CURRENT_TIMESTAMP
                ),
                last_seen = COALESCE(
                    last_seen,
                    CURRENT_TIMESTAMP
                )
                """
            )

    finally:

        c.close()

    # --------------------------------------------------------
    # إضافة المواد الافتراضية إذا كانت القاعدة فارغة.
    # --------------------------------------------------------

    if not sql_all(
        "SELECT id FROM subjects LIMIT 1"
    ):

        for name in DEFAULT_SUBJECTS:

            sid = add_subject(name)

            if name in SEED_SUMMARIES and sid:

                title, url = SEED_SUMMARIES[name]

                add_summary(
                    sid,
                    title,
                    url=url,
                )


# ============================================================
# Subjects
# ============================================================

def subjects():

    return sql_all(
        "SELECT id, name FROM subjects ORDER BY id"
    )


def subjects_with_counts():

    return sql_all(
        "SELECT s.id, s.name,"
        " (SELECT COUNT(*) FROM questions "
        "WHERE subject_id = s.id) AS q_count,"
        " (SELECT COUNT(*) FROM summaries "
        "WHERE subject_id = s.id) AS s_count"
        " FROM subjects s ORDER BY s.id"
    )


def get_subject(sid):

    return sql_one(
        "SELECT id, name FROM subjects WHERE id = ?",
        (sid,),
    )


def add_subject(name):

    try:

        return sql_run(
            "INSERT INTO subjects(name) VALUES (?)",
            (name,),
        )

    except sqlite3.IntegrityError:

        return None


def delete_subject(sid):

    sql_run(
        "DELETE FROM subjects WHERE id = ?",
        (sid,),
    )


# ============================================================
# Summaries
# ============================================================

def summaries(sid):

    return sql_all(
        "SELECT * FROM summaries "
        "WHERE subject_id = ? ORDER BY id",
        (sid,),
    )


def get_summary(sum_id):

    return sql_one(
        "SELECT * FROM summaries WHERE id = ?",
        (sum_id,),
    )


def add_summary(
    sid,
    title,
    url=None,
    file_id=None,
):

    return sql_run(
        "INSERT INTO summaries("
        "subject_id, title, url, file_id"
        ") VALUES (?,?,?,?)",
        (
            sid,
            title,
            url,
            file_id,
        ),
    )


def delete_summary(sum_id):

    sql_run(
        "DELETE FROM summaries WHERE id = ?",
        (sum_id,),
    )


# ============================================================
# Users
# ============================================================

def upsert_user(
    uid,
    name,
    username=None,
):
    """
    حفظ أو تحديث بيانات مستخدم تيليجرام.

    uid:
        Telegram User ID

    name:
        اسم المستخدم الظاهر

    username:
        اسم المستخدم في تيليجرام بدون @
    """

    sql_run(
        """
        INSERT INTO users(
            user_id,
            name,
            username,
            first_seen,
            last_seen
        )
        VALUES (
            ?, ?,
            ?,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(user_id)
        DO UPDATE SET
            name = excluded.name,
            username = excluded.username,
            last_seen = CURRENT_TIMESTAMP
        """,
        (
            uid,
            name,
            username,
        ),
    )


def set_section(
    uid,
    section,
):

    sql_run(
        """
        INSERT INTO users(
            user_id,
            name,
            section,
            first_seen,
            last_seen
        )
        VALUES (
            ?, ?,
            ?,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(user_id)
        DO UPDATE SET
            section = excluded.section,
            last_seen = CURRENT_TIMESTAMP
        """,
        (
            uid,
            str(uid),
            section,
        ),
    )


def get_section(uid):

    r = sql_one(
        "SELECT section FROM users WHERE user_id = ?",
        (uid,),
    )

    return r["section"] if r else None


def users_with_section():

    return sql_all(
        """
        SELECT user_id, section
        FROM users
        WHERE section IS NOT NULL
        """
    )


# ============================================================
# المستخدمون - لوحة المدير
# ============================================================

def get_users_count():
    """إرجاع عدد المستخدمين المسجلين."""

    r = sql_one(
        "SELECT COUNT(*) AS count FROM users"
    )

    return int(
        r["count"]
    ) if r else 0


def get_all_users():
    """
    إرجاع جميع المستخدمين مرتبين من الأحدث استخداماً.
    """

    return sql_all(
        """
        SELECT
            user_id,
            name,
            username,
            section,
            first_seen,
            last_seen
        FROM users
        ORDER BY last_seen DESC, user_id DESC
        """
    )


def get_users_page(
    limit=10,
    offset=0,
):
    """
    إرجاع مجموعة من المستخدمين للعرض على صفحات.
    """

    return sql_all(
        """
        SELECT
            user_id,
            name,
            username,
            section,
            first_seen,
            last_seen
        FROM users
        ORDER BY last_seen DESC, user_id DESC
        LIMIT ? OFFSET ?
        """,
        (
            int(limit),
            int(offset),
        ),
    )


# ============================================================
# Outfit / Wardrobe
# ============================================================

def add_wardrobe_item(
    uid,
    gender,
    category,
    color,
):
    """
    إضافة قطعة ملابس إلى خزانة المستخدم.

    gender:
        him / her

    category:
        نوع القطعة مثل قميص، بنطلون، حذاء...

    color:
        لون القطعة.
    """

    return sql_run(
        """
        INSERT INTO wardrobe_items(
            user_id,
            gender,
            category,
            color
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            uid,
            str(gender).strip(),
            str(category).strip(),
            str(color).strip(),
        ),
    )


def get_wardrobe_items(
    uid,
    gender=None,
):
    """
    جلب ملابس المستخدم.

    إذا تم تمرير gender:
        يجلب ملابس For Him أو For Her فقط.

    إذا لم يتم تمريره:
        يجلب جميع الملابس.
    """

    if gender:

        return sql_all(
            """
            SELECT
                id,
                user_id,
                gender,
                category,
                color,
                created_at
            FROM wardrobe_items
            WHERE user_id = ?
              AND gender = ?
            ORDER BY id DESC
            """,
            (
                uid,
                str(gender).strip(),
            ),
        )

    return sql_all(
        """
        SELECT
            id,
            user_id,
            gender,
            category,
            color,
            created_at
        FROM wardrobe_items
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (uid,),
    )


def get_wardrobe_item(
    item_id,
    uid,
):
    """
    جلب قطعة واحدة مع التأكد من أنها تخص المستخدم.
    """

    return sql_one(
        """
        SELECT
            id,
            user_id,
            gender,
            category,
            color,
            created_at
        FROM wardrobe_items
        WHERE id = ?
          AND user_id = ?
        """,
        (
            item_id,
            uid,
        ),
    )


def delete_wardrobe_item(
    item_id,
    uid,
):
    """
    حذف قطعة ملابس تخص المستخدم فقط.
    """

    sql_run(
        """
        DELETE FROM wardrobe_items
        WHERE id = ?
          AND user_id = ?
        """,
        (
            item_id,
            uid,
        ),
    )


def clear_wardrobe(
    uid,
    gender=None,
):
    """
    حذف خزانة المستخدم.

    إذا تم تمرير gender:
        يحذف ملابس ذلك القسم فقط.

    إذا لم يتم تمريره:
        يحذف جميع الملابس.
    """

    if gender:

        sql_run(
            """
            DELETE FROM wardrobe_items
            WHERE user_id = ?
              AND gender = ?
            """,
            (
                uid,
                str(gender).strip(),
            ),
        )

        return

    sql_run(
        """
        DELETE FROM wardrobe_items
        WHERE user_id = ?
        """,
        (uid,),
    )


def count_wardrobe_items(
    uid,
    gender=None,
):
    """
    إرجاع عدد قطع الملابس المحفوظة.
    """

    if gender:

        result = sql_one(
            """
            SELECT COUNT(*) AS count
            FROM wardrobe_items
            WHERE user_id = ?
              AND gender = ?
            """,
            (
                uid,
                str(gender).strip(),
            ),
        )

    else:

        result = sql_one(
            """
            SELECT COUNT(*) AS count
            FROM wardrobe_items
            WHERE user_id = ?
            """,
            (uid,),
        )

    return int(
        result["count"]
    ) if result else 0
