from typing import List, Optional
from services.database import _get_client, now_iso

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
        return True, "Caller requested human or asked sensitive question", "Normal"
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
    res = _get_client().table("handoffs").insert({
        "lead_id": lead_id,
        "session_id": session_id,
        "reason": reason,
        "priority": priority,
        "status": "Pending",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }).execute()
    return res.data[0]["id"]


def get_handoffs(status: str = "all") -> List:
    q = _get_client().table("handoffs").select("*")
    if status != "all":
        q = q.eq("status", status)
    res = q.order("created_at", desc=True).limit(100).execute()
    return res.data or []


def update_handoff_status(handoff_id: int, status: str) -> bool:
    allowed = {"Pending", "In Progress", "Resolved", "Dismissed"}
    if status not in allowed:
        return False
    res = _get_client().table("handoffs").update({
        "status": status,
        "updated_at": now_iso(),
    }).eq("id", handoff_id).execute()
    return bool(res.data)