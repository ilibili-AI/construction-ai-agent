from typing import List, Optional
import re
from services.database import _get_client, now_iso


def create_appointment_request(
    session_id: str,
    lead_id: Optional[int],
    full_name: str,
    phone: str,
    appointment_date: str = "",
    appointment_time: str = "",
    appointment_type: str = "Consultation",
) -> int:
    res = _get_client().table("appointments").insert({
        "lead_id": lead_id,
        "session_id": session_id,
        "full_name": full_name,
        "phone": phone,
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "appointment_type": appointment_type,
        "status": "Requested",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }).execute()
    return res.data[0]["id"]


def update_appointment_status(appointment_id: int, status: str) -> bool:
    allowed = {"Requested", "Confirmed", "Rescheduled", "Canceled"}
    if status not in allowed:
        return False
    res = _get_client().table("appointments").update({
        "status": status,
        "updated_at": now_iso(),
    }).eq("id", appointment_id).execute()
    return bool(res.data)


def get_appointments(session_id: Optional[str] = None, status: str = "all") -> List:
    q = _get_client().table("appointments").select("*")
    if session_id:
        q = q.eq("session_id", session_id)
    if status != "all":
        q = q.eq("status", status)
    res = q.order("created_at", desc=True).limit(100).execute()
    return res.data or []


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