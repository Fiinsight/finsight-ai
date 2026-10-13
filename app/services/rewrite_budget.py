"""Atomic KST budget, cached articles and quota retry/circuit state."""
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from app import config


def _now():
    return datetime.now(ZoneInfo('Asia/Seoul'))


def _open():
    path = Path(config.REWRITE_LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.execute('CREATE TABLE IF NOT EXISTS rewrite_attempt (article_key TEXT PRIMARY KEY, day TEXT NOT NULL, result TEXT NOT NULL, status TEXT NOT NULL DEFAULT "RESERVED")')
    if 'status' not in {row[1] for row in db.execute('PRAGMA table_info(rewrite_attempt)')}:
        db.execute('ALTER TABLE rewrite_attempt ADD COLUMN status TEXT NOT NULL DEFAULT "RESERVED"')
    db.execute('CREATE TABLE IF NOT EXISTS rewrite_day (day TEXT PRIMARY KEY, successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0, quota_errors INTEGER NOT NULL DEFAULT 0, last_429 TEXT)')
    db.execute('BEGIN IMMEDIATE')
    return db


def peek(article_key: str) -> dict | None:
    """Read-only batch lookup, without creating or reserving anything."""
    path = Path(config.REWRITE_LEDGER_PATH)
    if not path.exists(): return None
    key = hashlib.sha256(article_key.encode()).hexdigest()
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as db:
        row = db.execute('SELECT result FROM rewrite_attempt WHERE article_key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None


def reserve(article_key: str, fallback: dict) -> tuple[bool, dict]:
    key = hashlib.sha256(article_key.encode()).hexdigest()
    day = _now().date().isoformat()
    db = _open()
    try:
        with db:
            previous = db.execute('SELECT result,status FROM rewrite_attempt WHERE article_key=?', (key,)).fetchone()
            if previous and previous[1] != 'RETRY':
                return False, json.loads(previous[0])
            db.execute('INSERT OR IGNORE INTO rewrite_day(day) VALUES(?)', (day,))
            quota = db.execute('SELECT quota_errors FROM rewrite_day WHERE day=?', (day,)).fetchone()[0]
            if quota >= 3:
                return False, {**fallback, 'retryable': True}
            count = db.execute('SELECT count(*) FROM rewrite_attempt WHERE day=? AND status<>"RETRY"', (day,)).fetchone()[0]
            if count >= config.MAX_DAILY_REWRITE_CALLS:
                return False, json.loads(previous[0]) if previous else fallback
            result = json.dumps(fallback, ensure_ascii=False)
            db.execute('INSERT INTO rewrite_attempt VALUES(?,?,?,"RESERVED") ON CONFLICT(article_key) DO UPDATE SET day=excluded.day,result=excluded.result,status="RESERVED"', (key, day, result))
        return True, fallback
    finally:
        db.close()


def finish(article_key: str, result: dict, *, failed: bool = False, quota: bool = False) -> None:
    key = hashlib.sha256(article_key.encode()).hexdigest()
    now = _now()
    db = _open()
    try:
        with db:
            row = db.execute('SELECT day,status FROM rewrite_attempt WHERE article_key=?', (key,)).fetchone()
            if not row or row[1] != 'RESERVED': return
            # Attribute outcomes to the KST response day, including a call crossing midnight.
            day = now.date().isoformat()
            db.execute('INSERT OR IGNORE INTO rewrite_day(day) VALUES(?)', (day,))
            status = 'RETRY' if quota else 'FAILED' if failed else 'SUCCESS'
            db.execute('UPDATE rewrite_attempt SET result=?,status=? WHERE article_key=?', (json.dumps(result, ensure_ascii=False), status, key))
            db.execute('UPDATE rewrite_day SET successes=successes+?,failures=failures+?,quota_errors=quota_errors+?,last_429=CASE WHEN ? THEN ? ELSE last_429 END WHERE day=?',
                       (int(not failed), int(failed), int(quota), quota, now.isoformat(), day))
    finally:
        db.close()


def status() -> dict:
    day = _now().date().isoformat()
    result = {'rewriteDay': day, 'rewriteSuccessCount': 0, 'rewriteFailureCount': 0,
              'rewrite429Count': 0, 'rewriteUsedCalls': 0, 'rewriteDailyLimit': config.MAX_DAILY_REWRITE_CALLS,
              'rewriteStoppedToday': False, 'rewriteLast429At': None}
    path = Path(config.REWRITE_LEDGER_PATH)
    if not path.exists(): return result
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as db:
        tables = {row[0] for row in db.execute('SELECT name FROM sqlite_master WHERE type="table"')}
        if 'rewrite_day' in tables:
            row = db.execute('SELECT successes,failures,quota_errors,last_429 FROM rewrite_day WHERE day=?', (day,)).fetchone()
            if row:
                result.update(rewriteSuccessCount=row[0], rewriteFailureCount=row[1], rewrite429Count=row[2], rewriteLast429At=row[3], rewriteStoppedToday=row[2] >= 3)
        if 'rewrite_attempt' in tables:
            has_status = 'status' in {row[1] for row in db.execute('PRAGMA table_info(rewrite_attempt)')}
            result['rewriteUsedCalls'] = db.execute('SELECT count(*) FROM rewrite_attempt WHERE day=?'+(' AND status<>"RETRY"' if has_status else ''), (day,)).fetchone()[0]
    return result
