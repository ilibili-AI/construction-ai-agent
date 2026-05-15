import re
from typing import Optional

PROJECT_KEYWORDS = {
    "Kitchen Remodel": ["kitchen"],
    "Bathroom Remodel": ["bathroom", "restroom", "bath"],
    "ADU": ["adu", "accessory dwelling", "guest house", "granny flat"],
    "Roofing": ["roof", "roofing", "shingle", "roof leak"],
    "Flooring": ["floor", "flooring", "tile", "hardwood", "vinyl"],
    "Concrete": ["concrete", "driveway", "slab", "patio"],
    "Commercial Construction": ["commercial", "office", "tenant improvement", "retail", "restaurant", "warehouse"],
    "New Home Construction": ["new home", "build a house", "custom home", "ground up", "new build"],
    "Addition": ["addition", "add a room", "second story", "extension"],
    "Renovation": ["renovation", "renovate", "remodel"],
    "Repair": ["repair", "fix", "damage", "broken"],
}

CITY_HINTS = [
    "los angeles", "orange county", "san diego", "santa monica", "pasadena",
    "irvine", "anaheim", "long beach", "glendale", "burbank", "beverly hills",
    "torrance", "sherman oaks", "van nuys", "culver city", "walnut creek",
    "san francisco", "san jose", "oakland", "fremont", "hayward",
]

EMERGENCY_WORDS = [
    "emergency", "fire", "gas smell", "flood", "flooding", "spark", "sparks",
    "collapse", "structural failure", "unsafe", "injury", "leaking badly",
    "active leak", "sewer backup", "urgent roof leak",
]

HIGH_URGENCY_WORDS = [
    "urgent", "asap", "today", "tomorrow", "deadline",
    "inspection", "permit issue", "complaint",
]

LOW_INTENT_WORDS = [
    "just shopping", "cheapest", "free advice", "no budget",
    "maybe later", "not sure yet",
]


def clean_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    blocked = {"sarah", "manager", "office", "company", "unknown", "ai", "bot"}
    if value.lower() in blocked or len(value) < 2:
        return "Unknown"
    return " ".join(part.capitalize() for part in value.split())


def extract_name(text: str) -> str:
    patterns = [
        r"my name is\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        r"i am\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        r"i'm\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        r"this is\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        r"name[:\s]+([A-Za-z]+(?:\s+[A-Za-z]+){0,2})",
        r"call me\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,1})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_name(match.group(1))
    return "Unknown"


def extract_phone(text: str) -> str:
    match = re.search(
        r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}",
        text
    )
    return match.group(0).strip() if match else "Unknown"


def extract_email(text: str) -> str:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0).strip() if match else "Unknown"


def extract_budget(text: str) -> str:
    patterns = [
        r"\$\s?\d+[\d,]*(?:\s?(?:-|to)\s?\$?\d+[\d,]*)?(?:\s?(?:k|K|thousand|million))?",
        r"\d+[\d,]*\s?(?:k|K)\b(?:\s?(?:-|to)\s?\d+[\d,]*\s?(?:k|K)\b)?",
        r"budget\s*(?:is|of|around|about|roughly)?\s*[:\-]?\s*([^.\n;,]{3,40})",
        r"around\s+\$?\d+[\d,]*",
        r"about\s+\$?\d+[\d,]*",
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
    elif "million" in lower and amount < 1000:
        amount *= 1000000
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
        if any(kw in lower for kws in PROJECT_KEYWORDS.values() for kw in kws):
            return sentence.strip()[:240]
    return "Unknown"


def extract_location(text: str) -> str:
    lower = text.lower()
    for city in CITY_HINTS:
        if city in lower:
            return city.title()
    match = re.search(r"(?:in|near|at|located in|project is in)\s+([A-Z][A-Za-z .\-]{2,44})", text)
    if match:
        location = match.group(1).strip().rstrip(".,")
        location = re.sub(r"\s+(and|with|for|my|the)\s+.*$", "", location, flags=re.IGNORECASE)
        return location
    return "Unknown"


def detect_property_type(text: str) -> str:
    lower = text.lower()
    if any(x in lower for x in ["commercial", "office", "retail", "restaurant", "warehouse", "tenant"]):
        return "Commercial"
    if any(x in lower for x in ["home", "house", "condo", "apartment", "residential", "adu", "duplex"]):
        return "Residential"
    return "Unknown"


def extract_timeline(text: str) -> str:
    lower = text.lower()
    if any(x in lower for x in ["today", "asap", "immediately", "right away", "right now"]):
        return "Immediate"
    if "tomorrow" in lower:
        return "Tomorrow"
    if any(x in lower for x in ["this week", "next week", "within two weeks"]):
        return "Within 1-2 weeks"
    if any(x in lower for x in ["this month", "next month", "30 days", "within a month"]):
        return "Within 30 days"
    if any(x in lower for x in ["3 months", "three months", "quarter"]):
        return "Within 3 months"
    if any(x in lower for x in ["flexible", "no rush", "whenever", "later this year"]):
        return "Flexible"
    return "Unknown"


def detect_urgency(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in EMERGENCY_WORDS):
        return "Emergency"
    if any(word in lower for word in HIGH_URGENCY_WORDS):
        return "High"
    return "Normal"


def extract_appointment_window(text: str) -> str:
    patterns = [
        r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)[^.]*(?:at|from|between)[^.]*(?:am|pm)",
        r"\d{1,2}(?::\d{2})?\s?(?:am|pm)[^.]*(?:to|-)\s?\d{1,2}(?::\d{2})?\s?(?:am|pm)",
        r"(?:tomorrow|next week|this week)[^.]*(?:at|from|between)[^.]*(?:am|pm)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return "Unknown"