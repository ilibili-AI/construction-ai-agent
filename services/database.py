import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import DATABASE_PATH

_db_lock = threading.Lock()


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    with _db_lock:
        conn = db_connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    full_name TEXT DEFAULT 'Unknown',
                    phone TEXT DEFAULT 'Unknown',
                    email TEXT DEFAULT 'Unknown',
                    project_type TEXT DEFAULT 'General Construction',
                    project_scope TEXT DEFAULT 'Unknown',
                    budget TEXT DEFAULT 'Unknown',
                    location TEXT DEFAULT 'Unknown',
                    property_type TEXT DEFAULT 'Unknown',
                    timeline TEXT DEFAULT 'Unknown',
                    urgency TEXT DEFAULT 'Normal',
                    lead_score INTEGER DEFAULT 0,
                    lead_quality TEXT DEFAULT 'Needs Review',
                    missing_info TEXT DEFAULT '',
                    recommended_action TEXT DEFAULT 'Needs human review',
                    summary TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    manager_notes TEXT DEFAULT '',
                    notified_at TEXT DEFAULT '',
                    status TEXT DEFAULT 'New',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER,
                    session_id TEXT NOT NULL,
                    full_name TEXT DEFAULT 'Unknown',
                    phone TEXT DEFAULT 'Unknown',
                    appointment_date TEXT DEFAULT '',
                    appointment_time TEXT DEFAULT '',
                    appointment_type TEXT DEFAULT 'Consultation',
                    status TEXT DEFAULT 'Requested',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS handoffs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER,
                    session_id TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    priority TEXT DEFAULT 'Normal',
                    status TEXT DEFAULT 'Pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_session ON leads(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id)")
            conn.commit()
        finally:
            conn.close()


def log_message(session_id: str, sender: str, message: str) -> None:
    with _db_lock:
        conn = db_connect()
        try:
            conn.execute(
                "INSERT INTO conversations (session_id, sender, message, created_at) VALUES (?, ?, ?, ?)",
                (session_id, sender, message, now_iso()),
            )
            conn.commit()
        finally:
            conn.close()


def get_conversation(session_id: str, limit: int = 80) -> List[sqlite3.Row]:
    conn = db_connect()
    try:
        rows = conn.execute(
            "SELECT sender, message, created_at FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return rows[::-1]
    finally:
        conn.close()


def transcript_for_session(session_id: str, sender: Optional[str] = None) -> str:
    rows = get_conversation(session_id, limit=160)
    if sender:
        rows = [r for r in rows if r["sender"] == sender]
    return "\n".join(str(r["message"]) for r in rows)


def get_existing_lead(session_id: str) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            "SELECT * FROM leads WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()


def upsert_lead(session_id: str, payload: Dict[str, Any]) -> int:
    with _db_lock:
        conn = db_connect()
        try:
            existing = conn.execute(
                "SELECT id FROM leads WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()

            if existing:
                lead_id = int(existing["id"])
                conn.execute("""
                    UPDATE leads SET
                        full_name=?, phone=?, email=?, project_type=?, project_scope=?,
                        budget=?, location=?, property_type=?, timeline=?, urgency=?,
                        lead_score=?, lead_quality=?, missing_info=?, recommended_action=?,
                        summary=?, notes=?, updated_at=?
                    WHERE id=?
                """, (
                    payload.get("full_name", "Unknown"),
                    payload.get("phone", "Unknown"),
                    payload.get("email", "Unknown"),
                    payload.get("project_type", "General Construction"),
                    payload.get("project_scope", "Unknown"),
                    payload.get("budget", "Unknown"),
                    payload.get("location", "Unknown"),
                    payload.get("property_type", "Unknown"),
                    payload.get("timeline", "Unknown"),
                    payload.get("urgency", "Normal"),
                    payload.get("lead_score", 0),
                    payload.get("lead_quality", "Needs Review"),
                    payload.get("missing_info", ""),
                    payload.get("recommended_action", "Needs human review"),
                    payload.get("summary", ""),
                    payload.get("notes", ""),
                    now_iso(),
                    lead_id,
                ))
            else:
                cursor = conn.execute("""
                    INSERT INTO leads (
                        session_id, full_name, phone, email, project_type, project_scope,
                        budget, location, property_type, timeline, urgency, lead_score,
                        lead_quality, missing_info, recommended_action, summary, notes,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id,
                    payload.get("full_name", "Unknown"),
                    payload.get("phone", "Unknown"),
                    payload.get("email", "Unknown"),
                    payload.get("project_type", "General Construction"),
                    payload.get("project_scope", "Unknown"),
                    payload.get("budget", "Unknown"),
                    payload.get("location", "Unknown"),
                    payload.get("property_type", "Unknown"),
                    payload.get("timeline", "Unknown"),
                    payload.get("urgency", "Normal"),
                    payload.get("lead_score", 0),
                    payload.get("lead_quality", "Needs Review"),
                    payload.get("missing_info", ""),
                    payload.get("recommended_action", "Needs human review"),
                    payload.get("summary", ""),
                    payload.get("notes", ""),
                    now_iso(),
                    now_iso(),
                ))
                lead_id = int(cursor.lastrowid)

            conn.commit()
            return lead_id
        finally:
            conn.close()


def fetch_leads(status: str = "all", quality: str = "all", urgency: str = "all", search: str = "") -> List[sqlite3.Row]:
    clauses, params = [], []
    if status != "all":
        clauses.append("status = ?")
        params.append(status)
    if quality != "all":
        clauses.append("lead_quality = ?")
        params.append(quality)
    if urgency != "all":
        clauses.append("urgency = ?")
        params.append(urgency)
    if search:
        like = f"%{search}%"
        clauses.append("(full_name LIKE ? OR phone LIKE ? OR project_type LIKE ? OR location LIKE ?)")
        params.extend([like, like, like, like])

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    conn = db_connect()
    try:
        return conn.execute(f"""
            SELECT * FROM leads {where}
            ORDER BY
                CASE urgency WHEN 'Emergency' THEN 1 WHEN 'High' THEN 2 ELSE 3 END,
                lead_score DESC, updated_at DESC
            LIMIT 300
        """, params).fetchall()
    finally:
        conn.close()


def fetch_lead_by_id(lead_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    finally:
        conn.close()


def update_lead_status(lead_id: int, status: str) -> bool:
    allowed = {"New", "Contacted", "Scheduled", "Proposal Sent", "Won", "Lost"}
    if status not in allowed:
        return False
    with _db_lock:
        conn = db_connect()
        try:
            cursor = conn.execute(
                "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), lead_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def update_manager_notes(lead_id: int, notes: str) -> bool:
    with _db_lock:
        conn = db_connect()
        try:
            cursor = conn.execute(
                "UPDATE leads SET manager_notes = ?, updated_at = ? WHERE id = ?",
                (notes[:3000], now_iso(), lead_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def mark_lead_notified(lead_id: int) -> None:
    with _db_lock:
        conn = db_connect()
        try:
            conn.execute(
                "UPDATE leads SET notified_at = ?, updated_at = ? WHERE id = ?",
                (now_iso(), now_iso(), lead_id),
            )
            conn.commit()
        finally:
            conn.close()


def lead_was_notified(lead_id: int) -> bool:
    conn = db_connect()
    try:
        row = conn.execute("SELECT notified_at FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return bool(row and row["notified_at"])
    finally:
        conn.close()


def dashboard_stats() -> Dict[str, int]:
    conn = db_connect()
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        total = conn.execute("SELECT COUNT(*) AS c FROM leads").fetchone()["c"]
        hot = conn.execute("SELECT COUNT(*) AS c FROM leads WHERE lead_quality IN ('Hot Lead', 'Emergency')").fetchone()["c"]
        urgent = conn.execute("SELECT COUNT(*) AS c FROM leads WHERE urgency IN ('High', 'Emergency')").fetchone()["c"]
        scheduled = conn.execute("SELECT COUNT(*) AS c FROM leads WHERE status = 'Scheduled'").fetchone()["c"]
        today_count = conn.execute("SELECT COUNT(*) AS c FROM leads WHERE created_at LIKE ?", (f"{today}%",)).fetchone()["c"]
        return {"total": total, "hot": hot, "urgent": urgent, "scheduled": scheduled, "today": today_count}
    finally:
        conn.close()