from typing import List, Optional
from services.database import db_connect, now_iso, _db_lock


HANDOFF_TRIGGERS = [
    "exact price", "how much exactly", "guarantee", "legal",
    "permit advice", "engineering advice", "structural",
    "lawsuit", "attorney", "insurance claim", "i want to speak",
    "talk to a human", "talk to a person", "real person",
    "speak to someone", "manager please", "get me a manager",
]


def should_create_handoff(
    urgency: str,
    lead_quality: str,
    message: str,
    message_count: int,
    used_fallback: bool = False,
) -> tuple:
    lower = message.lower()

    if urgency == "Emergency":
        return True, "Emergency situation detected", "Emergency"

    if urgency == "High":
        return True, "High urgency request", "High"

    if lead_quality == "Hot Lead":
        return True, "Hot lead identified — immediate follow-up needed", "High"

    if any(trigger in lower for trigger in HANDOFF_TRIGGERS):
        return True, f"Caller requested human or asked sensitive question", "Normal"

    if used_fallback:
        return True, "AI fallback used — human review recommended", "Normal"

    if message_count >= 10:
        return True, "Long conversation — human follow-up recommended", "Normal"

    return False, "", "Normal"


def create_handoff(
    session_id: str,
    lead_id: Optional[int],
    reason: str,
    priority: str = "Normal",
) -> int:
    with _db_lock:
        conn = db_connect()
        try:
            cursor = conn.execute("""
                INSERT INTO handoffs (
                    lead_id, session_id, reason, priority, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                lead_id, session_id, reason, priority,
                "Pending", now_iso(), now_iso(),
            ))
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()


def get_handoffs(status: str = "all") -> List:
    conn = db_connect()
    try:
        if status != "all":
            return conn.execute(
                "SELECT * FROM handoffs WHERE status = ? ORDER BY created_at DESC LIMIT 100",
                (status,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM handoffs ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    finally:
        conn.close()


def update_handoff_status(handoff_id: int, status: str) -> bool:
    allowed = {"Pending", "In Progress", "Resolved", "Dismissed"}
    if status not in allowed:
        return False
    with _db_lock:
        conn = db_connect()
        try:
            cursor = conn.execute(
                "UPDATE handoffs SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), handoff_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()