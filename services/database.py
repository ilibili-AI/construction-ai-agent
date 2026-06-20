"""
services/database.py
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import create_client, Client

logger = logging.getLogger(__name__)

_client = None

def _get_client():
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        _client = create_client(url, key)
    return _client


def _retry(fn, attempts=3, delay=0.5):
    last_exc = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            logger.warning("[DB] Attempt %d failed: %s", i + 1, exc)
            if i < attempts - 1:
                time.sleep(delay * (i + 1))
    raise last_exc


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Row(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


def _wrap(data):
    if data is None:
        return None
    if isinstance(data, list):
        return [_Row(r) for r in data]
    return _Row(data)


def init_db():
    try:
        client = _get_client()
        client.table("leads").select("id").limit(1).execute()
        logger.info("[DB] Supabase connection OK")
    except Exception as exc:
        logger.warning("[DB] Supabase connectivity check failed: %s", exc)


def log_message(session_id, sender, message):
    def _do():
        _get_client().table("conversations").insert({
            "session_id": session_id,
            "sender": sender,
            "message": message,
            "created_at": now_iso(),
        }).execute()
    _retry(_do)


def get_conversation(session_id, limit=80):
    def _do():
        res = (
            _get_client()
            .table("conversations")
            .select("sender, message, created_at")
            .eq("session_id", session_id)
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        rows = list(reversed(res.data or []))
        return _wrap(rows)
    return _retry(_do)


def transcript_for_session(session_id, sender=None):
    rows = get_conversation(session_id, limit=160)
    if sender:
        rows = [r for r in rows if r["sender"] == sender]
    return "\n".join(str(r["message"]) for r in rows)


def get_existing_lead(session_id):
    def _do():
        res = (
            _get_client()
            .table("leads")
            .select("*")
            .eq("session_id", session_id)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        data = res.data
        return _wrap(data[0]) if data else None
    return _retry(_do)


def upsert_lead(session_id, payload):
    def _do():
        client = _get_client()
        existing = (
            client.table("leads")
            .select("id")
            .eq("session_id", session_id)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        row = {
            "full_name":          payload.get("full_name", "Unknown"),
            "phone":              payload.get("phone", "Unknown"),
            "email":              payload.get("email", "Unknown"),
            "project_type":       payload.get("project_type", "General Construction"),
            "project_scope":      payload.get("project_scope", "Unknown"),
            "budget":             payload.get("budget", "Unknown"),
            "location":           payload.get("location", "Unknown"),
            "property_type":      payload.get("property_type", "Unknown"),
            "timeline":           payload.get("timeline", "Unknown"),
            "urgency":            payload.get("urgency", "Normal"),
            "lead_score":         payload.get("lead_score", 0),
            "lead_quality":       payload.get("lead_quality", "Needs Review"),
            "missing_info":       payload.get("missing_info", ""),
            "recommended_action": payload.get("recommended_action", "Needs human review"),
            "summary":            payload.get("summary", ""),
            "notes":              payload.get("notes", ""),
            "updated_at":         now_iso(),
        }
        if existing.data:
            lead_id = existing.data[0]["id"]
            client.table("leads").update(row).eq("id", lead_id).execute()
            return lead_id
        else:
            row["session_id"] = session_id
            row["created_at"] = now_iso()
            res = client.table("leads").insert(row).execute()
            return res.data[0]["id"]
    return _retry(_do)


def fetch_leads(status="all", quality="all", urgency="all", search=""):
    def _do():
        q = _get_client().table("leads").select("*")
        if status != "all":
            q = q.eq("status", status)
        if quality != "all":
            q = q.eq("lead_quality", quality)
        if urgency != "all":
            q = q.eq("urgency", urgency)
        if search:
            q = q.or_(
                f"full_name.ilike.%{search}%,"
                f"phone.ilike.%{search}%,"
                f"project_type.ilike.%{search}%,"
                f"location.ilike.%{search}%"
            )
        res = q.order("lead_score", desc=True).limit(300).execute()
        return _wrap(res.data or [])
    return _retry(_do)


def fetch_lead_by_id(lead_id):
    def _do():
        res = (
            _get_client()
            .table("leads")
            .select("*")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        data = res.data
        return _wrap(data[0]) if data else None
    return _retry(_do)


def update_lead_status(lead_id, status):
    allowed = {"New", "Contacted", "Scheduled", "Proposal Sent", "Won", "Lost"}
    if status not in allowed:
        return False
    def _do():
        res = (
            _get_client()
            .table("leads")
            .update({"status": status, "updated_at": now_iso()})
            .eq("id", lead_id)
            .execute()
        )
        return bool(res.data)
    return _retry(_do)


def update_manager_notes(lead_id, notes):
    def _do():
        res = (
            _get_client()
            .table("leads")
            .update({"manager_notes": notes[:3000], "updated_at": now_iso()})
            .eq("id", lead_id)
            .execute()
        )
        return bool(res.data)
    return _retry(_do)


def mark_lead_notified(lead_id):
    def _do():
        _get_client().table("leads").update({
            "notified_at": now_iso(),
            "updated_at":  now_iso(),
        }).eq("id", lead_id).execute()
    _retry(_do)


def lead_was_notified(lead_id):
    def _do():
        res = (
            _get_client()
            .table("leads")
            .select("notified_at")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        data = res.data
        return bool(data and data[0].get("notified_at"))
    return _retry(_do)


def dashboard_stats():
    def _do():
        client = _get_client()
        today = datetime.now(timezone.utc).date().isoformat()
        total     = client.table("leads").select("id", count="exact").execute().count or 0
        hot       = client.table("leads").select("id", count="exact").in_("lead_quality", ["Hot Lead", "Emergency"]).execute().count or 0
        urgent    = client.table("leads").select("id", count="exact").in_("urgency", ["High", "Emergency"]).execute().count or 0
        scheduled = client.table("leads").select("id", count="exact").eq("status", "Scheduled").execute().count or 0
        today_count = client.table("leads").select("id", count="exact").gte("created_at", today).execute().count or 0

        score_res = client.table("leads").select("lead_score").execute()
        scores = [row.get("lead_score", 0) for row in (score_res.data or [])]
        avg_score = round(sum(scores) / len(scores)) if scores else 0

        convo_res = client.table("conversations").select("session_id").execute()
        sessions = set(row.get("session_id") for row in (convo_res.data or []) if row.get("session_id"))
        calls = len(sessions)

        return {
            "total": total,
            "hot": hot,
            "urgent": urgent,
            "scheduled": scheduled,
            "today": today_count,
            "avg_score": avg_score,
            "calls": calls,
        }
    return _retry(_do)