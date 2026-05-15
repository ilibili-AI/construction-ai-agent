from typing import Optional
from config import (
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER, MANAGER_PHONE,
)
from services.database import mark_lead_notified, lead_was_notified


def twilio_ready() -> bool:
    return all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, MANAGER_PHONE])


def build_sms_body(lead: dict) -> str:
    name = lead.get("full_name", "Unknown")
    phone = lead.get("phone", "Unknown")
    project = lead.get("project_type", "Unknown")
    location = lead.get("location", "Unknown")
    budget = lead.get("budget", "Unknown")
    quality = lead.get("lead_quality", "Unknown")
    score = lead.get("lead_score", 0)
    action = lead.get("recommended_action", "Review lead")

    return (
        f"BuildAI ALERT\n"
        f"Quality: {quality} ({score}/100)\n"
        f"Name: {name}\n"
        f"Phone: {phone}\n"
        f"Project: {project}\n"
        f"Location: {location}\n"
        f"Budget: {budget}\n"
        f"Action: {action}"
    )


def send_manager_sms(body: str) -> bool:
    if not twilio_ready():
        print("[Notifications] Twilio not configured — skipping SMS")
        return False
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=body[:1600],
            from_=TWILIO_PHONE_NUMBER,
            to=MANAGER_PHONE,
        )
        print("[Notifications] SMS sent to manager")
        return True
    except Exception as e:
        print(f"[Notifications] SMS failed: {e}")
        return False


def maybe_notify_manager(lead_id: int, lead: dict) -> bool:
    quality = lead.get("lead_quality", "")
    urgency = lead.get("urgency", "")

    should_notify = quality in {"Hot Lead", "Emergency"} or urgency in {"High", "Emergency"}

    if not should_notify:
        return False

    if lead_was_notified(lead_id):
        print(f"[Notifications] Lead {lead_id} already notified — skipping")
        return False

    body = build_sms_body(lead)
    sent = send_manager_sms(body)

    if sent:
        mark_lead_notified(lead_id)

    return sent