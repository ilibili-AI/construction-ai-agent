from dataclasses import dataclass, asdict
from typing import Tuple, Dict, Any

from services.extraction import (
    extract_name, extract_phone, extract_email, extract_budget,
    extract_project_type, extract_project_scope, extract_location,
    detect_property_type, extract_timeline, detect_urgency,
    budget_amount, LOW_INTENT_WORDS,
)
from services.database import get_existing_lead, transcript_for_session


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


def first_known(new_value: str, old_value: str, fallback: str = "Unknown") -> str:
    if new_value and new_value != "Unknown":
        return new_value
    if old_value and old_value != "Unknown":
        return old_value
    return fallback


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
    subject = (
        f"{profile.full_name} is asking about {profile.project_type.lower()}"
        if profile.full_name != "Unknown"
        else f"Prospect is asking about {profile.project_type.lower()}"
    )
    parts = [subject]
    if profile.location != "Unknown":
        parts.append(f"in {profile.location}")
    if profile.budget != "Unknown":
        parts.append(f"with budget {profile.budget}")
    if profile.timeline != "Unknown":
        parts.append(f"and timeline {profile.timeline.lower()}")
    return " ".join(parts) + "."


def score_lead(profile: LeadProfile, transcript: str) -> Tuple[int, str, str]:
    score = 0
    lower = transcript.lower()

    if profile.full_name != "Unknown":
        score += 8
    if profile.phone != "Unknown" or profile.email != "Unknown":
        score += 15
    if profile.location != "Unknown":
        score += 15
    if profile.project_type != "General Construction":
        score += 15
    if profile.project_scope != "Unknown":
        score += 10
    if profile.timeline != "Unknown":
        score += 10
    if profile.budget != "Unknown":
        score += 20
    if budget_amount(profile.budget) >= 50000:
        score += 8
    if any(x in lower for x in ["owner", "own the property", "we own", "decision maker", "property manager"]):
        score += 10
    if any(x in lower for x in ["plans", "drawings", "permit", "engineering", "architect", "blueprint"]):
        score += 10
    if profile.urgency == "High":
        score += 7
    if any(x in lower for x in LOW_INTENT_WORDS):
        score -= 15
    if any(x in lower for x in ["renting", "landlord hasn't approved", "not approved yet"]):
        score -= 8

    score = max(0, min(100, score))

    if profile.urgency == "Emergency":
        return 100, "Emergency", "Call now — treat as emergency"
    if score >= 85:
        return score, "Hot Lead", "Call this person as soon as possible"
    if score >= 70:
        return score, "Qualified Lead", "Book a consultation or site visit"
    if score >= 45:
        return score, "Needs Review", "Ask for the missing details"
    if score >= 25:
        return score, "Low Priority", "Send a simple follow-up message"
    return score, "Not a Fit", "Save the record but no urgent follow-up needed"


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


def lead_to_dict(profile: LeadProfile) -> Dict[str, Any]:
    return asdict(profile)