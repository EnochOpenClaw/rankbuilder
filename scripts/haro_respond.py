#!/usr/bin/env python3
"""
HARO Responder - Main Script
Receives forwarded HARO query, drafts response, sends via Brevo.
Usage: haro_respond.py <email_id> [dry_run]
"""

import sys
import json
import subprocess
import urllib.request
import urllib.error
import re
from pathlib import Path
from datetime import datetime

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from haro_responder import (
    read_email, extract_forwarded_haro_content, is_relevant_query,
    score_relevance, BRAND_BIO, BRAND_VOICE
)

from credentials import BREVO_API_KEY, BREVO_ENDPOINT, SENDER_EMAIL, SENDER_NAME

BLIND_CC = "craig@fortressblinds.co.za"  # Craig sees what went out
CAREER_EMAIL = "support@ct-designs.co.za"  # Enoch's inbox

LOG_FILE = Path(__file__).parent / "logs" / "responses.jsonl"
LOG_FILE.parent.mkdir(exist_ok=True)


# ============================================================================
# EMAIL SENDING (Brevo)
# ============================================================================

def send_via_brevo(to_email: str, subject: str, html_body: str, reply_to: str = None) -> dict:
    """Send email via Brevo SMTP API."""
    payload = {
        "subject": subject,
        "to": [{"email": to_email, "name": ""}],
        "htmlContent": html_body,
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL}
    }
    
    # Add blind CC to Craig
    payload["bcc"] = [{"email": BLIND_CC}]
    
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        BREVO_ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/json",
            "api-key": BREVO_API_KEY
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return {"success": True, "message_id": result.get("messageId")}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        return {"success": False, "error": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_confirmation_to_enoch(query_data: dict, drafted_response: str):
    """Send drafted response to Craig for approval."""
    subject = f"[HARO REVIEW] {query_data.get('outlet', 'Query')} - {query_data.get('summary', 'Response ready')}"
    
    body = f"""HARO Query Response - Ready for Review
{'='*50}

📰 Outlet: {query_data.get('outlet', 'Unknown')}
👤 Journalist: {query_data.get('journalist_name', 'Unknown')}
📧 Reply-To: {query_data.get('reply_to', 'Unknown')}
⏰ Deadline: {query_data.get('deadline', 'Not specified')}
🔗 Profile: {query_data.get('journalist_profile', 'N/A')}

📋 Query Summary:
{query_data.get('summary', 'N/A')}

📝 Full Query:
{query_data.get('query_text', 'N/A')}

{'='*50}
DRAFTED RESPONSE:
{'='*50}

{drafted_response}

{'='*50}
STATUS: {query_data.get('status', 'PENDING_APPROVAL')}
{'='*50}

---
To APPROVE and send: Reply with YES or SEND
To EDIT: Reply with your revised version
To CANCEL: Reply with CANCEL
"""


# ============================================================================
# CLAUDE DRAFTING
# ============================================================================

def draft_response(query_data: dict, api_key: str) -> str:
    """Use Claude to draft a HARO response."""
    prompt = f"""You are drafting a professional response to a HARO (Help A Reporter Out) query.

## JOURNALIST DETAILS
- Name: {query_data.get('journalist_name', 'Unknown')}
- Outlet: {query_data.get('outlet', 'Unknown')}
- Profile: {query_data.get('journalist_profile', 'N/A')}

## QUERY
{query_data.get('query_text', 'No query text found')}

## DEADLINE
{query_data.get('deadline', 'Not specified')}

## BRAND BIO (your client)
{BRAND_BIO}

## BRAND VOICE
{BRAND_VOICE}

## TASK
Write a compelling, journalist-friendly HARO response that:
1. Addresses the query directly with valuable expert insights
2. Positions Craig Pauls as a knowledgeable South African expert in home improvements
3. Is 150-300 words
4. Includes a 2-sentence author bio at the end
5. Offers additional value (e.g., to provide more details, photos, etc.)
6. Uses a professional but approachable tone
7. Include the journalist's name in the greeting if known

## RESPONSE FORMAT
Start directly with the response body - no preamble needed.

End with:
---
Author: Craig Pauls, Fortress Blinds (South Africa)
Website: https://fortressblinds.co.za
Contact: craig@fortressblinds.co.za

Write ONLY the response. No explanation. No notes."""

    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            response = json.loads(resp.read().decode('utf-8'))
            return response['content'][0]['text']
    except Exception as e:
        return f"Error drafting response: {str(e)}"


# ============================================================================
# LOGGING
# ============================================================================

def log_response(query_data: dict, drafted_response: str, status: str, send_result: dict = None):
    """Log response to JSONL file."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "query": query_data,
        "drafted_response": drafted_response,
        "status": status,
        "send_result": send_result
    }
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(entry) + '\n')


# ============================================================================
# MAIN
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: haro_respond.py <email_id> [claude_api_key]")
        print("  email_id: Himalayan envelope ID to process")
        print("  claude_api_key: Optional, reads from ANTHROPIC_API_KEY env if not provided")
        sys.exit(1)
    
    email_id = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not api_key:
        api_key = subprocess.check_output(
            ["bw", "get", "password", "ANTHROPIC_API_KEY"],
            text=True, stderr=subprocess.DEVNULL
        ).strip() if Path("/usr/local/bin/bw").exists() else None
    
    # Read email
    print(f"Reading email {email_id}...")
    body = read_email(email_id)
    if not body:
        print("ERROR: Could not read email")
        sys.exit(1)
    
    # Parse HARO content
    print("Parsing HARO query...")
    query_data = extract_forwarded_haro_content(body)
    if not query_data:
        print("ERROR: No HARO query found in email")
        sys.exit(1)
    
    # Check relevance
    relevant = is_relevant_query(query_data)
    score = score_relevance(query_data)
    print(f"Relevance: {relevant} (score: {score})")
    print(f"Journalist: {query_data.get('journalist_name')}")
    print(f"Outlet: {query_data.get('outlet')}")
    print(f"Reply-To: {query_data.get('reply_to')}")
    print(f"Query: {query_data.get('query_text', '')[:100]}...")
    
    if not relevant:
        print("Query not relevant - skipping draft")
        sys.exit(0)
    
    # Draft response
    if not api_key:
        print("ERROR: No Claude API key available")
        print("Set ANTHROPIC_API_KEY env or pass as argument")
        sys.exit(1)
    
    print("Drafting response with Claude...")
    drafted = draft_response(query_data, api_key)
    
    if drafted.startswith("Error"):
        print(f"ERROR: {drafted}")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("DRAFTED RESPONSE:")
    print("="*60)
    print(drafted)
    print("="*60)
    
    # Send to Enoch for review (instead of directly to journalist)
    query_data['status'] = 'DRAFTED'
    query_data['drafted_response'] = drafted
    
    print("\nSending draft to Craig for approval...")
    print(f"  From: {SENDER_EMAIL}")
    print(f"  To: {CAREER_EMAIL}")
    print("\nReply with YES to send, or edit the response.")
    
    # For now, just log and show - in production, email Craig the draft
    log_response(query_data, drafted, "DRAFTED")
    print(f"\nLogged to {LOG_FILE}")


if __name__ == "__main__":
    main()
