from flask import Blueprint, request, jsonify, session, render_template
import uuid

from config import COMPANY_PROFILE, AGENCY_NAME
from services.database import log_message, get_conversation, upsert_lead
from services.lead_scoring import build_lead_profile, should_save_or_update_lead, lead_to_dict
from services.session_manager import get_agent_for_session, is_fallback_agent, reset_session_agent
from services.voice import make_audio_base64
from services.appointments import extract_appointment_request, create_appointment_request
from services.handoffs import should_create_handoff, create_handoff
from services.notifications import maybe_notify_manager

chat_bp = Blueprint("chat", __name__)


def get_session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return str(session["session_id"])


@chat_bp.route("/")
def index():
    get_session_id()
    return render_template(
        "index.html",
        company_name=COMPANY_PROFILE["company_name"],
        agency_name=AGENCY_NAME,
    )


@chat_bp.route("/chat", methods=["POST"])
def chat():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    user_message = str(data.get("message", "")).strip()

    if not user_message:
        return jsonify({"response": "Please type a message.", "audio": "", "lead_id": None}), 400

    log_message(session_id, "user", user_message)
    agent = get_agent_for_session(session_id)
    used_fallback = is_fallback_agent(session_id)

    try:
        response = str(agent.process_message(user_message)).strip()
    except Exception as e:
        print(f"[Chat] Agent error: {e}")
        response = "I can still help. Are you calling about a new project, urgent issue, or existing project?"

    if not response:
        response = "Could you please tell me more about your project?"

    log_message(session_id, "assistant", response)

    conversation_count = len(get_conversation(session_id, limit=160))
    lead_profile = build_lead_profile(session_id)
    lead_id = None

    if should_save_or_update_lead(lead_profile, conversation_count):
        lead_dict = lead_to_dict(lead_profile)
        lead_id = upsert_lead(session_id, lead_dict)

        maybe_notify_manager(lead_id, lead_dict)

        needs_handoff, reason, priority = should_create_handoff(
            urgency=lead_profile.urgency,
            lead_quality=lead_profile.lead_quality,
            message=user_message,
            message_count=conversation_count,
            used_fallback=used_fallback,
        )
        if needs_handoff:
            create_handoff(session_id, lead_id, reason, priority)

        appt = extract_appointment_request(user_message)
        if appt["wants_appointment"] and lead_id:
            create_appointment_request(
                session_id=session_id,
                lead_id=lead_id,
                full_name=lead_profile.full_name,
                phone=lead_profile.phone,
                appointment_date=appt["appointment_date"],
                appointment_time=appt["appointment_time"],
                appointment_type=appt["appointment_type"],
            )

    return jsonify({
        "response": response,
        "audio": make_audio_base64(response),
        "lead_id": lead_id,
        "lead_preview": lead_to_dict(lead_profile),
    })


@chat_bp.route("/reset-session", methods=["POST"])
def reset_session_route():
    session_id = get_session_id()
    reset_session_agent(session_id)
    session.pop("session_id", None)
    return jsonify({"success": True})