from __future__ import annotations

import base64
import csv
import io
import json
import hmac
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, Response, jsonify, redirect, render_template_string, request, session

try:
    from gtts import gTTS
except Exception:
    gTTS = None

try:
    from agent import ConstructionAgent
except Exception:
    ConstructionAgent = None


APP_NAME = "A & I Construction Agent"
AGENT_NAME = "Sarah"
DATABASE_PATH = os.getenv("DATABASE_PATH", "buildai.db")
LEADS_FILE = os.getenv("LEADS_FILE", "leads.json")
ENABLE_TTS = os.getenv("ENABLE_TTS", "true").lower() == "true"
APP_ENV = os.getenv("APP_ENV", "development").lower()
AGENT_TTL_SECONDS = int(os.getenv("AGENT_TTL_SECONDS", "21600"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
ADMIN_SESSION_KEY = "admin_authenticated"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
MANAGER_PHONE = os.getenv("MANAGER_PHONE", "").strip()

COMPANY_PROFILE = {
    "company_name": os.getenv("COMPANY_NAME", "A & I Construction Agent"),
    "phone": os.getenv("COMPANY_PHONE", "(555) 010-2040"),
    "email": os.getenv("COMPANY_EMAIL", "office@example.com"),
    "services": os.getenv(
        "COMPANY_SERVICES",
        "custom homes, remodels, ADUs, roofing, concrete, tenant improvements",
    ),
    "area": os.getenv("SERVICE_AREA", "Los Angeles, Orange County, San Diego"),
}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-this-before-production")

_db_lock = threading.Lock()
_agent_lock = threading.Lock()
_session_agents: Dict[str, Dict[str, Any]] = {}


@dataclass
class LeadProfile:
    full_name: str = "Unknown"
    phone: str = "Unknown"
    email: str = "Unknown"
    project_type: str = "General Construction"
    project_scope: str = "Unknown"
    budget: str = "Unknown"
    location: str = "Unknown"
    property_type: str = "Unknown"
    timeline: str = "Unknown"
    urgency: str = "Normal"
    lead_score: int = 0
    lead_quality: str = "Needs Review"
    missing_info: str = ""
    recommended_action: str = "Needs human review"
    summary: str = ""
    notes: str = ""


PROJECT_KEYWORDS = {
    "Kitchen Remodel": ["kitchen"],
    "Bathroom Remodel": ["bathroom", "restroom"],
    "ADU": ["adu", "accessory dwelling", "guest house"],
    "Roofing": ["roof", "roofing", "roof leak", "shingle"],
    "Flooring": ["floor", "flooring", "tile", "hardwood", "vinyl plank"],
    "Concrete": ["concrete", "driveway", "slab", "foundation", "patio"],
    "Commercial Construction": ["commercial", "office", "tenant improvement", "retail", "restaurant"],
    "New Home Construction": ["new home", "build a house", "house build", "ground up", "custom home"],
    "Addition": ["addition", "add room", "extension", "second story"],
    "Renovation": ["renovation", "remodel", "renovate"],
    "Repair": ["repair", "fix", "damage"],
}

CITY_HINTS = [
    "los angeles",
    "orange county",
    "san diego",
    "santa monica",
    "pasadena",
    "irvine",
    "anaheim",
    "long beach",
    "glendale",
    "burbank",
    "beverly hills",
    "torrance",
    "sherman oaks",
    "van nuys",
    "culver city",
]

EMERGENCY_WORDS = [
    "emergency",
    "fire",
    "gas smell",
    "flood",
    "flooding",
    "spark",
    "sparks",
    "collapse",
    "structural failure",
    "unsafe",
    "injury",
    "leaking badly",
    "active leak",
    "sewer backup",
]

HIGH_URGENCY_WORDS = [
    "urgent",
    "asap",
    "today",
    "tomorrow",
    "deadline",
    "inspection",
    "permit issue",
    "complaint",
]

LOW_INTENT_WORDS = [
    "just shopping",
    "cheapest",
    "free advice",
    "no budget",
    "maybe later",
]


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    with _db_lock:
        conn = db_connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    full_name TEXT DEFAULT 'Unknown',
                    phone TEXT DEFAULT 'Unknown',
                    email TEXT DEFAULT 'Unknown',
                    project_type TEXT DEFAULT 'General Construction',
                    project_scope TEXT DEFAULT 'Unknown',
                    budget TEXT DEFAULT 'Unknown',
                    location TEXT DEFAULT 'Unknown',
                    property_type TEXT DEFAULT 'Unknown',
                    timeline TEXT DEFAULT 'Unknown',
                    urgency TEXT DEFAULT 'Normal',
                    lead_score INTEGER DEFAULT 0,
                    lead_quality TEXT DEFAULT 'Needs Review',
                    missing_info TEXT DEFAULT '',
                    recommended_action TEXT DEFAULT 'Needs human review',
                    summary TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    manager_notes TEXT DEFAULT '',
                    notified_at TEXT DEFAULT '',
                    status TEXT DEFAULT 'New',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_session ON leads(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id)")
            ensure_column(conn, "leads", "notified_at", "TEXT DEFAULT ''")
            conn.commit()
        finally:
            conn.close()


def legacy_timestamp_to_iso(value: str) -> str:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds")
        except ValueError:
            pass
    return now_iso()


def migrate_legacy_leads() -> None:
    if not os.path.exists(LEADS_FILE):
        return

    with _db_lock:
        conn = db_connect()
        try:
            count = conn.execute("SELECT COUNT(*) AS c FROM leads").fetchone()["c"]
            if count:
                return

            with open(LEADS_FILE, "r", encoding="utf-8") as file:
                legacy = json.load(file)

            if not isinstance(legacy, list):
                return

            for item in legacy:
                if not isinstance(item, dict):
                    continue

                created_at = legacy_timestamp_to_iso(str(item.get("timestamp", "")))
                session_id = f"legacy-{item.get('id', uuid.uuid4())}"
                project_type = str(item.get("project_type", "General Construction") or "General Construction")
                notes = str(item.get("notes", "") or "")
                profile = LeadProfile(
                    full_name=str(item.get("name", "Unknown") or "Unknown"),
                    phone=str(item.get("phone", "Unknown") or "Unknown"),
                    project_type=project_type,
                    budget=str(item.get("budget", "Unknown") or "Unknown"),
                    location=str(item.get("location", "Unknown") or "Unknown"),
                    notes=notes,
                )
                profile.missing_info = missing_fields(profile)
                profile.lead_score, profile.lead_quality, profile.recommended_action = score_lead(profile, notes)
                profile.summary = build_summary(profile)

                conn.execute(
                    """
                    INSERT INTO leads (
                        session_id, full_name, phone, email, project_type, project_scope,
                        budget, location, property_type, timeline, urgency, lead_score,
                        lead_quality, missing_info, recommended_action, summary, notes,
                        status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        profile.full_name,
                        profile.phone,
                        profile.email,
                        profile.project_type,
                        profile.project_scope,
                        profile.budget,
                        profile.location,
                        profile.property_type,
                        profile.timeline,
                        profile.urgency,
                        profile.lead_score,
                        profile.lead_quality,
                        profile.missing_info,
                        profile.recommended_action,
                        profile.summary,
                        profile.notes,
                        str(item.get("status", "New") or "New"),
                        created_at,
                        created_at,
                    ),
                )

            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()


def log_message(session_id: str, sender: str, message: str) -> None:
    with _db_lock:
        conn = db_connect()
        try:
            conn.execute(
                "INSERT INTO conversations (session_id, sender, message, created_at) VALUES (?, ?, ?, ?)",
                (session_id, sender, message, now_iso()),
            )
            conn.commit()
        finally:
            conn.close()


def get_conversation(session_id: str, limit: int = 80) -> List[sqlite3.Row]:
    conn = db_connect()
    try:
        rows = conn.execute(
            """
            SELECT sender, message, created_at
            FROM conversations
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return rows[::-1]
    finally:
        conn.close()


def transcript_for_session(session_id: str, sender: Optional[str] = None) -> str:
    rows = get_conversation(session_id, limit=160)
    if sender:
        rows = [row for row in rows if row["sender"] == sender]
    return "\n".join(str(row["message"]) for row in rows)


def get_existing_lead(session_id: str) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            "SELECT * FROM leads WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()


def first_known(new_value: str, old_value: Optional[str], fallback: str = "Unknown") -> str:
    if new_value and new_value != "Unknown":
        return new_value
    if old_value and old_value != "Unknown":
        return old_value
    return fallback


def upsert_lead(session_id: str, lead: LeadProfile) -> int:
    payload = asdict(lead)

    with _db_lock:
        conn = db_connect()
        try:
            existing = conn.execute(
                "SELECT id FROM leads WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()

            if existing:
                lead_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE leads
                    SET full_name=?, phone=?, email=?, project_type=?, project_scope=?,
                        budget=?, location=?, property_type=?, timeline=?, urgency=?,
                        lead_score=?, lead_quality=?, missing_info=?, recommended_action=?,
                        summary=?, notes=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        payload["full_name"],
                        payload["phone"],
                        payload["email"],
                        payload["project_type"],
                        payload["project_scope"],
                        payload["budget"],
                        payload["location"],
                        payload["property_type"],
                        payload["timeline"],
                        payload["urgency"],
                        payload["lead_score"],
                        payload["lead_quality"],
                        payload["missing_info"],
                        payload["recommended_action"],
                        payload["summary"],
                        payload["notes"],
                        now_iso(),
                        lead_id,
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO leads (
                        session_id, full_name, phone, email, project_type, project_scope,
                        budget, location, property_type, timeline, urgency, lead_score,
                        lead_quality, missing_info, recommended_action, summary, notes,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        payload["full_name"],
                        payload["phone"],
                        payload["email"],
                        payload["project_type"],
                        payload["project_scope"],
                        payload["budget"],
                        payload["location"],
                        payload["property_type"],
                        payload["timeline"],
                        payload["urgency"],
                        payload["lead_score"],
                        payload["lead_quality"],
                        payload["missing_info"],
                        payload["recommended_action"],
                        payload["summary"],
                        payload["notes"],
                        now_iso(),
                        now_iso(),
                    ),
                )
                lead_id = int(cursor.lastrowid)

            conn.commit()
            return lead_id
        finally:
            conn.close()


def update_lead_status(lead_id: int, status: str) -> bool:
    allowed = {"New", "Contacted", "Scheduled", "Proposal Sent", "Won", "Lost"}
    if status not in allowed:
        return False

    with _db_lock:
        conn = db_connect()
        try:
            cursor = conn.execute(
                "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), lead_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def update_manager_notes(lead_id: int, notes: str) -> bool:
    with _db_lock:
        conn = db_connect()
        try:
            cursor = conn.execute(
                "UPDATE leads SET manager_notes = ?, updated_at = ? WHERE id = ?",
                (notes[:3000], now_iso(), lead_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def mark_lead_notified(lead_id: int) -> None:
    with _db_lock:
        conn = db_connect()
        try:
            conn.execute("UPDATE leads SET notified_at = ? WHERE id = ?", (now_iso(), lead_id))
            conn.commit()
        finally:
            conn.close()


def lead_was_notified(lead_id: int) -> bool:
    conn = db_connect()
    try:
        row = conn.execute("SELECT notified_at FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return bool(row and row["notified_at"])
    finally:
        conn.close()


def fetch_leads(status: str = "all", quality: str = "all", urgency: str = "all", search: str = "") -> List[sqlite3.Row]:
    clauses: List[str] = []
    params: List[Any] = []

    if status != "all":
        clauses.append("status = ?")
        params.append(status)
    if quality != "all":
        clauses.append("lead_quality = ?")
        params.append(quality)
    if urgency != "all":
        clauses.append("urgency = ?")
        params.append(urgency)
    if search:
        like = f"%{search}%"
        clauses.append(
            "(full_name LIKE ? OR phone LIKE ? OR email LIKE ? OR project_type LIKE ? OR location LIKE ? OR summary LIKE ?)"
        )
        params.extend([like, like, like, like, like, like])

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    conn = db_connect()
    try:
        return conn.execute(
            f"""
            SELECT *
            FROM leads
            {where}
            ORDER BY
                CASE urgency
                    WHEN 'Emergency' THEN 1
                    WHEN 'High' THEN 2
                    WHEN 'Normal' THEN 3
                    ELSE 4
                END,
                lead_score DESC,
                updated_at DESC
            LIMIT 300
            """,
            params,
        ).fetchall()
    finally:
        conn.close()


def fetch_lead_by_id(lead_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    finally:
        conn.close()


def dashboard_stats() -> Dict[str, int]:
    conn = db_connect()
    try:
        today_prefix = datetime.now(timezone.utc).date().isoformat()
        total = conn.execute("SELECT COUNT(*) AS c FROM leads").fetchone()["c"]
        hot = conn.execute("SELECT COUNT(*) AS c FROM leads WHERE lead_quality IN ('Hot Lead', 'Emergency')").fetchone()["c"]
        urgent = conn.execute("SELECT COUNT(*) AS c FROM leads WHERE urgency IN ('High', 'Emergency')").fetchone()["c"]
        scheduled = conn.execute("SELECT COUNT(*) AS c FROM leads WHERE status = 'Scheduled'").fetchone()["c"]
        today = conn.execute(
            "SELECT COUNT(*) AS c FROM leads WHERE created_at LIKE ?",
            (f"{today_prefix}%",),
        ).fetchone()["c"]
        return {"total": total, "hot": hot, "urgent": urgent, "scheduled": scheduled, "today": today}
    finally:
        conn.close()


def get_session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return str(session["session_id"])


class SmartFallbackAgent:
    def __init__(self) -> None:
        self.history: List[Dict[str, str]] = []

    def process_message(self, message: str) -> str:
        self.history.append({"role": "user", "content": message})
        lower = message.lower()

        if any(word in lower for word in EMERGENCY_WORDS):
            reply = (
                "I can mark this urgent and collect the details for immediate review. "
                "If anyone is in danger, call emergency services now. What is the project address and best callback number?"
            )
        elif any(word in lower for word in ["subcontractor", "vendor", "supplier", "crew"]):
            reply = (
                "Thanks. I can route that to the office. What is your company name, trade, service area, "
                "license number if applicable, and best phone or email?"
            )
        elif any(word in lower for word in ["meeting", "schedule", "appointment", "consultation"]):
            reply = (
                "Absolutely. What is your name, phone number, project location, project type, "
                "and two preferred consultation windows?"
            )
        elif any(word in lower for word in ["quote", "estimate", "price", "cost", "budget"]):
            reply = (
                "I can help qualify the request before the team reviews it. What type of project is it, "
                "where is it located, what budget range are you considering, and when do you want to start?"
            )
        else:
            reply = (
                "Got it. To route this cleanly, please share your name, phone or email, project location, "
                "scope, budget range, and desired timeline."
            )

        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self) -> None:
        self.history = []


def cleanup_session_agents() -> None:
    cutoff = time.time() - AGENT_TTL_SECONDS
    for session_id in [sid for sid, payload in _session_agents.items() if payload.get("last_seen", 0) < cutoff]:
        _session_agents.pop(session_id, None)


def get_agent_for_session(session_id: str) -> Any:
    with _agent_lock:
        cleanup_session_agents()
        if session_id not in _session_agents:
            if ConstructionAgent is not None:
                try:
                    agent = ConstructionAgent(
                        company_name=COMPANY_PROFILE["company_name"],
                        phone=COMPANY_PROFILE["phone"],
                        email=COMPANY_PROFILE["email"],
                        services=COMPANY_PROFILE["services"],
                        area=COMPANY_PROFILE["area"],
                    )
                except Exception:
                    agent = SmartFallbackAgent()
            else:
                agent = SmartFallbackAgent()
            _session_agents[session_id] = {"agent": agent, "last_seen": time.time()}

        _session_agents[session_id]["last_seen"] = time.time()
        return _session_agents[session_id]["agent"]


def clean_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    blocked = {"sarah", "manager", "office", "company"}
    if value.lower() in blocked:
        return "Unknown"
    return " ".join(part.capitalize() for part in value.split())


def extract_phone(text: str) -> str:
    match = re.search(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}", text)
    return match.group(0).strip() if match else "Unknown"


def extract_email(text: str) -> str:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0).strip() if match else "Unknown"


def extract_budget(text: str) -> str:
    patterns = [
        r"\$\s?\d+[\d,]*(?:\s?(?:-|to)\s?\$?\d+[\d,]*)?",
        r"\d+[\d,]*\s?(?:k|K)\b(?:\s?(?:-|to)\s?\d+[\d,]*\s?(?:k|K)\b)?",
        r"budget\s*(?:is|of|around|about)?\s*[:\-]?\s*([^.\n;]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip().rstrip(",")
    return "Unknown"


def budget_amount(value: str) -> int:
    if value == "Unknown":
        return 0
    lower = value.lower().replace(",", "")
    numbers = re.findall(r"\d+", lower)
    if not numbers:
        return 0
    amount = int(numbers[-1])
    if "k" in lower and amount < 1000:
        amount *= 1000
    return amount


def extract_project_type(text: str) -> str:
    lower = text.lower()
    for project_type, keywords in PROJECT_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return project_type
    return "General Construction"


def extract_project_scope(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for sentence in reversed(sentences):
        lower = sentence.lower()
        if any(keyword in lower for keywords in PROJECT_KEYWORDS.values() for keyword in keywords):
            return sentence.strip()[:240]
    return "Unknown"


def extract_location(text: str) -> str:
    lower = text.lower()
    for city in CITY_HINTS:
        if city in lower:
            return city.title()

    match = re.search(r"(?:in|near|at|located in)\s+([A-Z][A-Za-z .-]{2,44})", text)
    if match:
        location = match.group(1).strip().rstrip(".,")
        location = re.sub(r"\s+(and|with|for)\s+.*$", "", location, flags=re.IGNORECASE)
        return location
    return "Unknown"


def extract_name(text: str) -> str:
    patterns = [
        r"my name is\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        r"i am\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        r"i'm\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        r"this is\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        r"name[:\s]+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_name(match.group(1))
    return "Unknown"


def extract_timeline(text: str) -> str:
    lower = text.lower()
    if any(x in lower for x in ["today", "asap", "immediately", "right away"]):
        return "Immediate"
    if "tomorrow" in lower:
        return "Tomorrow"
    if any(x in lower for x in ["this week", "next week", "within two weeks"]):
        return "Within 1-2 weeks"
    if any(x in lower for x in ["this month", "next month", "30 days"]):
        return "Within 30 days"
    if any(x in lower for x in ["flexible", "no rush", "later this year"]):
        return "Flexible"
    return "Unknown"


def detect_property_type(text: str) -> str:
    lower = text.lower()
    if any(x in lower for x in ["commercial", "office", "retail", "restaurant", "warehouse", "tenant"]):
        return "Commercial"
    if any(x in lower for x in ["home", "house", "condo", "apartment", "residential", "adu"]):
        return "Residential"
    return "Unknown"


def detect_urgency(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in EMERGENCY_WORDS):
        return "Emergency"
    if any(word in lower for word in HIGH_URGENCY_WORDS):
        return "High"
    return "Normal"


def score_lead(profile: LeadProfile, transcript: str) -> Tuple[int, str, str]:
    score = 0
    lower = transcript.lower()

    if profile.full_name != "Unknown":
        score += 8
    if profile.phone != "Unknown" or profile.email != "Unknown":
        score += 12
    if profile.location != "Unknown":
        score += 14
    if profile.project_type != "General Construction":
        score += 16
    if profile.timeline != "Unknown":
        score += 10
    if profile.budget != "Unknown":
        score += 18
    if budget_amount(profile.budget) >= 50000:
        score += 8
    if any(x in lower for x in ["owner", "own", "property manager", "decision maker", "we own"]):
        score += 10
    if any(x in lower for x in ["plans", "drawings", "permit", "engineering", "architect"]):
        score += 8
    if profile.urgency == "High":
        score += 7
    if any(x in lower for x in LOW_INTENT_WORDS):
        score -= 14
    if any(x in lower for x in ["rent", "landlord has not approved", "not approved"]):
        score -= 8

    score = max(0, min(100, score))

    if profile.urgency == "Emergency":
        return 100, "Emergency", "Call now and treat this as an emergency"
    if score >= 85:
        return score, "Hot Lead", "Call this person as soon as possible"
    if score >= 70:
        return score, "Qualified Lead", "Book a call or visit"
    if score >= 45:
        return score, "Needs Review", "Ask for the missing details"
    if score >= 25:
        return score, "Low Priority", "Send a simple follow-up"
    return score, "Not a Fit", "Save it, but no rush"


def missing_fields(profile: LeadProfile) -> str:
    missing = []
    if profile.full_name == "Unknown":
        missing.append("full name")
    if profile.phone == "Unknown" and profile.email == "Unknown":
        missing.append("phone or email")
    if profile.location == "Unknown":
        missing.append("project location")
    if profile.project_type == "General Construction":
        missing.append("project type")
    if profile.budget == "Unknown":
        missing.append("budget range")
    if profile.timeline == "Unknown":
        missing.append("timeline")
    return ", ".join(missing) if missing else "None"


def build_summary(profile: LeadProfile) -> str:
    if profile.full_name != "Unknown":
        subject = f"{profile.full_name} is asking about {profile.project_type.lower()}"
    else:
        subject = f"Prospect is asking about {profile.project_type.lower()}"

    parts = [subject]
    if profile.location != "Unknown":
        parts.append(f"in {profile.location}")
    if profile.budget != "Unknown":
        parts.append(f"with budget signal {profile.budget}")
    if profile.timeline != "Unknown":
        parts.append(f"and timeline {profile.timeline.lower()}")
    return " ".join(parts).strip() + "."


def build_lead_profile(session_id: str) -> LeadProfile:
    user_transcript = transcript_for_session(session_id, sender="user")
    full_transcript = transcript_for_session(session_id)
    existing = get_existing_lead(session_id)

    profile = LeadProfile(
        full_name=extract_name(user_transcript),
        phone=extract_phone(user_transcript),
        email=extract_email(user_transcript),
        project_type=extract_project_type(user_transcript),
        project_scope=extract_project_scope(user_transcript),
        budget=extract_budget(user_transcript),
        location=extract_location(user_transcript),
        property_type=detect_property_type(user_transcript),
        timeline=extract_timeline(user_transcript),
        urgency=detect_urgency(user_transcript),
        notes=full_transcript[-5000:],
    )

    if existing:
        profile.full_name = first_known(profile.full_name, existing["full_name"])
        profile.phone = first_known(profile.phone, existing["phone"])
        profile.email = first_known(profile.email, existing["email"])
        profile.project_type = first_known(profile.project_type, existing["project_type"], "General Construction")
        profile.project_scope = first_known(profile.project_scope, existing["project_scope"])
        profile.budget = first_known(profile.budget, existing["budget"])
        profile.location = first_known(profile.location, existing["location"])
        profile.property_type = first_known(profile.property_type, existing["property_type"])
        profile.timeline = first_known(profile.timeline, existing["timeline"])
        profile.urgency = first_known(profile.urgency, existing["urgency"], "Normal")

    profile.missing_info = missing_fields(profile)
    profile.lead_score, profile.lead_quality, profile.recommended_action = score_lead(profile, user_transcript)
    profile.summary = build_summary(profile)
    return profile


def should_save_or_update_lead(profile: LeadProfile, message_count: int) -> bool:
    has_contact = profile.phone != "Unknown" or profile.email != "Unknown" or profile.full_name != "Unknown"
    has_project_signal = (
        profile.project_type != "General Construction"
        or profile.location != "Unknown"
        or profile.budget != "Unknown"
        or profile.urgency in {"High", "Emergency"}
    )
    return has_contact or has_project_signal or message_count >= 4


def configured(value: str) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    return not (
        lowered.startswith("your_")
        or lowered.startswith("change-me")
        or lowered in {"example", "none", "null", "todo"}
        or lowered == "+1234567890"
    )


def elevenlabs_ready() -> bool:
    return configured(ELEVENLABS_API_KEY) and configured(ELEVENLABS_VOICE_ID)


def twilio_ready() -> bool:
    return all(
        configured(value)
        for value in [TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, MANAGER_PHONE]
    )


def admin_lock_enabled() -> bool:
    return configured(ADMIN_PASSWORD)


def dashboard_unlocked() -> bool:
    return not admin_lock_enabled() or session.get(ADMIN_SESSION_KEY) is True


def require_admin() -> Optional[Response]:
    if dashboard_unlocked():
        return None
    return redirect("/login")


def make_elevenlabs_audio_base64(text: str) -> str:
    if not elevenlabs_ready():
        return ""

    try:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
            json={
                "text": text[:900],
                "model_id": ELEVENLABS_MODEL_ID,
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.8,
                    "style": 0.2,
                    "use_speaker_boost": True,
                },
            },
            timeout=20,
        )
        if response.ok and response.content:
            return base64.b64encode(response.content).decode("utf-8")
    except Exception:
        return ""
    return ""


def make_audio_base64(text: str) -> str:
    if not ENABLE_TTS:
        return ""

    premium_audio = make_elevenlabs_audio_base64(text)
    if premium_audio:
        return premium_audio

    if gTTS is None:
        return ""

    try:
        buffer = io.BytesIO()
        tts = gTTS(text=text[:900], lang="en")
        tts.write_to_fp(buffer)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("utf-8")
    except Exception:
        return ""


def build_sms_body(lead_id: int, profile: LeadProfile) -> str:
    return (
        f"{APP_NAME}: {display_quality(profile.lead_quality)} lead #{lead_id}\n"
        f"Name: {profile.full_name}\n"
        f"Phone: {profile.phone}\n"
        f"Project: {profile.project_type}\n"
        f"Location: {profile.location}\n"
        f"Next: {profile.recommended_action}"
    )[:1500]


def send_manager_sms(body: str) -> bool:
    if not twilio_ready():
        return False

    try:
        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                "From": TWILIO_PHONE_NUMBER,
                "To": MANAGER_PHONE,
                "Body": body,
            },
            timeout=12,
        )
        return response.status_code in {200, 201}
    except Exception:
        return False


def maybe_notify_manager(lead_id: int, profile: LeadProfile) -> bool:
    important = profile.lead_quality in {"Emergency", "Hot Lead"} or profile.urgency in {"Emergency", "High"}
    if not important or lead_was_notified(lead_id):
        return False

    if send_manager_sms(build_sms_body(lead_id, profile)):
        mark_lead_notified(lead_id)
        return True
    return False


LOGIN_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A &amp; I Construction Agent | Login</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh; display: grid; place-items: center; padding: 24px;
      font-family: Inter, "Segoe UI", Arial, sans-serif;
      background:
        radial-gradient(circle at 18% 12%, rgba(245,158,11,.24), transparent 28%),
        linear-gradient(135deg, #111827, #1f2937 55%, #1e3a8a 125%);
      color: #111827;
    }
    .login {
      width: min(430px, 100%); background: #fff; border: 1px solid rgba(255,255,255,.14);
      border-radius: 24px; padding: 28px; box-shadow: 0 30px 90px rgba(0,0,0,.28);
    }
    .brand { font-size: 1.45rem; font-weight: 950; letter-spacing: -.04em; margin-bottom: 8px; }
    .brand span { color: #f59e0b; }
    .brand .amp { color: #f59e0b; font-family: Georgia, "Times New Roman", serif; font-size: 1.18em; font-style: italic; padding: 0 2px; }
    p { color: #64748b; line-height: 1.55; margin-bottom: 20px; }
    label { display: block; color: #64748b; font-size: .78rem; font-weight: 900; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }
    input { width: 100%; border: 2px solid #e5e7eb; border-radius: 14px; padding: 13px 14px; outline: none; font: inherit; }
    input:focus { border-color: #f59e0b; box-shadow: 0 0 0 4px rgba(245,158,11,.13); }
    button { width: 100%; margin-top: 14px; border: 0; border-radius: 14px; padding: 13px 14px; background: #111827; color: #fff; font-weight: 950; cursor: pointer; font: inherit; }
    .error { background: #fee2e2; color: #991b1b; border-radius: 12px; padding: 10px 12px; margin-bottom: 14px; font-weight: 800; }
    a { color: #92400e; text-decoration: none; font-weight: 900; display: inline-block; margin-top: 14px; }
  </style>
</head>
<body>
  <form class="login" method="post" action="/login">
    <div class="brand">A <span class="amp">&amp;</span> I<span> Construction</span> Agent</div>
    <p>Enter the office password to open the dashboard.</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" autofocus>
    <button type="submit">Open Dashboard</button>
    <a href="/">Back to chat</a>
  </form>
</body>
</html>
"""


MAIN_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A &amp; I Construction Agent | Construction Chat</title>
  <style>
    :root {
      --ink: #111827;
      --muted: #64748b;
      --line: #e2e8f0;
      --paper: #ffffff;
      --wash: #f3f6fb;
      --gold: #f59e0b;
      --gold-2: #fbbf24;
      --blue: #2563eb;
      --green: #16a34a;
      --red: #dc2626;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      font-family: Inter, "Segoe UI", Arial, sans-serif;
      background:
        linear-gradient(180deg, #eef2f7 0%, #f8fafc 48%, #eef2f7 100%);
      color: var(--ink);
    }
    button, input, select, textarea { font: inherit; }
    .app { min-height: 100vh; }
    .topbar {
      height: 72px; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 0 40px;
      background: rgba(255,255,255,.94); backdrop-filter: blur(18px); border-bottom: 1px solid rgba(15,23,42,.08);
      box-shadow: 0 14px 35px rgba(15,23,42,.06); position: sticky; top: 0; z-index: 5;
    }
    .brand { font-size: 1.42rem; font-weight: 950; letter-spacing: -.04em; }
    .brand span { color: var(--gold); }
    .brand .amp { color: var(--gold); font-family: Georgia, "Times New Roman", serif; font-size: 1.2em; font-style: italic; padding: 0 2px; }
    .nav { display: flex; align-items: center; gap: 12px; }
    .nav a, .nav button {
      color: var(--muted); text-decoration: none; font-weight: 800; font-size: .88rem; background: transparent;
      border: 0; cursor: pointer;
    }
    .online { background: linear-gradient(135deg, #111827, #1f2937); color: #fff; border-radius: 999px; padding: 9px 15px; font-weight: 900; font-size: .78rem; box-shadow: 0 10px 22px rgba(17,24,39,.18); }
    .hero {
      min-height: 360px; color: #fff; position: relative; overflow: hidden; padding: 58px 40px 86px;
      background:
        radial-gradient(circle at 16% 20%, rgba(251,191,36,.34), transparent 28%),
        radial-gradient(circle at 90% 10%, rgba(37,99,235,.32), transparent 26%),
        linear-gradient(135deg, #111827 0%, #1f2937 48%, #1e3a8a 120%);
    }
    .hero:after {
      content: ""; position: absolute; inset: auto -20% -55% -20%; height: 220px;
      background: rgba(255,255,255,.08); transform: rotate(-2deg);
    }
    .hero-inner { max-width: 1280px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1.1fr) 430px; gap: 36px; align-items: center; position: relative; z-index: 1; }
    .hero-badge {
      display: inline-flex; align-items: center; gap: 8px; color: #fde68a; border: 1px solid rgba(251,191,36,.38);
      background: rgba(251,191,36,.12); padding: 8px 14px; border-radius: 999px; font-size: .74rem; font-weight: 950; letter-spacing: .09em;
    }
    .hero h1 { max-width: 730px; margin: 18px 0 16px; font-size: clamp(2.45rem, 5.3vw, 5rem); line-height: .96; letter-spacing: -.07em; }
    .hero h1 span { color: #fbbf24; }
    .hero p { max-width: 620px; color: #cbd5e1; line-height: 1.72; font-size: 1.04rem; }
    .hero-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; max-width: 620px; margin-top: 28px; }
    .hero-stat { border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.08); border-radius: 18px; padding: 15px; }
    .hero-stat strong { display: block; color: #fde68a; font-size: 1.6rem; letter-spacing: -.05em; }
    .hero-stat small { color: #94a3b8; font-size: .68rem; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }
    .hero-board {
      background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.14); border-radius: 26px; padding: 20px;
      box-shadow: 0 30px 80px rgba(0,0,0,.28);
    }
    .hero-board h2 { font-size: 1rem; margin-bottom: 12px; }
    .board-item { display: grid; grid-template-columns: 42px 1fr; gap: 12px; align-items: center; padding: 13px; border-radius: 16px; background: rgba(255,255,255,.08); margin-top: 10px; }
    .board-icon { width: 42px; height: 42px; border-radius: 14px; display: grid; place-items: center; background: linear-gradient(135deg, #f59e0b, #fbbf24); color: #111827; font-weight: 950; }
    .board-item b { display: block; color: #fff; margin-bottom: 2px; }
    .board-item span { color: #cbd5e1; font-size: .86rem; line-height: 1.4; }
    .shell { max-width: 1280px; width: 100%; margin: -54px auto 38px; padding: 0 24px; display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 22px; position: relative; z-index: 2; }
    .chat-card, .panel {
      background: rgba(255,255,255,.98); border: 1px solid rgba(15,23,42,.08); border-radius: 22px;
      box-shadow: 0 24px 70px rgba(15,23,42,.13); overflow: hidden;
    }
    .chat-card { height: 690px; display: grid; grid-template-rows: auto 1fr auto auto; }
    .chat-head {
      display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 20px;
      background:
        radial-gradient(circle at 14% 0%, rgba(245,158,11,.36), transparent 24%),
        linear-gradient(135deg, #111827 0%, #1f2937 58%, #1e3a8a 130%);
      color: #fff;
    }
    .agent { display: flex; align-items: center; gap: 13px; min-width: 0; }
    .avatar { width: 48px; height: 48px; border-radius: 16px; display: grid; place-items: center; background: linear-gradient(135deg, var(--gold), var(--gold-2)); color: #111827; font-weight: 950; position: relative; flex: 0 0 auto; }
    .dot { position: absolute; right: -2px; bottom: -2px; width: 13px; height: 13px; border-radius: 50%; background: #22c55e; border: 3px solid #111827; }
    .agent h1 { font-size: 1.08rem; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .agent p { color: #cbd5e1; font-size: .78rem; margin-top: 3px; }
    .agent-tags { display: flex; gap: 7px; flex-wrap: wrap; margin-top: 8px; }
    .agent-tags span {
      display: inline-flex; align-items: center; gap: 5px; color: #e5e7eb; border: 1px solid rgba(255,255,255,.14);
      background: rgba(255,255,255,.08); border-radius: 999px; padding: 4px 8px; font-size: .68rem; font-weight: 900;
    }
    .tiny-icon {
      width: 18px; height: 18px; border-radius: 7px; display: inline-grid; place-items: center;
      background: linear-gradient(135deg, var(--gold), var(--gold-2)); color: #111827; font-style: normal;
      font-size: .82rem; font-weight: 950; line-height: 1;
    }
    .head-actions { display: flex; align-items: center; gap: 10px; }
    .premium-chip { border: 1px solid rgba(251,191,36,.35); color: #fde68a; background: rgba(251,191,36,.12); padding: 8px 12px; border-radius: 999px; font-weight: 950; font-size: .76rem; white-space: nowrap; }
    .chat-body { overflow-y: auto; padding: 22px; background: #f8fafc; display: flex; flex-direction: column; gap: 14px; }
    .msg { display: flex; gap: 10px; max-width: 86%; }
    .msg.user { margin-left: auto; flex-direction: row-reverse; }
    .mini { width: 34px; height: 34px; border-radius: 12px; display: grid; place-items: center; flex: 0 0 auto; background: #e2e8f0; color: #334155; font-size: .74rem; font-weight: 950; }
    .assistant .mini { background: #fef3c7; color: #92400e; }
    .bubble { padding: 12px 15px; border-radius: 18px; font-size: .94rem; line-height: 1.56; white-space: pre-wrap; overflow-wrap: anywhere; box-shadow: 0 2px 10px rgba(15,23,42,.04); }
    .assistant .bubble { background: #fff; border: 1px solid #e5e7eb; border-bottom-left-radius: 5px; }
    .user .bubble { color: #fff; background: linear-gradient(135deg, var(--gold), var(--gold-2)); border-bottom-right-radius: 5px; }
    .typing { width: 70px; display: flex; gap: 5px; align-items: center; }
    .typing span { width: 7px; height: 7px; border-radius: 50%; background: var(--gold); animation: bounce 1.1s infinite; }
    .typing span:nth-child(2) { animation-delay: .18s; }
    .typing span:nth-child(3) { animation-delay: .36s; }
    @keyframes bounce { 0%,70%,100%{ transform: translateY(0); opacity: .35; } 35%{ transform: translateY(-6px); opacity: 1; } }
    .quick { padding: 13px 18px; border-top: 1px solid #eef2f7; display: flex; gap: 8px; flex-wrap: wrap; background: #fff; }
    .quick button { border: 1px solid #fed7aa; background: #fff7ed; color: #9a3412; padding: 7px 12px 7px 8px; border-radius: 999px; font-weight: 850; cursor: pointer; transition: .18s ease; display: inline-flex; align-items: center; gap: 7px; }
    .quick button:hover { background: var(--gold); color: #fff; border-color: var(--gold); transform: translateY(-1px); }
    .quick button:hover .btn-icon { background: #fff; color: #92400e; }
    .btn-icon {
      width: 25px; height: 25px; border-radius: 10px; display: inline-grid; place-items: center;
      background: #fed7aa; color: #92400e; font-size: .95rem; font-weight: 950; flex: 0 0 auto; line-height: 1;
    }
    .input-row { padding: 16px 18px; border-top: 1px solid #eef2f7; display: flex; gap: 10px; background: #fff; }
    .input-row input { flex: 1; min-width: 0; border: 2px solid #e5e7eb; border-radius: 999px; padding: 13px 16px; outline: none; }
    .input-row input:focus { border-color: var(--gold); box-shadow: 0 0 0 4px rgba(245,158,11,.12); }
    .send { border: 0; border-radius: 999px; color: #fff; background: linear-gradient(135deg, #111827, #1f2937); cursor: pointer; padding: 0 18px; min-width: 78px; font-weight: 950; box-shadow: 0 10px 20px rgba(17,24,39,.18); }
    .side { display: grid; gap: 18px; align-content: start; }
    .panel { padding: 20px; }
    .panel.accent { border-top: 4px solid var(--gold); }
    .panel h2 { color: var(--muted); font-size: .76rem; text-transform: uppercase; letter-spacing: .09em; margin-bottom: 14px; }
    .score-area { display: grid; grid-template-columns: 96px 1fr; gap: 15px; align-items: center; margin-bottom: 15px; }
    .ring {
      width: 96px; height: 96px; border-radius: 50%; display: grid; place-items: center; position: relative;
      background: conic-gradient(var(--gold) calc(var(--score) * 1%), #e5e7eb 0);
    }
    .ring:after { content: ""; width: 72px; height: 72px; border-radius: 50%; background: #fff; position: absolute; }
    .ring strong { position: relative; z-index: 1; font-size: 1.75rem; letter-spacing: -.06em; }
    .quality { font-weight: 950; font-size: 1.08rem; }
    .action { color: var(--muted); line-height: 1.45; font-size: .87rem; margin-top: 6px; }
    .field { border-top: 1px solid #eef2f7; padding: 11px 0; display: grid; grid-template-columns: 34px 1fr; gap: 10px; align-items: center; }
    .field-icon { width: 34px; height: 34px; border-radius: 12px; display: grid; place-items: center; background: #fef3c7; color: #92400e; font-size: 1rem; font-weight: 950; line-height: 1; }
    .field small { color: var(--muted); font-weight: 900; text-transform: uppercase; letter-spacing: .08em; font-size: .65rem; }
    .field b { font-size: .92rem; overflow-wrap: anywhere; }
    .feature-list { display: grid; gap: 10px; margin-top: 14px; }
    .feature { display: grid; grid-template-columns: 38px 1fr; gap: 10px; align-items: center; padding: 10px; border: 1px solid #eef2f7; border-radius: 14px; background: #f8fafc; }
    .feature-mark { width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; color: #92400e; background: #fef3c7; font-weight: 950; }
    .feature b { font-size: .9rem; display: block; }
    .feature span { color: var(--muted); font-size: .78rem; line-height: 1.35; }
    .manager { display: block; text-align: center; text-decoration: none; background: linear-gradient(135deg, #111827, #1f2937); color: #fff; padding: 14px; border-radius: 16px; font-weight: 950; margin-top: 14px; box-shadow: 0 12px 24px rgba(17,24,39,.18); }
    .muted { color: var(--muted); line-height: 1.5; font-size: .85rem; }
    @media (max-width: 960px) {
      .hero-inner { grid-template-columns: 1fr; }
      .hero { padding: 42px 20px 76px; }
      .hero-board { display: none; }
      .shell { grid-template-columns: 1fr; }
      .chat-card { min-height: 680px; }
      .nav a { display: none; }
    }
    @media (max-width: 560px) {
      .topbar { padding: 0 16px; }
      .hero-stats { grid-template-columns: 1fr; }
      .shell { padding: 14px; }
      .chat-head { align-items: flex-start; }
      .premium-chip { display: none; }
      .msg { max-width: 96%; }
      .quick button { flex: 1 1 auto; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">A <span class="amp">&amp;</span> I<span> Construction</span> Agent</div>
      <nav class="nav">
        <a href="/">Chat</a>
        <a href="/dashboard">Dashboard</a>
        <button type="button" onclick="resetSession()">Reset Chat</button>
        <span class="online">AI Online</span>
      </nav>
    </header>

    <section class="hero">
      <div class="hero-inner">
        <div>
          <div class="hero-badge">SMART CONSTRUCTION ASSISTANT</div>
          <h1>Your project calls handled by <span>Sarah.</span></h1>
          <p>Sarah answers customers, collects project details, plays voice replies, and saves everything for your team in one clean dashboard.</p>
          <div class="hero-stats">
            <div class="hero-stat"><strong>24/7</strong><small>Always ready</small></div>
            <div class="hero-stat"><strong>Voice</strong><small>Speaks back</small></div>
            <div class="hero-stat"><strong>Saved</strong><small>Every lead</small></div>
          </div>
        </div>
        <div class="hero-board">
          <h2>What Sarah does</h2>
          <div class="board-item"><div class="board-icon">1</div><div><b>Answers fast</b><span>Customers can ask about projects, meetings, and urgent problems.</span></div></div>
          <div class="board-item"><div class="board-icon">2</div><div><b>Saves details</b><span>Name, phone, location, budget, timeline, and project type.</span></div></div>
          <div class="board-item"><div class="board-icon">3</div><div><b>Helps the office</b><span>Your dashboard shows who to call and what is still missing.</span></div></div>
        </div>
      </div>
    </section>

    <main class="shell">
      <section class="chat-card">
        <div class="chat-head">
          <div class="agent">
            <div class="avatar">S<span class="dot"></span></div>
            <div>
              <h1>Sarah, Construction Helper</h1>
              <p>Answers questions and saves project details</p>
              <div class="agent-tags">
                <span><i class="tiny-icon">🎙️</i> Voice</span>
                <span><i class="tiny-icon">📋</i> Saves</span>
                <span><i class="tiny-icon">⚡</i> Fast</span>
              </div>
            </div>
          </div>
          <div class="head-actions">
            <span class="premium-chip">Smart Chat</span>
          </div>
        </div>

        <div class="chat-body" id="chatBox">
          <div class="msg assistant">
            <div class="mini">S</div>
            <div class="bubble">Welcome. I am Sarah from {{ company_name }}. I can help with new projects, appointments, urgent problems, existing project questions, supplier messages, and contractor info. How can I help today?</div>
          </div>
        </div>

        <div class="quick">
          <button onclick="quickSend('My name is Alex Carter. I need a quote for a kitchen remodel in Los Angeles. My budget is around $75,000 and I want to start next month. My phone is 310-555-0148.')"><span class="btn-icon">🔨</span>Kitchen remodel</button>
          <button onclick="quickSend('I have an urgent roof leak in Pasadena and need help today. Call me at 626-555-0122.')"><span class="btn-icon">🚨</span>Urgent leak</button>
          <button onclick="quickSend('I want to schedule a consultation for an ADU project in Irvine.')"><span class="btn-icon">🏠</span>Guest house / ADU</button>
          <button onclick="quickSend('I am a subcontractor and want to send my company info.')"><span class="btn-icon">👷</span>Subcontractor</button>
        </div>

        <div class="input-row">
          <input id="userInput" placeholder="Type your message..." autocomplete="off">
          <button class="send" onclick="sendMessage()">Send</button>
        </div>
      </section>

      <aside class="side">
        <section class="panel accent">
          <h2>Project Info</h2>
          <div class="score-area">
            <div class="ring" id="scoreRing" style="--score:0"><strong id="leadScore">0</strong></div>
            <div>
              <div class="quality" id="leadQuality">No details yet</div>
              <p class="action" id="leadAction">Send a message and Sarah will fill this in.</p>
            </div>
          </div>
          <div class="field"><div class="field-icon">🏗️</div><div><small>Project</small><b id="leadProject">Unknown</b></div></div>
          <div class="field"><div class="field-icon">📍</div><div><small>Location</small><b id="leadLocation">Unknown</b></div></div>
          <div class="field"><div class="field-icon">💵</div><div><small>Budget</small><b id="leadBudget">Unknown</b></div></div>
          <div class="field"><div class="field-icon">🚨</div><div><small>Priority</small><b id="leadUrgency">Normal</b></div></div>
          <div class="field"><div class="field-icon">🧾</div><div><small>Still Needed</small><b id="leadMissing">Unknown</b></div></div>
        </section>

        <section class="panel">
          <h2>Office Tools</h2>
          <p class="muted">See saved leads, notes, chat history, and what to do next.</p>
          <div class="feature-list">
            <div class="feature"><div class="feature-mark">☎️</div><div><b>Customer details</b><span>Contact info and project notes.</span></div></div>
            <div class="feature"><div class="feature-mark">🚨</div><div><b>Priority</b><span>See who needs a fast call.</span></div></div>
            <div class="feature"><div class="feature-mark">🧰</div><div><b>Next step</b><span>Know what to ask or do next.</span></div></div>
          </div>
          <a class="manager" href="/dashboard">Open Dashboard</a>
        </section>
      </aside>
    </main>
  </div>

  <script>
    const input = document.getElementById('userInput');
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') sendMessage();
    });

    function addMessage(text, sender) {
      const box = document.getElementById('chatBox');
      const row = document.createElement('div');
      row.className = 'msg ' + sender;

      const avatar = document.createElement('div');
      avatar.className = 'mini';
      avatar.textContent = sender === 'user' ? 'YOU' : 'S';

      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.textContent = text;

      row.appendChild(avatar);
      row.appendChild(bubble);
      box.appendChild(row);
      box.scrollTop = box.scrollHeight;
    }

    function showTyping() {
      const box = document.getElementById('chatBox');
      const row = document.createElement('div');
      row.className = 'msg assistant';
      row.id = 'typingRow';

      const avatar = document.createElement('div');
      avatar.className = 'mini';
      avatar.textContent = 'S';

      const bubble = document.createElement('div');
      bubble.className = 'bubble typing';
      bubble.innerHTML = '<span></span><span></span><span></span>';

      row.appendChild(avatar);
      row.appendChild(bubble);
      box.appendChild(row);
      box.scrollTop = box.scrollHeight;
    }

    function removeTyping() {
      const row = document.getElementById('typingRow');
      if (row) row.remove();
    }

    function quickSend(text) {
      input.value = text;
      sendMessage();
    }

    function setText(id, value) {
      document.getElementById(id).textContent = value || 'Unknown';
    }

    function simpleQuality(value) {
      const labels = {
        'Emergency': 'Emergency',
        'Hot Lead': 'Very interested',
        'Qualified Lead': 'Good match',
        'Needs Review': 'Needs a check',
        'Low Priority': 'Maybe later',
        'Not a Fit': 'Not ready'
      };
      return labels[value] || value || 'Unknown';
    }

    function simplePriority(value) {
      const labels = {
        'Emergency': 'Emergency',
        'High': 'High',
        'Normal': 'Normal'
      };
      return labels[value] || value || 'Normal';
    }

    function updateLeadPreview(profile) {
      if (!profile) return;
      const score = Number(profile.lead_score || 0);
      document.getElementById('scoreRing').style.setProperty('--score', score);
      setText('leadScore', String(score));
      setText('leadQuality', simpleQuality(profile.lead_quality || 'Needs Review'));
      setText('leadAction', profile.recommended_action || 'Needs human review');
      setText('leadProject', profile.project_type);
      setText('leadLocation', profile.location);
      setText('leadBudget', profile.budget);
      setText('leadUrgency', simplePriority(profile.urgency));
      setText('leadMissing', profile.missing_info);
    }

    async function sendMessage() {
      const text = input.value.trim();
      if (!text) return;

      addMessage(text, 'user');
      input.value = '';
      input.focus();
      showTyping();

      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({message: text})
        });

        const data = await response.json();
        removeTyping();
        addMessage(data.response || 'I could not process that request.', 'assistant');
        updateLeadPreview(data.lead_preview);

        if (data.audio) {
          const audio = new Audio('data:audio/mp3;base64,' + data.audio);
          audio.play().catch(() => {});
        }
      } catch (error) {
        removeTyping();
        addMessage('Something went wrong. Please try again.', 'assistant');
      }
    }

    async function resetSession() {
      await fetch('/reset-session', {method: 'POST'});
      window.location.reload();
    }
  </script>
</body>
</html>
"""


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A &amp; I Construction Agent | Dashboard</title>
  <style>
    :root { --ink:#111827; --muted:#64748b; --line:#e2e8f0; --paper:#fff; --wash:#f3f6fb; --gold:#f59e0b; --gold-2:#fbbf24; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: Inter, "Segoe UI", Arial, sans-serif;
      background:
        radial-gradient(circle at 12% 0%, rgba(245,158,11,.14), transparent 28%),
        linear-gradient(180deg, #eef2f7 0%, #f8fafc 48%, #eef2f7 100%);
      color: var(--ink);
    }
    button, input, select, textarea { font: inherit; }
    .top {
      background:
        radial-gradient(circle at 12% 0%, rgba(245,158,11,.32), transparent 24%),
        linear-gradient(135deg, #111827, #1f2937 58%, #1e3a8a 125%);
      color: #fff; padding: 20px 36px; display: flex; align-items: center; justify-content: space-between; gap: 18px;
      box-shadow: 0 18px 45px rgba(15,23,42,.18);
    }
    .brand { font-weight: 950; letter-spacing: -.04em; font-size: 1.24rem; }
    .brand span { color: #fbbf24; }
    .brand .amp { color: #fbbf24; font-family: Georgia, "Times New Roman", serif; font-size: 1.18em; font-style: italic; padding: 0 2px; }
    .top a { color: #cbd5e1; text-decoration: none; font-weight: 800; }
    .wrap { max-width: 1280px; margin: 30px auto; padding: 0 22px; }
    .title { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
    h1 { font-size: 2rem; letter-spacing: -.045em; }
    .title p { color: var(--muted); margin-top: 6px; }
    .export { background: linear-gradient(135deg, var(--gold), var(--gold-2)); color: #111827; text-decoration: none; padding: 11px 14px; border-radius: 13px; font-weight: 950; white-space: nowrap; box-shadow: 0 12px 24px rgba(245,158,11,.24); }
    .stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 18px; }
    .stat { background: var(--paper); padding: 20px; border-radius: 18px; border: 1px solid var(--line); border-top: 4px solid var(--gold); box-shadow: 0 16px 42px rgba(15,23,42,.08); }
    .stat small { color: var(--muted); font-weight: 900; text-transform: uppercase; letter-spacing: .08em; font-size: .68rem; }
    .stat strong { display: block; font-size: 2.1rem; margin-top: 8px; letter-spacing: -.05em; }
    .filters { background: #fff; border: 1px solid var(--line); padding: 14px; border-radius: 18px; display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; box-shadow: 0 12px 34px rgba(15,23,42,.06); }
    .filters input, .filters select { padding: 10px 12px; border-radius: 12px; border: 1px solid #cbd5e1; min-width: 160px; background: #fff; }
    .filters button, .filters a { border: 0; background: #111827; color: #fff; padding: 10px 14px; border-radius: 12px; text-decoration: none; font-weight: 900; cursor: pointer; }
    .filters a { background: #e2e8f0; color: #111827; }
    .table-card { background: #fff; border-radius: 20px; border: 1px solid var(--line); overflow: hidden; box-shadow: 0 18px 52px rgba(15,23,42,.09); }
    table { width: 100%; border-collapse: collapse; }
    th { background: #f8fafc; color: var(--muted); text-align: left; font-size: .7rem; text-transform: uppercase; letter-spacing: .08em; padding: 13px; }
    td { padding: 14px 13px; border-top: 1px solid #f1f5f9; vertical-align: top; font-size: .88rem; }
    tr:hover td { background: #f8fafc; }
    .lead-link { color: var(--ink); font-weight: 950; text-decoration: none; }
    .note { color: var(--muted); font-size: .78rem; line-height: 1.45; max-width: 270px; overflow-wrap: anywhere; }
    .score { font-size: 1.15rem; font-weight: 950; }
    .badge { display: inline-block; padding: 5px 9px; border-radius: 999px; font-size: .72rem; font-weight: 950; white-space: nowrap; }
    .hot { background: #fee2e2; color: #991b1b; }
    .qualified { background: #dcfce7; color: #166534; }
    .review { background: #dbeafe; color: #1e40af; }
    .low { background: #fef3c7; color: #92400e; }
    .emergency { background: #7f1d1d; color: #fff; }
    .normal { background: #e2e8f0; color: #334155; }
    .status-select { border: 1px solid #cbd5e1; border-radius: 10px; padding: 7px 8px; background: #fff; min-width: 130px; }
    .empty { padding: 54px; text-align: center; color: var(--muted); }
    @media (max-width: 1080px) {
      .stats { grid-template-columns: repeat(2, 1fr); }
      table { min-width: 1120px; }
      .table-card { overflow: auto; }
      .title { align-items: start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header class="top">
    <div class="brand">A <span class="amp">&amp;</span> I<span> Construction</span> Agent Dashboard</div>
    <div style="display:flex; gap:14px; align-items:center; flex-wrap:wrap;">
      {% if dashboard_locked %}<a href="/logout">Lock Dashboard</a>{% endif %}
      <a href="/">Back to Chat</a>
    </div>
  </header>

  <main class="wrap">
    <div class="title">
      <div>
        <h1>Dashboard</h1>
        <p>See customers, project details, priority, and what to do next.</p>
      </div>
      <a class="export" href="/export/leads.csv">Download CSV</a>
    </div>

    <section class="stats">
      <div class="stat"><small>Total</small><strong>{{ stats.total }}</strong></div>
      <div class="stat"><small>Important</small><strong>{{ stats.hot }}</strong></div>
      <div class="stat"><small>High Priority</small><strong>{{ stats.urgent }}</strong></div>
      <div class="stat"><small>Meetings</small><strong>{{ stats.scheduled }}</strong></div>
      <div class="stat"><small>Today</small><strong>{{ stats.today }}</strong></div>
    </section>

    <form class="filters" method="get" action="/dashboard">
      <input name="search" value="{{ search }}" placeholder="Search leads...">
      <select name="quality">
        {% for q in ['all', 'Emergency', 'Hot Lead', 'Qualified Lead', 'Needs Review', 'Low Priority', 'Not a Fit'] %}
          <option value="{{ q }}" {% if quality == q %}selected{% endif %}>{{ display_quality(q) }}</option>
        {% endfor %}
      </select>
      <select name="urgency">
        {% for u in ['all', 'Emergency', 'High', 'Normal'] %}
          <option value="{{ u }}" {% if urgency == u %}selected{% endif %}>{{ display_priority(u) }}</option>
        {% endfor %}
      </select>
      <select name="status">
        {% for s in ['all', 'New', 'Contacted', 'Scheduled', 'Proposal Sent', 'Won', 'Lost'] %}
          <option value="{{ s }}" {% if status == s %}selected{% endif %}>{{ s }}</option>
        {% endfor %}
      </select>
      <button type="submit">Search</button>
      <a href="/dashboard">Reset</a>
    </form>

    <section class="table-card">
      {% if leads %}
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Customer</th>
            <th>Project</th>
            <th>Location</th>
            <th>Budget</th>
            <th>Timeline</th>
            <th>Rating</th>
            <th>Interest</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Next Step</th>
            <th>Still Needed</th>
          </tr>
        </thead>
        <tbody>
          {% for lead in leads %}
          <tr>
            <td>#{{ lead.id }}</td>
            <td>
              <a class="lead-link" href="/lead/{{ lead.id }}">{{ lead.full_name }}</a><br>
              <span class="note">{{ lead.phone }}<br>{{ lead.email }}</span>
            </td>
            <td>{{ lead.project_type }}<br><span class="note">{{ lead.property_type }}</span></td>
            <td>{{ lead.location }}</td>
            <td>{{ lead.budget }}</td>
            <td>{{ lead.timeline }}</td>
            <td><span class="score">{{ lead.lead_score }}</span></td>
            <td><span class="badge {{ quality_class(lead.lead_quality) }}">{{ display_quality(lead.lead_quality) }}</span></td>
            <td><span class="badge {{ urgency_class(lead.urgency) }}">{{ lead.urgency }}</span></td>
            <td>
              <select class="status-select" onchange="updateStatus({{ lead.id }}, this.value)">
                {% for s in ['New', 'Contacted', 'Scheduled', 'Proposal Sent', 'Won', 'Lost'] %}
                  <option value="{{ s }}" {% if lead.status == s %}selected{% endif %}>{{ s }}</option>
                {% endfor %}
              </select>
            </td>
            <td><span class="note">{{ lead.recommended_action }}</span></td>
            <td><span class="note">{{ lead.missing_info }}</span></td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% else %}
      <div class="empty">
        <h2>No saved leads found</h2>
        <p>Start a conversation on the front desk page.</p>
      </div>
      {% endif %}
    </section>
  </main>

  <script>
    async function updateStatus(id, status) {
      const response = await fetch('/api/leads/' + id + '/status', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status})
      });
      if (!response.ok) alert('Could not update status.');
    }
  </script>
</body>
</html>
"""


LEAD_DETAIL_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A &amp; I Construction Agent | Customer Info</title>
  <style>
    :root { --ink:#111827; --muted:#64748b; --line:#e2e8f0; --wash:#f3f6fb; --gold:#f59e0b; --gold-2:#fbbf24; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: Inter, "Segoe UI", Arial, sans-serif;
      background:
        radial-gradient(circle at 10% 0%, rgba(245,158,11,.16), transparent 28%),
        linear-gradient(180deg, #eef2f7 0%, #f8fafc 50%, #eef2f7 100%);
      color: var(--ink);
    }
    button, textarea, select { font: inherit; }
    .top {
      background:
        radial-gradient(circle at 12% 0%, rgba(245,158,11,.32), transparent 24%),
        linear-gradient(135deg, #111827, #1f2937 58%, #1e3a8a 125%);
      color: #fff; padding: 20px 36px; display: flex; align-items: center; justify-content: space-between; gap: 18px;
      box-shadow: 0 18px 45px rgba(15,23,42,.18);
    }
    .brand { font-weight: 950; letter-spacing: -.04em; font-size: 1.24rem; }
    .brand span { color: #fbbf24; }
    .brand .amp { color: #fbbf24; font-family: Georgia, "Times New Roman", serif; font-size: 1.18em; font-style: italic; padding: 0 2px; }
    .top a { color: #cbd5e1; text-decoration: none; font-weight: 800; }
    .wrap { max-width: 1180px; margin: 26px auto; padding: 0 22px; display: grid; grid-template-columns: 390px 1fr; gap: 20px; align-items: start; }
    .card { background: #fff; border: 1px solid var(--line); border-radius: 22px; box-shadow: 0 18px 52px rgba(15,23,42,.09); overflow: hidden; }
    .card-head { padding: 20px; border-bottom: 1px solid #eef2f7; display: flex; justify-content: space-between; gap: 16px; align-items: start; }
    h1 { font-size: 1.45rem; letter-spacing: -.04em; }
    .muted { color: var(--muted); line-height: 1.5; font-size: .86rem; }
    .badge { display: inline-block; padding: 6px 10px; border-radius: 999px; font-size: .74rem; font-weight: 950; white-space: nowrap; }
    .hot { background: #fee2e2; color: #991b1b; }
    .qualified { background: #dcfce7; color: #166534; }
    .review { background: #dbeafe; color: #1e40af; }
    .low { background: #fef3c7; color: #92400e; }
    .emergency { background: #7f1d1d; color: #fff; }
    .normal { background: #e2e8f0; color: #334155; }
    .fields { padding: 8px 20px 20px; }
    .field { border-bottom: 1px solid #eef2f7; padding: 12px 0; }
    .field:last-child { border-bottom: 0; }
    .field small { color: var(--muted); display: block; text-transform: uppercase; letter-spacing: .08em; font-size: .66rem; font-weight: 900; margin-bottom: 5px; }
    .field b, .field p { overflow-wrap: anywhere; }
    .score { font-size: 2.5rem; font-weight: 950; letter-spacing: -.06em; }
    .actions { padding: 20px; border-top: 1px solid #eef2f7; display: grid; gap: 12px; }
    select, textarea { width: 100%; border: 1px solid #cbd5e1; border-radius: 13px; padding: 11px 12px; background: #fff; }
    textarea { min-height: 120px; resize: vertical; }
    button { border: 0; border-radius: 13px; padding: 12px 14px; background: linear-gradient(135deg, #111827, #1f2937); color: #fff; font-weight: 950; cursor: pointer; box-shadow: 0 12px 24px rgba(17,24,39,.16); }
    .thread { padding: 18px; display: grid; gap: 12px; max-height: 720px; overflow: auto; background: #f8fafc; }
    .msg { max-width: 82%; padding: 12px 14px; border-radius: 18px; background: #fff; border: 1px solid #e5e7eb; line-height: 1.55; font-size: .92rem; white-space: pre-wrap; overflow-wrap: anywhere; }
    .msg.user { margin-left: auto; background: linear-gradient(135deg,#f59e0b,#fbbf24); color: #fff; border: 0; }
    .msg small { display: block; opacity: .7; margin-top: 7px; font-size: .72rem; }
    .handoff { white-space: pre-wrap; background: linear-gradient(135deg, #111827, #1f2937); color: #dbeafe; padding: 16px; border-radius: 16px; line-height: 1.55; font-size: .88rem; border-top: 4px solid var(--gold); }
    @media (max-width: 920px) { .wrap { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header class="top">
    <div class="brand">A <span class="amp">&amp;</span> I<span> Construction</span> Agent Customer Info</div>
    <div style="display:flex; gap:14px; align-items:center; flex-wrap:wrap;">
      {% if dashboard_locked %}<a href="/logout">Lock Dashboard</a>{% endif %}
      <a href="/dashboard">Back to Dashboard</a>
    </div>
  </header>

  <main class="wrap">
    <aside class="card">
      <div class="card-head">
        <div>
          <h1>{{ lead.full_name }}</h1>
          <p class="muted">#{{ lead.id }} | Updated {{ lead.updated_at }}</p>
        </div>
        <span class="badge {{ quality_class(lead.lead_quality) }}">{{ display_quality(lead.lead_quality) }}</span>
      </div>
      <div class="fields">
        <div class="field"><small>Rating</small><div class="score">{{ lead.lead_score }}</div></div>
        <div class="field"><small>Next Step</small><p>{{ lead.recommended_action }}</p></div>
        <div class="field"><small>Contact</small><b>{{ lead.phone }}</b><p class="muted">{{ lead.email }}</p></div>
        <div class="field"><small>Project</small><b>{{ lead.project_type }}</b><p class="muted">{{ lead.project_scope }}</p></div>
        <div class="field"><small>Location</small><b>{{ lead.location }}</b></div>
        <div class="field"><small>Budget</small><b>{{ lead.budget }}</b></div>
        <div class="field"><small>Timeline</small><b>{{ lead.timeline }}</b></div>
        <div class="field"><small>Priority</small><span class="badge {{ urgency_class(lead.urgency) }}">{{ lead.urgency }}</span></div>
        <div class="field"><small>Still Needed</small><p>{{ lead.missing_info }}</p></div>
        <div class="field"><small>Summary</small><p>{{ lead.summary }}</p></div>
      </div>
      <div class="actions">
        <select id="status">
          {% for s in ['New', 'Contacted', 'Scheduled', 'Proposal Sent', 'Won', 'Lost'] %}
            <option value="{{ s }}" {% if lead.status == s %}selected{% endif %}>{{ s }}</option>
          {% endfor %}
        </select>
        <textarea id="managerNotes" placeholder="Manager notes...">{{ lead.manager_notes }}</textarea>
        <button onclick="saveLead()">Save Changes</button>
      </div>
    </aside>

    <section class="card">
      <div class="card-head">
        <div>
          <h1>Chat and Summary</h1>
          <p class="muted">Use this when you call or message the customer.</p>
        </div>
        <button onclick="copyHandoff()">Copy Summary</button>
      </div>
      <div class="thread">
        <div class="handoff" id="handoffText">Customer: {{ lead.full_name }}
Phone: {{ lead.phone }}
Email: {{ lead.email }}
Project: {{ lead.project_type }}
Location: {{ lead.location }}
Budget: {{ lead.budget }}
Timeline: {{ lead.timeline }}
Priority: {{ lead.urgency }}
Rating: {{ lead.lead_score }} / 100
Interest: {{ display_quality(lead.lead_quality) }}
Still Needed: {{ lead.missing_info }}
Next Step: {{ lead.recommended_action }}
Summary: {{ lead.summary }}</div>
        {% for row in conversation %}
          <div class="msg {{ row.sender }}">
            {{ row.message }}
            <small>{{ row.sender }} | {{ row.created_at }}</small>
          </div>
        {% endfor %}
      </div>
    </section>
  </main>

  <script>
    async function saveLead() {
      const status = document.getElementById('status').value;
      const manager_notes = document.getElementById('managerNotes').value;

      const statusResponse = await fetch('/api/leads/{{ lead.id }}/status', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status})
      });
      const notesResponse = await fetch('/api/leads/{{ lead.id }}/manager-notes', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({manager_notes})
      });

      if (statusResponse.ok && notesResponse.ok) {
        window.location.reload();
      } else {
        alert('Could not save lead updates.');
      }
    }

    async function copyHandoff() {
      const text = document.getElementById('handoffText').textContent;
      await navigator.clipboard.writeText(text);
    }
  </script>
</body>
</html>
"""


def quality_class(value: str) -> str:
    mapping = {
        "Emergency": "emergency",
        "Hot Lead": "hot",
        "Qualified Lead": "qualified",
        "Needs Review": "review",
        "Low Priority": "low",
        "Not a Fit": "normal",
    }
    return mapping.get(value, "normal")


def urgency_class(value: str) -> str:
    if value == "Emergency":
        return "emergency"
    if value == "High":
        return "hot"
    return "normal"


def display_quality(value: str) -> str:
    mapping = {
        "all": "All interests",
        "Emergency": "Emergency",
        "Hot Lead": "Very interested",
        "Qualified Lead": "Good match",
        "Needs Review": "Needs a check",
        "Low Priority": "Maybe later",
        "Not a Fit": "Not ready",
    }
    return mapping.get(value, value)


def display_priority(value: str) -> str:
    mapping = {
        "all": "All priorities",
        "Emergency": "Emergency",
        "High": "High",
        "Normal": "Normal",
    }
    return mapping.get(value, value)


@app.context_processor
def template_helpers() -> Dict[str, Any]:
    return {
        "quality_class": quality_class,
        "urgency_class": urgency_class,
        "display_quality": display_quality,
        "display_priority": display_priority,
    }


@app.route("/login", methods=["GET", "POST"])
def login() -> Response | str:
    if not admin_lock_enabled():
        return redirect("/dashboard")

    error = ""
    if request.method == "POST":
        password = str(request.form.get("password", ""))
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            session[ADMIN_SESSION_KEY] = True
            return redirect("/dashboard")
        error = "Wrong password."

    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout")
def logout() -> Response:
    session.pop(ADMIN_SESSION_KEY, None)
    return redirect("/")


@app.route("/")
def index() -> str:
    get_session_id()
    return render_template_string(MAIN_HTML, company_name=COMPANY_PROFILE["company_name"])


@app.route("/chat", methods=["POST"])
def chat() -> Tuple[Response, int] | Response:
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    user_message = str(data.get("message", "")).strip()

    if not user_message:
        return jsonify({"response": "Please type a message so I can help.", "audio": "", "lead_id": None}), 400

    log_message(session_id, "user", user_message)
    agent = get_agent_for_session(session_id)

    try:
        response = str(agent.process_message(user_message)).strip()
    except Exception:
        response = (
            "I can still help collect the details. Are you contacting us about a new project, "
            "an existing project, an urgent issue, scheduling, or subcontractor information?"
        )

    if not response:
        response = "I can help route this. Is this for a new project, an existing project, or an urgent issue?"

    log_message(session_id, "assistant", response)

    conversation_count = len(get_conversation(session_id, limit=160))
    lead_profile = build_lead_profile(session_id)
    lead_id: Optional[int] = None

    if should_save_or_update_lead(lead_profile, conversation_count):
        lead_id = upsert_lead(session_id, lead_profile)
        maybe_notify_manager(lead_id, lead_profile)

    return jsonify(
        {
            "response": response,
            "audio": make_audio_base64(response),
            "lead_id": lead_id,
            "lead_preview": asdict(lead_profile),
        }
    )


@app.route("/dashboard")
def dashboard() -> Response | str:
    admin_redirect = require_admin()
    if admin_redirect is not None:
        return admin_redirect

    status = request.args.get("status", "all")
    quality = request.args.get("quality", "all")
    urgency = request.args.get("urgency", "all")
    search = request.args.get("search", "").strip()
    leads = fetch_leads(status=status, quality=quality, urgency=urgency, search=search)

    return render_template_string(
        DASHBOARD_HTML,
        leads=leads,
        stats=dashboard_stats(),
        status=status,
        quality=quality,
        urgency=urgency,
        search=search,
        dashboard_locked=admin_lock_enabled(),
    )


@app.route("/lead/<int:lead_id>")
def lead_detail(lead_id: int) -> Response | Tuple[str, int] | str:
    admin_redirect = require_admin()
    if admin_redirect is not None:
        return admin_redirect

    lead = fetch_lead_by_id(lead_id)
    if not lead:
        return "Lead not found", 404
    conversation = get_conversation(lead["session_id"], limit=200)
    return render_template_string(
        LEAD_DETAIL_HTML,
        lead=lead,
        conversation=conversation,
        dashboard_locked=admin_lock_enabled(),
    )


@app.route("/api/leads")
def api_leads() -> Response:
    admin_redirect = require_admin()
    if admin_redirect is not None:
        return jsonify({"error": "Login required"}), 401

    leads = fetch_leads()
    return jsonify([dict(row) for row in leads])


@app.route("/api/leads/<int:lead_id>")
def api_lead_detail(lead_id: int) -> Tuple[Response, int] | Response:
    admin_redirect = require_admin()
    if admin_redirect is not None:
        return jsonify({"error": "Login required"}), 401

    lead = fetch_lead_by_id(lead_id)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
    conversation = [dict(row) for row in get_conversation(lead["session_id"], limit=200)]
    return jsonify({"lead": dict(lead), "conversation": conversation})


@app.route("/api/leads/<int:lead_id>/status", methods=["POST"])
def api_update_status(lead_id: int) -> Tuple[Response, int] | Response:
    admin_redirect = require_admin()
    if admin_redirect is not None:
        return jsonify({"success": False, "error": "Login required"}), 401

    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()
    if not update_lead_status(lead_id, status):
        return jsonify({"success": False, "error": "Invalid lead or status"}), 400
    return jsonify({"success": True})


@app.route("/api/leads/<int:lead_id>/manager-notes", methods=["POST"])
def api_update_manager_notes(lead_id: int) -> Tuple[Response, int] | Response:
    admin_redirect = require_admin()
    if admin_redirect is not None:
        return jsonify({"success": False, "error": "Login required"}), 401

    data = request.get_json(silent=True) or {}
    notes = str(data.get("manager_notes", "")).strip()
    if not update_manager_notes(lead_id, notes):
        return jsonify({"success": False, "error": "Lead not found"}), 404
    return jsonify({"success": True})


@app.route("/export/leads.csv")
def export_leads_csv() -> Response:
    admin_redirect = require_admin()
    if admin_redirect is not None:
        return admin_redirect

    leads = fetch_leads()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "status",
            "lead_quality",
            "lead_score",
            "urgency",
            "full_name",
            "phone",
            "email",
            "project_type",
            "budget",
            "location",
            "timeline",
            "missing_info",
            "recommended_action",
            "summary",
            "created_at",
            "updated_at",
        ]
    )
    for lead in leads:
        writer.writerow(
            [
                lead["id"],
                lead["status"],
                lead["lead_quality"],
                lead["lead_score"],
                lead["urgency"],
                lead["full_name"],
                lead["phone"],
                lead["email"],
                lead["project_type"],
                lead["budget"],
                lead["location"],
                lead["timeline"],
                lead["missing_info"],
                lead["recommended_action"],
                lead["summary"],
                lead["created_at"],
                lead["updated_at"],
            ]
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=buildai-leads.csv"},
    )


@app.route("/save-lead", methods=["POST"])
def save_lead_route() -> Response:
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    profile = LeadProfile(
        full_name=str(data.get("name") or data.get("full_name") or "Unknown"),
        phone=str(data.get("phone") or "Unknown"),
        email=str(data.get("email") or "Unknown"),
        project_type=str(data.get("project_type") or "General Construction"),
        budget=str(data.get("budget") or "Unknown"),
        location=str(data.get("location") or "Unknown"),
        notes=str(data.get("notes") or ""),
    )
    profile.missing_info = missing_fields(profile)
    profile.lead_score, profile.lead_quality, profile.recommended_action = score_lead(profile, profile.notes)
    profile.summary = build_summary(profile)
    lead_id = upsert_lead(session_id, profile)
    maybe_notify_manager(lead_id, profile)
    return jsonify({"success": True, "lead_id": lead_id, "lead": asdict(profile)})


@app.route("/reset-session", methods=["POST"])
def reset_session() -> Response:
    session_id = get_session_id()
    with _agent_lock:
        _session_agents.pop(session_id, None)
    session.pop("session_id", None)
    return jsonify({"success": True})


@app.route("/health")
def health() -> Response:
    return jsonify(
        {
            "status": "ok",
            "app": APP_NAME,
            "tts_enabled": ENABLE_TTS,
            "voice_provider": "elevenlabs" if elevenlabs_ready() else "gtts",
            "sms_ready": twilio_ready(),
            "dashboard_locked": admin_lock_enabled(),
            "agent_available": ConstructionAgent is not None,
            "database": DATABASE_PATH,
        }
    )


@app.route("/api/readiness")
def api_readiness() -> Response:
    return jsonify(
        {
            "app": APP_NAME,
            "agent": ConstructionAgent is not None,
            "voice": {
                "enabled": ENABLE_TTS,
                "provider": "elevenlabs" if elevenlabs_ready() else "gtts",
                "elevenlabs_ready": elevenlabs_ready(),
            },
            "sms_notifications": twilio_ready(),
            "dashboard_locked": admin_lock_enabled(),
            "production_mode": APP_ENV == "production",
            "custom_secret_key": configured(str(app.secret_key)),
        }
    )


init_db()
migrate_legacy_leads()


if __name__ == "__main__":
    debug = APP_ENV != "production"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=debug)
