from typing import List, Optional
import re
from services.database import db_connect, now_iso, _db_lock


def create_appointment_request(
    session_id: str,
    lead_id: Optional[int],
    full_name: str,
    phone: str,
    appointment_date: str = "",
    appointment_time: str = "",
    appointment_type: str = "Consultation",
) -> int:
    with _db_lock:
        conn = db_connect()
        try:
            cursor = conn.execute("""
                INSERT INTO appointments (
                    lead_id, session_id, full_name, phone,
                    appointment_date, appointment_time, appointment_type,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead_id, session_id, full_name, phone,
                appointment_date, appointment_time, appointment_type,
                "Requested", now_iso(), now_iso(),
            ))
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()


def update_appointment_status(appointment_id: int, status: str) -> bool:
    allowed = {"Requested", "Confirmed", "Rescheduled", "Canceled"}
    if status not in allowed:
        return False
    with _db_lock:
        conn = db_connect()
        try:
            cursor = conn.execute(
                "UPDATE appointments SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), appointment_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def get_appointments(session_id: Optional[str] = None, status: str = "all") -> List:
    conn = db_connect()
    try:
        clauses, params = [], []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if status != "all":
            clauses.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return conn.execute(
            f"SELECT * FROM appointments {where} ORDER BY created_at DESC LIMIT 100",
            params,
        ).fetchall()
    finally:
        conn.close()


def cancel_appointment(appointment_id: int) -> bool:
    return update_appointment_status(appointment_id, "Canceled")


def extract_appointment_request(text: str) -> dict:
    lower = text.lower()

    wants_appointment = any(x in lower for x in [
        "schedule", "appointment", "consultation", "meet", "meeting",
        "come out", "visit", "book", "set up a time", "available",
    ])

    date = ""
    time = ""

    date_patterns = [
        r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        r"(?:tomorrow|next week|this week)",
        r"\d{1,2}[\/\-]\d{1,2}(?:[\/\-]\d{2,4})?",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, lower)
        if match:
            date = match.group(0)
            break

    time_patterns = [
        r"\d{1,2}(?::\d{2})?\s?(?:am|pm)",
        r"(?:morning|afternoon|evening|noon)",
    ]
    for pattern in time_patterns:
        match = re.search(pattern, lower)
        if match:
            time = match.group(0)
            break

    return {
        "wants_appointment": wants_appointment,
        "appointment_date": date,
        "appointment_time": time,
        "appointment_type": "Consultation",
    }