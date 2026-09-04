#!/usr/bin/env python3
"""
Credentials — loaded from environment variables.
Set these in your shell profile, .env file, or cron job.
Never commit actual values to git.
"""

import os
from pathlib import Path

# Load .env file if present (project root)
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

# Brevo (Sendinblue) API key for transactional email
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "craig@fortressblinds.co.za")
SENDER_NAME = "Craig Pauls"
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "craig@fortressblinds.co.za")

# Connectively login credentials
# Prefer env vars (set in Coolify/container), but fall back to the local
# gitignored lib/credentials.json so the correct account is used even when
# the env var is stale/wrong (e.g. agentdevelopmentops@gmail.com which does
# not exist on Connectively).
CONNECTIVELY_EMAIL = os.environ.get("CONNECTIVELY_EMAIL", "")
CONNECTIVELY_PASSWORD = os.environ.get("CONNECTIVELY_PASSWORD", "")
if not CONNECTIVELY_EMAIL or not CONNECTIVELY_PASSWORD:
    _cred_file = Path(__file__).parent / "credentials.json"
    if _cred_file.exists():
        try:
            import json as _json
            _c = _json.loads(_cred_file.read_text()).get("connectively", {})
            CONNECTIVELY_EMAIL = CONNECTIVELY_EMAIL or _c.get("email", "")
            CONNECTIVELY_PASSWORD = CONNECTIVELY_PASSWORD or _c.get("password", "")
        except Exception:
            pass

# LinkedIn OAuth (for posting to personal profile via API)
# Client ID and Secret from: linkedin.com/developers → your app → Auth
LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "77dby6enaswjd8")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "WPL_AP1.RMMYuALrUeORaB0D.rplX9g==")
# Access token (set after OAuth handshake)
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "AQXGt2x2YZgC1KJcMDw9Fkg4yGuiQ3YIdjTodTG9QVFNJDbAiy")
LINKEDIN_ACCESS_TOKEN_EXPIRY = os.environ.get("LINKEDIN_ACCESS_TOKEN_EXPIRY", "")

# Medium posting (via Playwright — no API token needed, uses cookie session)
MEDIUM_SESSION_COOKIE = os.environ.get("MEDIUM_SESSION_COOKIE", "")