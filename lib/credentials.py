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