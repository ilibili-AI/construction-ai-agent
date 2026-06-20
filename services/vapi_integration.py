"""
services/vapi_integration.py
"""

import os
import re
import logging
from datetime import datetime, timedelta
from typing import Optional
from agent import ConstructionAgent
from services.database import _get_client, now_iso

logger = logging.getLogger(__name__)

_call_sessions: dict[str, ConstructionAgent] = {}

DAY_NAME_TO_OFFSET = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4,
}

TIME_WORDS = {
    "9": "9:00 AM", "9am": "9:00 AM", "9 am": "9:00 AM",
    "10": "10:00 AM", "10am": "10:00 AM", "10 am": "10:00 AM",
    "11": "11:00 AM", "11am": "11:00 AM", "11 am": "11:00 AM",
    "12": "12:00 PM", "noon": "12:00 PM", "12pm": "12:00 PM",
    "1": "1:00 PM", "1pm": "1:00 PM", "1 pm": "1:00 PM",
    "2": "2:00 PM", "2pm": "2:00 PM", "2 pm": "2:00 PM",
    "3": "3:00 PM", "3pm": "3:00 PM", "3 pm": "3:00 PM",
    "4": "4:00 PM", "4pm": "4:00 PM", "4 pm": "4:00 PM",
    "morning": "9:00 AM",
    "afternoon": "2:00 PM",
}


def get_or_create_agent(call_id: str) -> ConstructionAgent:
    if call_id not in _call_sessions:
        logger.info("[Vapi] New call session: %s", call_id)
        _call_sessions[call_id] = ConstructionAgent()
    return _call_sessions[call_id]


def end_call_session(call_id: str) -> None:
    removed = _call_sessions.pop(call_id, None)
    if removed:
        logger.info("[Vapi] Closed call session: %s", call_id)


def get_available_slots() -> str:
    try:
        res = (
            _get_client()
            .table("time_slots")
            .select("slot_date, slot_time")
            .eq("is_booked", False)
            .order("slot_date")
            .order("slot_time")
            .execute()
        )
        slots = res.data or []
        if not slots:
            return "No available slots next week."

        grouped = {}
        for slot in slots:
            date = slot["slot_date"]
            time = slot["slot_time"]
            grouped.setdefault(date, []).append(time)

        lines = ["Available appointment slots for next week:"]
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        for i, (date, times) in enumerate(grouped.items()):
            day_name = days[i] if i < len(days) else date
            lines.append(f"{day_name}: {', '.join(times)}")

        return "\n".join(lines)
    except Exception as exc:
        logger.error("[Vapi] Error fetching slots: %s", exc)
        return "Available Monday through Friday, 9 AM to 5 PM next week."


def book_slot(slot_date: str, slot_time: str, session_id: str, lead_id=None) -> bool:
    try:
        res = (
            _get_client()
            .table("time_slots")
            .update({
                "is_booked": True,
                "session_id": session_id,
                "lead_id": lead_id,
            })
            .eq("slot_date", slot_date)
            .eq("slot_time", slot_time)
            .eq("is_booked", False)
            .execute()
        )
        return bool(res.data)
    except Exception as exc:
        logger.error("[Vapi] Error booking slot: %s", exc)
        return False


def _get_next_week_monday() -> datetime:
    """تاریخ دوشنبه هفته بعد رو بر اساس امروز حساب می‌کنه."""
    today = datetime.now()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)
    return next_monday


def parse_day_and_time(text: str):
    """
    از روی متن caller (مثلاً 'Monday at two PM') روز و ساعت رو پیدا می‌کنه
    و تاریخ دقیق رو برمی‌گردونه.
    """
    lower = text.lower()

    # پیدا کردن روز هفته
    day_offset = None
    for day_name, offset in DAY_NAME_TO_OFFSET.items():
        if day_name in lower:
            day_offset = offset
            break

    if day_offset is None:
        return None, None

    # محاسبه تاریخ دقیق
    monday = _get_next_week_monday()
    target_date = monday + timedelta(days=day_offset)
    slot_date = target_date.strftime("%Y-%m-%d")

    # پیدا کردن ساعت
    slot_time = None

    # الگوهای رایج ساعت: "2 pm", "2pm", "two pm", "at 2"
    time_pattern = re.search(r'\b(\d{1,2})\s*(am|pm)\b', lower)
    if time_pattern:
        hour = time_pattern.group(1)
        period = time_pattern.group(2)
        key = f"{hour}{period}"
        slot_time = TIME_WORDS.get(key) or TIME_WORDS.get(hour)

    if not slot_time:
        for word, mapped_time in TIME_WORDS.items():
            if word in lower:
                slot_time = mapped_time
                break

    # تبدیل اعداد نوشتاری به رقم (one, two, three...)
    word_to_num = {
        "one": "1", "two": "2", "three": "3", "four": "4",
        "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    }
    if not slot_time:
        for word, num in word_to_num.items():
            if word in lower:
                period = "pm" if "pm" in lower or word in ["one", "two", "three", "four"] else "am"
                key = f"{num}{period}"
                slot_time = TIME_WORDS.get(key) or TIME_WORDS.get(num)
                break

    return slot_date, slot_time


def extract_caller_message(payload: dict) -> Optional[str]:
    msg_type = payload.get("type", "")

    if msg_type == "transcript":
        role = payload.get("role", "")
        transcript = payload.get("transcript", "")
        if role == "user" and transcript:
            return transcript.strip()

    if msg_type == "assistant-request":
        messages = payload.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if content:
                    return content.strip()

    if msg_type == "function-call":
        func = payload.get("functionCall", {})
        name = func.get("name", "unknown_function")
        params = func.get("parameters", {})
        return f"[Function called: {name} with params: {params}]"

    return None


def build_vapi_response(reply_text: str) -> dict:
    return {
        "role": "assistant",
        "content": reply_text,
    }


def handle_vapi_webhook(payload: dict) -> dict:
    call_id: str = payload.get("callId", "unknown")
    msg_type: str = payload.get("type", "")

    logger.info("[Vapi] Event '%s' for call %s", msg_type, call_id)

    if msg_type in ("end-of-call-report", "hang"):
        end_call_session(call_id)
        return {"status": "ok"}

    caller_text = extract_caller_message(payload)

    if not caller_text:
        return {"status": "no_content"}

    agent = get_or_create_agent(call_id)

    appointment_keywords = [
        "appointment", "schedule", "available", "book",
        "when", "day", "time", "next week", "monday",
        "tuesday", "wednesday", "thursday", "friday",
        "morning", "afternoon", "noon", "am", "pm"
    ]
    lower = caller_text.lower()
    if any(kw in lower for kw in appointment_keywords):
        slots_info = get_available_slots()
        enhanced_message = f"{caller_text}\n\n[SYSTEM: {slots_info}]"
    else:
        enhanced_message = caller_text

    try:
        reply = agent.process_message(enhanced_message)
    except Exception as exc:
        logger.error("[Vapi] Agent error for call %s: %s", call_id, exc)
        reply = (
            "I'm sorry, I'm having a technical difficulty right now. "
            "Please hold and I'll connect you with someone shortly."
        )

    # روز و ساعت رو از حرف خود caller پیدا کن (نه از جواب Sarah)
    slot_date, slot_time = parse_day_and_time(caller_text)
    if slot_date and slot_time:
        booked = book_slot(slot_date, slot_time, call_id)
        if booked:
            logger.info("[Vapi] ✅ Slot booked: %s %s for call %s", slot_date, slot_time, call_id)
        else:
            logger.warning("[Vapi] ❌ Slot already taken or not found: %s %s", slot_date, slot_time)

    logger.info("[Vapi] call=%s | user=%r | sarah=%r", call_id, caller_text, reply)

    return build_vapi_response(reply)