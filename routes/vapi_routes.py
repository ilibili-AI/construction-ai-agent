import os
import json
import logging
from flask import Blueprint, request, jsonify, Response, stream_with_context
from services.vapi_integration import get_or_create_agent

logger = logging.getLogger(__name__)

vapi_bp = Blueprint("vapi", __name__, url_prefix="/vapi")


@vapi_bp.route("/webhook", methods=["POST"])
def vapi_webhook():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Invalid JSON"}), 400
    from services.vapi_integration import handle_vapi_webhook
    response_data = handle_vapi_webhook(payload)
    return jsonify(response_data), 200


@vapi_bp.route("/webhook/chat/completions", methods=["POST"])
def vapi_chat_completions():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Invalid JSON"}), 400

    messages = payload.get("messages", [])
    caller_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            caller_text = msg.get("content", "")
            break

    if not caller_text:
        caller_text = "Hello"

    call_id = payload.get("call", {}).get("id", "unknown")
    agent = get_or_create_agent(call_id)
    reply = agent.process_message(caller_text)

    def generate():
        chunk = {
            "choices": [{
                "delta": {"role": "assistant", "content": reply},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        done = {
            "choices": [{
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(done)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@vapi_bp.route("/health", methods=["GET"])
def vapi_health():
    return jsonify({"status": "ok", "service": "vapi-webhook"}), 200