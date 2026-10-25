"""Local, version-bound review records for synthetic demonstration only."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .config import DATA_DIR


def _connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATA_DIR / "reviews.sqlite", timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY, study_id TEXT NOT NULL, extraction_hash TEXT NOT NULL,
        rule_id TEXT NOT NULL, decision TEXT NOT NULL, reviewer TEXT NOT NULL,
        purpose TEXT NOT NULL, reviewed_at TEXT NOT NULL)""")
    return connection


def save_review(study_id, extraction_hash, rule_ids, decision, reviewer, purpose="synthetic_demo"):
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.executemany("INSERT INTO reviews(study_id,extraction_hash,rule_id,decision,reviewer,purpose,reviewed_at) VALUES (?,?,?,?,?,?,?)",
                         [(study_id, extraction_hash, rule_id, decision, reviewer, purpose, now) for rule_id in set(rule_ids)])
    return get_reviews(study_id, extraction_hash)


def get_reviews(study_id, extraction_hash):
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM reviews WHERE study_id=? AND extraction_hash=? ORDER BY id", (study_id, extraction_hash)).fetchall()
    latest = {row["rule_id"]: dict(row) for row in rows}
    return list(latest.values())
