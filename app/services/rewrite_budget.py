"""Persistent, atomic daily budget and one-attempt-per-article ledger."""
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from app import config


def peek(article_key: str) -> dict | None:
    """Read-only maintenance lookup; never creates a ledger or reserves a call."""
    path = Path(config.REWRITE_LEDGER_PATH)
    if not path.exists(): return None
    key = hashlib.sha256(article_key.encode()).hexdigest()
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as db:
        row = db.execute('SELECT result FROM rewrite_attempt WHERE article_key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None


def reserve(article_key: str, fallback: dict) -> tuple[bool, dict]:
    key = hashlib.sha256(article_key.encode()).hexdigest()
    path = Path(config.REWRITE_LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=5) as db:
        db.execute("CREATE TABLE IF NOT EXISTS rewrite_attempt (article_key TEXT PRIMARY KEY, day TEXT NOT NULL, result TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT result FROM rewrite_attempt WHERE article_key=?", (key,)).fetchone()
        if previous:
            return False, json.loads(previous[0])
        day = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
        count = db.execute("SELECT count(*) FROM rewrite_attempt WHERE day=?", (day,)).fetchone()[0]
        if count >= config.MAX_DAILY_REWRITE_CALLS:
            return False, fallback
        # Reserve before dispatch: a crash/failure must not allow another paid attempt.
        db.execute("INSERT INTO rewrite_attempt VALUES (?, ?, ?)", (key, day, json.dumps(fallback, ensure_ascii=False)))
    return True, fallback


def finish(article_key: str, result: dict) -> None:
    key = hashlib.sha256(article_key.encode()).hexdigest()
    with sqlite3.connect(config.REWRITE_LEDGER_PATH, timeout=5) as db:
        db.execute("UPDATE rewrite_attempt SET result=? WHERE article_key=?", (json.dumps(result, ensure_ascii=False), key))
