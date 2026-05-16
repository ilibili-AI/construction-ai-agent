import time
import threading
from typing import Any, Dict
from config import AGENT_TTL_SECONDS, COMPANY_PROFILE

_agent_lock = threading.Lock()
_session_agents: Dict[str, Dict[str, Any]] = {}


class SmartFallbackAgent:
    def __init__(self) -> None:
        self.history = []

    def process_message(self, message: str) -> str:
        lower = message.lower()
        self.history.append({"role": "user", "content": message})

        if any(w in lower for w in ["emergency", "fire", "flood", "gas", "collapse"]):
            reply = "This sounds urgent. If there is immediate danger please call 911. Can I get your name, phone number, and address so I can alert the team right away?"
        elif any(w in lower for w in ["schedule", "appointment", "consultation", "meeting"]):
            reply = "I can help with that. What is your name, phone number, preferred date and time, and what type of project is it?"
        elif any(w in lower for w in ["quote", "estimate", "price", "cost"]):
            reply = "I can collect your project details for the team. What type of project, where is it located, and what is your budget range?"
        elif any(w in lower for w in ["subcontractor", "vendor", "supplier"]):
            reply = "Thanks for reaching out. Please share your company name, trade, license number, service area, and best contact info."
        else:
            reply = "Thanks for contacting us. To route this correctly, can you share your name, phone number, project location, and what you need help with?"

        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        self.history = []


def cleanup_session_agents() -> None:
    cutoff = time.time() - AGENT_TTL_SECONDS
    expired = [sid for sid, data in _session_agents.items() if data.get("last_seen", 0) < cutoff]
    for sid in expired:
        _session_agents.pop(sid, None)
    if expired:
        print(f"[SessionManager] Cleaned up {len(expired)} expired sessions")


def get_agent_for_session(session_id: str) -> Any:
    with _agent_lock:
        cleanup_session_agents()

        if session_id not in _session_agents:
            try:
                from agent import ConstructionAgent
                agent = ConstructionAgent(
                    company_name=COMPANY_PROFILE["company_name"],
                    phone=COMPANY_PROFILE["phone"],
                    email=COMPANY_PROFILE["email"],
                    services=COMPANY_PROFILE["services"],
                    area=COMPANY_PROFILE["area"],
                )
            except Exception as e:
                print(f"[SessionManager] ConstructionAgent failed: {e} — using fallback")
                agent = SmartFallbackAgent()

            _session_agents[session_id] = {
                "agent": agent,
                "last_seen": time.time(),
                "is_fallback": isinstance(agent, SmartFallbackAgent),
            }

        _session_agents[session_id]["last_seen"] = time.time()
        return _session_agents[session_id]["agent"]


def is_fallback_agent(session_id: str) -> bool:
    with _agent_lock:
        data = _session_agents.get(session_id, {})
        return data.get("is_fallback", False)


def reset_session_agent(session_id: str) -> None:
    with _agent_lock:
        _session_agents.pop(session_id, None)