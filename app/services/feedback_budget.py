"""KST daily feedback limit and result reuse, separate from the rewrite ledger."""
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from app import config


def reserve(key, fallback):
    path = Path(config.FEEDBACK_LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(key.encode()).hexdigest()
    day = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    with sqlite3.connect(path, timeout=5) as db:
        db.execute('CREATE TABLE IF NOT EXISTS feedback_call (key TEXT PRIMARY KEY, day TEXT NOT NULL, result TEXT NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT result FROM feedback_call WHERE key=?', (key,)).fetchone()
        if previous: return False, json.loads(previous[0])
        if db.execute('SELECT count(*) FROM feedback_call WHERE day=?', (day,)).fetchone()[0] >= config.MAX_DAILY_FEEDBACK_CALLS:
            return False, fallback
        db.execute('INSERT INTO feedback_call VALUES(?,?,?)', (key, day, json.dumps(fallback, ensure_ascii=False)))
        return True, fallback


def finish(key, result):
    with sqlite3.connect(config.FEEDBACK_LEDGER_PATH, timeout=5) as db:
        db.execute('UPDATE feedback_call SET result=? WHERE key=?', (json.dumps(result, ensure_ascii=False), hashlib.sha256(key.encode()).hexdigest()))
