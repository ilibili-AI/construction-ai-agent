import csv
import io
from flask import Blueprint, request, jsonify, render_template, Response

from services.database import (
    fetch_leads, fetch_lead_by_id, update_lead_status,
    update_manager_notes, get_conversation, dashboard_stats
)

dashboard_bp = Blueprint("dashboard", __name__)


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


@dashboard_bp.context_processor
def template_helpers():
    return {
        "quality_class": quality_class,
        "urgency_class": urgency_class,
        "display_quality": display_quality,
        "display_priority": display_priority,
    }


@dashboard_bp.route("/dashboard")
def dashboard():
    status = request.args.get("status", "all")
    quality = request.args.get("quality", "all")
    urgency = request.args.get("urgency", "all")
    search = request.args.get("search", "").strip()
    leads = fetch_leads(status=status, quality=quality, urgency=urgency, search=search)
    stats = dashboard_stats()

    try:
        return render_template(
            "dashboard.html",
            leads=leads,
            stats=stats,
            status=status,
            quality=quality,
            urgency=urgency,
            search=search,
        )
    except Exception:
        return _dashboard_fallback(leads, stats, status, quality, urgency, search)


def _dashboard_fallback(leads, stats, status, quality, urgency, search):
    rows = ""
    for lead in leads:
        rows += f"""
        <tr>
            <td>#{lead['id']}</td>
            <td><a href="/lead/{lead['id']}">{lead['full_name']}</a><br>
            <small>{lead['phone']}</small></td>
            <td>{lead['project_type']}</td>
            <td>{lead['location']}</td>
            <td>{lead['budget']}</td>
            <td>{lead['lead_score']}</td>
            <td>{lead['lead_quality']}</td>
            <td>{lead['urgency']}</td>
            <td>{lead['status']}</td>
            <td>{lead['recommended_action']}</td>
        </tr>
        """

    return f"""
    <!doctype html><html><head><title>Dashboard</title>
    <style>
        body {{ font-family: sans-serif; padding: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; font-size: 0.85rem; }}
        th {{ background: #f5f5f5; }}
        a {{ color: #f59e0b; }}
        .stats {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .stat {{ background: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 10px; }}
        .stat strong {{ font-size: 2rem; display: block; color: #f59e0b; }}
    </style>
    </head><body>
    <h1>BuildAI Dashboard</h1>
    <a href="/">Back to Chat</a>
    <div class="stats">
        <div class="stat"><small>Total</small><strong>{stats['total']}</strong></div>
        <div class="stat"><small>Hot</small><strong>{stats['hot']}</strong></div>
        <div class="stat"><small>Urgent</small><strong>{stats['urgent']}</strong></div>
        <div class="stat"><small>Today</small><strong>{stats['today']}</strong></div>
    </div>
    <table>
        <thead><tr>
            <th>#</th><th>Customer</th><th>Project</th><th>Location</th>
            <th>Budget</th><th>Score</th><th>Quality</th>
            <th>Priority</th><th>Status</th><th>Next Step</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>
    </body></html>
    """


@dashboard_bp.route("/lead/<int:lead_id>")
def lead_detail(lead_id: int):
    lead = fetch_lead_by_id(lead_id)
    if not lead:
        return "Lead not found", 404
    conversation = get_conversation(lead["session_id"], limit=200)
    try:
        return render_template("lead_detail.html", lead=lead, conversation=conversation)
    except Exception:
        return _lead_detail_fallback(lead, conversation)


def _lead_detail_fallback(lead, conversation):
    messages = ""
    for row in conversation:
        css = "user" if row["sender"] == "user" else "assistant"
        messages += f'<div class="msg {css}"><b>{row["sender"]}</b>: {row["message"]}<br><small>{row["created_at"]}</small></div>'

    return f"""
    <!doctype html><html><head><title>Lead #{lead['id']}</title>
    <style>
        body {{ font-family: sans-serif; padding: 20px; max-width: 900px; margin: 0 auto; }}
        .msg {{ padding: 10px; margin: 8px 0; border-radius: 8px; }}
        .user {{ background: #fef3c7; }}
        .assistant {{ background: #f0fdf4; }}
        .field {{ border-bottom: 1px solid #eee; padding: 8px 0; }}
        small {{ color: #888; }}
    </style>
    </head><body>
    <a href="/dashboard">← Dashboard</a>
    <h1>{lead['full_name']} — #{lead['id']}</h1>
    <div class="field"><small>Phone</small><br><b>{lead['phone']}</b></div>
    <div class="field"><small>Project</small><br><b>{lead['project_type']}</b></div>
    <div class="field"><small>Location</small><br><b>{lead['location']}</b></div>
    <div class="field"><small>Budget</small><br><b>{lead['budget']}</b></div>
    <div class="field"><small>Score</small><br><b>{lead['lead_score']} — {lead['lead_quality']}</b></div>
    <div class="field"><small>Next Step</small><br><b>{lead['recommended_action']}</b></div>
    <h2>Conversation</h2>
    {messages}
    </body></html>
    """


@dashboard_bp.route("/api/leads")
def api_leads():
    leads = fetch_leads()
    return jsonify([dict(row) for row in leads])


@dashboard_bp.route("/api/leads/<int:lead_id>")
def api_lead_detail(lead_id: int):
    lead = fetch_lead_by_id(lead_id)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
    conversation = [dict(row) for row in get_conversation(lead["session_id"], limit=200)]
    return jsonify({"lead": dict(lead), "conversation": conversation})


@dashboard_bp.route("/api/leads/<int:lead_id>/status", methods=["POST"])
def api_update_status(lead_id: int):
    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()
    if not update_lead_status(lead_id, status):
        return jsonify({"success": False, "error": "Invalid lead or status"}), 400
    return jsonify({"success": True})


@dashboard_bp.route("/api/leads/<int:lead_id>/manager-notes", methods=["POST"])
def api_update_manager_notes(lead_id: int):
    data = request.get_json(silent=True) or {}
    notes = str(data.get("manager_notes", "")).strip()
    if not update_manager_notes(lead_id, notes):
        return jsonify({"success": False, "error": "Lead not found"}), 404
    return jsonify({"success": True})


@dashboard_bp.route("/export/leads.csv")
def export_leads_csv():
    leads = fetch_leads()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "status", "lead_quality", "lead_score", "urgency",
        "full_name", "phone", "email", "project_type", "budget",
        "location", "timeline", "missing_info", "recommended_action",
        "summary", "created_at", "updated_at",
    ])
    for lead in leads:
        writer.writerow([
            lead["id"], lead["status"], lead["lead_quality"], lead["lead_score"],
            lead["urgency"], lead["full_name"], lead["phone"], lead["email"],
            lead["project_type"], lead["budget"], lead["location"], lead["timeline"],
            lead["missing_info"], lead["recommended_action"], lead["summary"],
            lead["created_at"], lead["updated_at"],
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=buildai-leads.csv"},
    )