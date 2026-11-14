"""Small SQLite store for predictions and sales-rep feedback."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def connect() -> sqlite3.Connection:
    db_path = Path(os.getenv("APP_DB", "data/app/leadiq.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS predictions (
        id TEXT PRIMARY KEY, created_at TEXT, model_version TEXT, variant TEXT,
        probability REAL, band TEXT, features TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS feedback (
        prediction_id TEXT PRIMARY KEY, converted INTEGER, created_at TEXT)""")
    return con


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_prediction(pid: str, version: str, variant: str, prob: float, band: str, features: dict) -> None:
    with connect() as con:
        con.execute("INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (pid, now(), version, variant, prob, band, json.dumps(features)))


def save_feedback(pid: str, converted: bool) -> bool:
    with connect() as con:
        if con.execute("SELECT 1 FROM predictions WHERE id = ?", (pid,)).fetchone() is None:
            return False
        # A rep can change their mind, so the latest answer wins
        con.execute("INSERT OR REPLACE INTO feedback VALUES (?, ?, ?)", (pid, int(converted), now()))
    return True


def recent_predictions(limit: int = 1000) -> list[dict]:
    with connect() as con:
        rows = con.execute("""
            SELECT p.*, f.converted FROM predictions p
            LEFT JOIN feedback f ON f.prediction_id = p.id
            ORDER BY p.created_at DESC LIMIT ?""", (limit,)).fetchall()
    return [dict(r) for r in rows]


def labelled_leads() -> list[dict]:
    """Leads a rep has marked converted / lost: new training data."""
    with connect() as con:
        rows = con.execute("""
            SELECT p.features, f.converted FROM predictions p
            JOIN feedback f ON f.prediction_id = p.id""").fetchall()
    return [{**json.loads(r["features"]), "converted": r["converted"]} for r in rows]
