import os
from dotenv import load_dotenv

load_dotenv()

# Flask
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
APP_ENV = os.getenv("APP_ENV", "development")

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", "buildai.db")

# Company Profile
COMPANY_NAME = os.getenv("COMPANY_NAME", "BuildAI Construction")
COMPANY_PHONE = os.getenv("COMPANY_PHONE", "(555) 010-2040")
COMPANY_EMAIL = os.getenv("COMPANY_EMAIL", "office@example.com")
COMPANY_SERVICES = os.getenv("COMPANY_SERVICES", "custom homes, remodels, ADUs, roofing, concrete")
SERVICE_AREA = os.getenv("SERVICE_AREA", "Los Angeles, Orange County, San Diego")

# Admin
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# AI
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
AGENT_TTL_SECONDS = int(os.getenv("AGENT_TTL_SECONDS", "21600"))

# TTS / Voice
ENABLE_TTS = os.getenv("ENABLE_TTS", "true").lower() == "true"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
MANAGER_PHONE = os.getenv("MANAGER_PHONE", "")

COMPANY_PROFILE = {
    "company_name": COMPANY_NAME,
    "phone": COMPANY_PHONE,
    "email": COMPANY_EMAIL,
    "services": COMPANY_SERVICES,
    "area": SERVICE_AREA,
}