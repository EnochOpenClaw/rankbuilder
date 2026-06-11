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
SENDER_EMAIL = "craig@houseofsupreme.co.za"
SENDER_NAME = "Craig Pauls"
NOTIFY_EMAIL = "craig@houseofsupreme.co.za"

# Connectively login credentials
CONNECTIVELY_EMAIL = os.environ.get("CONNECTIVELY_EMAIL", "")
CONNECTIVELY_PASSWORD = os.environ.get("CONNECTIVELY_PASSWORD", "")

# LinkedIn OAuth (for posting to personal profile via API)
# Client ID and Secret from: linkedin.com/developers → your app → Auth
LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "77dby6enaswjd8")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "WPL_AP1.RMMYuALrUeORaB0D.rplX9g==")
# Access token (set after OAuth handshake)
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "AQXGt2x2YZgC1KJcMDw9Fkg4yGuiQ3YIdjTodTG9QVFNJDbAiy")
LINKEDIN_ACCESS_TOKEN_EXPIRY = os.environ.get("LINKEDIN_ACCESS_TOKEN_EXPIRY", "")

# Medium posting (via Playwright — no API token needed, uses cookie session)
MEDIUM_SESSION_COOKIE = os.environ.get("MEDIUM_SESSION_COOKIE", "")