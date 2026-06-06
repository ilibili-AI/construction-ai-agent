"""
services/vapi_integration.py
"""

import os
import logging
from typing import Optional
from agent import ConstructionAgent

logger = logging.getLogger(__name__)

_call_sessions: dict[str, ConstructionAgent] = {}


def get_or_create_agent(call_id: str) -> ConstructionAgent:
    if call_id not in _call_sessions:
        logger.info("[Vapi] New call session: %s", call_id)
        _call_sessions[call_id] = ConstructionAgent()
    return _call_sessions[call_id]


def end_call_session(call_id: str) -> None:
    removed = _call_sessions.pop(call_id, None)
    if removed:
        logger.info("[Vapi] Closed call session: %s", call_id)


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
        logger.debug("[Vapi] No caller text in event '%s', skipping.", msg_type)
        return {"status": "no_content"}

    agent = get_or_create_agent(call_id)
    try:
        reply = agent.process_message(caller_text)
    except Exception as exc:
        logger.error("[Vapi] Agent error for call %s: %s", call_id, exc)
        reply = (
            "I'm sorry, I'm having a technical difficulty right now. "
            "Please hold and I'll connect you with someone shortly."
        )

    logger.info("[Vapi] call=%s | user=%r | sarah=%r", call_id, caller_text, reply)

    return build_vapi_response(reply)