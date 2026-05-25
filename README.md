\# 🏗️ AI Voice Receptionist for Construction Companies



> Built by A\&I Solutions

> An intelligent AI receptionist that answers customer calls, qualifies construction leads, detects emergencies, and saves everything to a CRM dashboard.



\---



\## 🎯 The Problem



Construction companies lose leads every day because:

\- No one answers the phone after hours

\- Receptionists forget to collect key project details

\- Hot leads do not get followed up fast enough

\- There is no system to track who called and why



\## 💡 The Solution



\*\*Sarah\*\* is an AI receptionist that never sleeps.



Sarah answers every inquiry, asks the right questions, scores each lead from 0 to 100, detects emergencies, and notifies the manager instantly via SMS — all automatically.



\---



\## ✨ Key Features



\- AI Conversation — Natural language chat powered by Groq Llama 3.3

\- Voice Responses — Sarah speaks back using ElevenLabs or gTTS

\- Lead Scoring — Automatic 0 to 100 scoring based on project details

\- Emergency Detection — Instantly flags urgent situations

\- CRM Dashboard — View, filter, and manage all leads

\- SMS Alerts — Manager gets notified for hot leads via Twilio

\- Appointment Requests — Detects and saves scheduling requests

\- Human Handoff — Auto-creates handoff for complex cases

\- CSV Export — Download all leads as spreadsheet

\- Multi-Company — White-label ready for any construction company



\---



\## 🛠️ Tech Stack



\- Backend: Python, Flask

\- AI/LLM: Groq API (Llama 3.3 70B)

\- Database: SQLite

\- Voice TTS: ElevenLabs / gTTS fallback

\- Voice STT: Deepgram

\- SMS: Twilio

\- NLP: Custom regex extraction pipeline

\- Frontend: HTML, CSS, Vanilla JavaScript



\---



\## 🏗️ Architecture



User Browser or Phone

→ Flask Web App

→ Chat Routes → ConstructionAgent via Groq LLM

→ Services Layer:

&#x20; - extraction.py — Extract name, phone, budget, location

&#x20; - lead\_scoring.py — Score lead 0 to 100

&#x20; - appointments.py — Detect scheduling requests

&#x20; - handoffs.py — Flag complex cases

&#x20; - notifications.py — SMS manager via Twilio

&#x20; - voice.py — TTS audio response

&#x20; - database.py — SQLite CRM storage

→ Admin Dashboard — View leads, filter, export CSV



\---



\## 🚀 Quick Start



1\. Clone the repo



git clone https://github.com/ilibili-AI/construction-ai-agent.git

cd construction-ai-agent



2\. Create virtual environment



python -m venv venv

venv\\Scripts\\activate



3\. Install dependencies



pip install -r requirements.txt



4\. Set up environment variables



cp .env.example .env



5\. Run the app



python app.py



Visit http://localhost:5000



\---



\## ⚙️ Environment Variables



GROQ\_API\_KEY=your\_groq\_key

AGENCY\_NAME=A\&I Solutions

COMPANY\_NAME=Your Client Company

COMPANY\_PHONE=555-000-0000

COMPANY\_EMAIL=office@example.com

COMPANY\_SERVICES=remodels, new homes, ADUs

SERVICE\_AREA=Los Angeles, Orange County

ELEVENLABS\_API\_KEY=your\_key

ELEVENLABS\_VOICE\_ID=your\_voice\_id

DEEPGRAM\_API\_KEY=your\_key

TWILIO\_ACCOUNT\_SID=your\_sid

TWILIO\_AUTH\_TOKEN=your\_token

TWILIO\_PHONE\_NUMBER=+1234567890

MANAGER\_PHONE=+1234567890



\---



\## 📊 Lead Scoring System



\- 85 to 100 — Hot Lead — Call immediately

\- 70 to 84 — Qualified Lead — Book consultation

\- 45 to 69 — Needs Review — Ask for details

\- 25 to 44 — Low Priority — Send follow-up

\- 0 to 24 — Not a Fit — Save only

\- Any score — Emergency — Call NOW



Scoring factors:

\- Contact info provided: +15

\- Project location: +15

\- Clear project type: +15

\- Budget shared: +20

\- Timeline given: +10

\- Decision maker: +10

\- Plans or permits ready: +10



\---



\## 💬 Demo Conversation



Customer: Hi, I need a quote for a kitchen remodel in Los Angeles.

&#x20;         My budget is around $75,000 and I want to start next month.

&#x20;         My name is John Smith, phone is 310-555-0199.



Sarah:    Thank you John! I have noted your kitchen remodel project

&#x20;         in Los Angeles with a budget of $75,000 starting next month.

&#x20;         Our project manager will reach out to you at 310-555-0199

&#x20;         to schedule a consultation. Is there anything else?



Dashboard: John Smith — Kitchen Remodel — LA — $75,000 — Score 91 — Hot Lead



\---



\## 🗄️ Database Schema



\- leads — All customer inquiries with scores

\- conversations — Full chat history per session

\- appointments — Scheduling requests

\- handoffs — Cases needing human review



\---



\## 🔒 Privacy and Security



\- API keys stored in .env and never committed

\- Database excluded from git

\- No real customer data in repository

\- Sessions are isolated per user



\---



\## 🔮 Future Improvements



\- Twilio phone call integration for live voice

\- Multi-language support for Spanish and Farsi

\- Google Calendar integration

\- Email follow-up automation

\- Analytics dashboard with charts

\- Login and authentication for dashboard

\- Mobile app for manager alerts



\---



\## 👤 Author



Ilia Khaleghi — A\&I Solutions

GitHub: https://github.com/ilibili-AI



\---



Built with Python, Flask, Groq, SQLite, ElevenLabs, and Twilio

