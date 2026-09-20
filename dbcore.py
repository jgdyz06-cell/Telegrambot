# -*- coding: utf-8 -*-
import os
import sqlite3
from pathlib import Path


def connect():
    path = os.environ.get("DB_PATH") or str(Path(__file__).with_name("bot.db"))
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def sql_run(sql, args=()):
    c = connect()
    try:
        with c:
            return c.execute(sql, args).lastrowid
    finally:
        c.close()


def sql_all(sql, args=()):
    c = connect()
    try:
        return [dict(r) for r in c.execute(sql, args).fetchall()]
    finally:
        c.close()


def sql_one(sql, args=()):
    r = sql_all(sql, args)
    return r[0] if r else None
