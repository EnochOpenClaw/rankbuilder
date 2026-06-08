#!/usr/bin/env python3
"""
HARO Monitor — Cron job that runs every 30 minutes.
Scans for new HARO queries, drafts responses, sends to Craig for approval.
"""

import sys
import json
import re
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from haro_responder import (
    read_email, extract_forwarded_haro_content, is_relevant_query,
    score_relevance, BRAND_BIO, BRAND_VOICE
)
from credentials import BREVO_API_KEY, BREVO_ENDPOINT, SENDER_EMAIL, SENDER_NAME, NOTIFY_EMAIL

STATE_FILE = Path(__file__).parent / "state" / "processed.jsonl"
STATE_FILE.parent.mkdir(exist_ok=True)

LOG_FILE = Path(__file__).parent / "logs" / "monitor.log"


# ============================================================================
# LOGGING
# ============================================================================

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ============================================================================
# STATE TRACKING
# ============================================================================

def is_processed(email_id: str) -> bool:
    """Check if we've already processed this email."""
    if not STATE_FILE.exists():
        return False
    with open(STATE_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("email_id") == email_id:
                    return True
            except:
                pass
    return False


def mark_processed(email_id: str, status: str, drafted_response: str = ""):
    """Mark an email as processed."""
    with open(STATE_FILE, "a") as f:
        f.write(json.dumps({
            "email_id": email_id,
            "status": status,
            "drafted_response": drafted_response,
            "timestamp": datetime.now().isoformat()
        }) + "\n")


# ============================================================================
# EMAIL SENDING (Brevo)
# ============================================================================

def send_email(to_email: str, subject: str, html_body: str) -> dict:
    """Send email via Brevo API."""
    payload = {
        "subject": subject,
        "to": [{"email": to_email, "name": ""}],
        "htmlContent": html_body,
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL}
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        BREVO_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json", "api-key": BREVO_API_KEY},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return {"success": True, "message_id": result.get("messageId")}
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.read().decode()}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# RESPONSE DRAFTING (Ollama kimi-k2.6:cloud)
# ============================================================================

def draft_response(query_data: dict) -> str:
    """Draft HARO response using Ollama (kimi-k2.6:cloud)."""
    prompt = f"""You are drafting a professional response to a HARO (Help A Reporter Out) query.

## JOURNALIST DETAILS
- Name: {query_data.get('journalist_name', 'Unknown')}
- Outlet: {query_data.get('outlet', 'Unknown')}
- Deadline: {query_data.get('deadline', 'Not specified')}

## QUERY
{query_data.get('query_text', 'No query text found')}

## BRAND BIO
{BRAND_BIO}

## BRAND VOICE
{BRAND_VOICE}

## TASK
Write a compelling, journalist-friendly HARO response that:
1. Addresses the query directly with valuable expert insights
2. Positions Craig Pauls as a knowledgeable South African home improvement expert
3. Is 150-250 words
4. Includes a 2-sentence author bio at the end
5. Offers additional value (more details, photos, statistics, etc.)
6. Professional but approachable tone

Start with a brief greeting addressing the journalist by name if known.

End with:
---
Author: Craig Pauls, House of Supreme (South Africa)
Website: https://houseofsupreme.co.za
Contact: craig@houseofsupreme.co.za

Write ONLY the email response. No preamble. No explanation."""

    payload = {
        "model": "kimi-k2.6:cloud",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1024}
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            response = json.loads(resp.read().decode('utf-8'))
            return response.get('response', '').strip()
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================================================
# EMAIL ENVELOPE PARSING
# ============================================================================

def strip_ansi(text: str) -> str:
    """Remove ANSI color/escape codes from text."""
    return re.sub(r'\x1b\[[0-9;]*[mK]', '', text)


def get_recent_envelopes() -> list:
    """Get all recent envelopes from inbox.

    Table format: | ID | FLAGS | SUBJECT | FROM | DATE(+00:00) |
    The SUBJECT field may contain | characters (e.g. "Lifestyle | Entertainment").
    We parse using a hybrid approach:
    - ID is at fixed position [1:5]
    - DATE anchor: scan from end for | before +00:00 timestamp
    - FROM: scan backwards from date for | where from_part has no |
    - SUBJECT: from 3rd pipe to from_sep
    """
    result = subprocess.run(
        ["himalaya", "envelope", "list", "-o", "plain"],
        capture_output=True, text=True, timeout=30
    )

    envelopes = []
    for line in result.stdout.split('\n'):
        line = strip_ansi(line)
        if not line.startswith('|') or '---' in line or 'WARN' in line:
            continue
        if '+00:00' not in line:
            continue

        try:
            # ID is always at positions 1-5 (4 chars, space-padded)
            id_part = line[1:5].strip()
            if not id_part.isdigit():
                continue

            # Find date separator (| before DATE field) by scanning backwards
            trailing = len(line) - 1  # trailing |
            date_sep = line.rindex('|', 0, trailing)

            # Find from separator: scan backwards for | where from_part has no |
            from_sep = None
            for candidate in range(date_sep - 1, -1, -1):
                if line[candidate] == '|':
                    from_candidate = line[candidate+1:date_sep].strip()
                    if '|' not in from_candidate:
                        from_sep = candidate
                        from_part = from_candidate
                        break

            if from_sep is None:
                continue

            # Find subject/from boundary: 3rd pipe from the start
            # First pipe at 0, second at 5, third at 13
            second_pipe = line.index('|', 5)          # position 5
            third_pipe = line.index('|', second_pipe + 1)  # position 13
            subject_part = line[third_pipe + 1:from_sep].strip()

            envelopes.append({
                'id': id_part,
                'subject': subject_part,
                'sender': from_part,
                'date': line[date_sep+1:trailing].strip(),
                'is_read': False
            })
        except (ValueError, IndexError):
            continue

    return envelopes


# ============================================================================
# MAIN SCAN
# ============================================================================

def main():
    log("=== HARO Monitor Run ===")

    # Get all envelopes
    envelopes = get_recent_envelopes()
    log(f"Found {len(envelopes)} total emails in inbox")

    processed_count = 0
    drafted_count = 0

    for env in envelopes:
        email_id = env['id']

        if is_processed(email_id):
            log(f"  [{email_id}] Already processed, skipping")
            continue

        log(f"  [{email_id}] Processing: {env['subject']}")

        # Read email body
        body = read_email(email_id)
        if not body:
            log(f"  [{email_id}] Could not read email")
            mark_processed(email_id, "ERROR_READ")
            continue

        # Parse HARO content
        query_data = extract_forwarded_haro_content(body)
        if not query_data:
            log(f"  [{email_id}] No HARO query found in email")
            mark_processed(email_id, "NOT_HARO")
            continue

        # Check relevance
        relevant = is_relevant_query(query_data)
        score = score_relevance(query_data)
        log(f"  [{email_id}] Relevance: {relevant} (score: {score})")
        log(f"  [{email_id}] Query: {query_data.get('query_text', '')[:80]}...")

        if not relevant:
            log(f"  [{email_id}] Not relevant — marking as skipped")
            mark_processed(email_id, "SKIPPED_NOT_RELEVANT")
            continue

        # Draft response
        log(f"  [{email_id}] Drafting response with kimi-k2.6:cloud...")
        drafted = draft_response(query_data)

        if drafted.startswith("Error"):
            log(f"  [{email_id}] Drafting failed: {drafted}")
            mark_processed(email_id, "ERROR_DRAFT")
            continue

        # Save drafted response for YES approval
        mark_processed(email_id, "AWAITING_APPROVAL", drafted)

        # Send draft to Craig for approval
        summary_preview = (query_data.get('summary') or query_data.get('query_text', '') or 'Query')[:60]
        subject = f"📋 [HARO APPROVAL] {query_data.get('outlet', 'Query')} — \"{summary_preview}\""

        query_text_display = (query_data.get('query_text') or 'N/A')[:500].replace('<', '&lt;').replace('>', '&gt;')
        drafted_display = drafted.replace('<', '&lt;').replace('>', '&gt;')

        html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px;">
<div style="background: #f8f9fa; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
<h2 style="margin-top: 0;">📋 HARO Response — Ready for Approval</h2>
<p><strong>Outlet:</strong> {query_data.get('outlet', 'Unknown')}<br>
<strong>Journalist:</strong> {query_data.get('journalist_name', 'Unknown')}<br>
<strong>Reply-To:</strong> {query_data.get('reply_to', 'N/A')}<br>
<strong>Deadline:</strong> {query_data.get('deadline', 'Not specified')}<br>
<strong>Relevance Score:</strong> {score}/100</p>
<p><strong>Query:</strong> {query_text_display}...</p>
</div>

<div style="background: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
<h3 style="margin-top: 0;">✍️ Drafted Response</h3>
<pre style="white-space: pre-wrap; font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;">{drafted_display}</pre>
</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 20px; text-align: center;">
<h3 style="margin-top: 0; color: #2e7d32;">✅ APPROVE & SEND</h3>
<p>Reply with <strong>YES</strong> to send this response to the journalist now.</p>
<p>Reply with <strong>SKIP</strong> to discard this response.</p>
<p>Reply with <strong>EDIT</strong> followed by your revised text to send an edited version.</p>
</div>

<p style="color: #666; font-size: 12px; margin-top: 20px;">
Email ID: {email_id} | Processed: {datetime.now().isoformat()}
</p>
</body>
</html>"""

        send_result = send_email(NOTIFY_EMAIL, subject, html_body)
        if send_result.get("success"):
            log(f"  [{email_id}] Draft sent to Craig for approval ✅")
            drafted_count += 1
        else:
            log(f"  [{email_id}] Failed to send draft: {send_result.get('error')}")

        processed_count += 1

    log(f"=== Done. Processed: {processed_count}, Drafted: {drafted_count} ===")


if __name__ == "__main__":
    main()