"""
RankBuilder CRM — AI Auto-Response Draft Generator

Uses OpenRouter to draft a personalized reply for a new lead. The agent
reviews/edits the draft before sending — human always approves.

Endpoint: POST /api/ai/draft-reply (body: { lead_id or lead fields })
"""

import json
import os
import urllib.request
import urllib.error

from backend.database import Lead, SessionLocal

# Load OPENROUTER_API_KEY from env (set in /root/rankbuilder/.env)
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = os.environ.get("AI_DRAFT_MODEL", "openai/gpt-4o-mini")
BASE = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are an AI sales assistant for House of Supreme, a South African company that supplies and installs custom aluminium security shutters, insect screens and window blinds. A new lead has just come in.

Write a warm, professional reply to this lead. Keep it under 150 words. Structure:
1. Acknowledge their enquiry personally
2. Mention something relevant to their request
3. State you will arrange a measure/quote
4. Ask ONE simple qualifying question (budget or timeline)
5. Sign as the salesperson's name provided (the current CRM user)

Tone: professional South African small-business, friendly but not pushy."""


def _load_key():
    global API_KEY
    if API_KEY:
        return API_KEY
    # Fall back to .env
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("OPENROUTER_API_KEY="):
                    API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return API_KEY


def draft_reply(lead, user_name: str = "", user_email: str = "") -> dict:
    """Generate an AI draft reply for a lead. Returns {draft, error}."""
    key = _load_key()
    if not key:
        return {"draft": None, "error": "OPENROUTER_API_KEY not configured"}

    name = lead.contact_name or "there"
    company = lead.company_name or "your company"
    location = lead.location or ""
    enquiry = lead.message_excerpt or lead.source_query or "a quote enquiry"
    source = lead.source.value if hasattr(lead.source, "value") else str(lead.source or "")
    # The salesperson signing the reply = the current CRM user (not hardcoded).
    signer = user_name or user_email or "the House of Supreme team"

    user_prompt = f"""
Lead details:
- Name: {name}
- Company: {company}
- Location: {location}
- Source: {source}
- Enquiry: {enquiry}

Sign the reply as: {signer}

Write the reply now.
"""

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 250,
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        BASE,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.loads(resp.read().decode())
        content = d.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            return {"draft": None, "error": "Empty AI response"}
        return {"draft": content, "error": None}
    except urllib.error.HTTPError as e:
        return {"draft": None, "error": f"OpenRouter HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"draft": None, "error": f"AI request failed: {str(e)[:200]}"}


def draft_for_lead_id(lead_id: str, user_name: str = "", user_email: str = "") -> dict:
    """Load a lead by id and generate a draft."""
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return {"draft": None, "error": "Lead not found"}
        return draft_reply(lead, user_name=user_name, user_email=user_email)
    finally:
        db.close()
