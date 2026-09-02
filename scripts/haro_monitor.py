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
from pitch_templates import select_angle, get_angle_name_and_guidance, build_pitch_response, BRAND_BIO, BRAND_VOICE
from haro_responder import read_email, extract_forwarded_haro_content, extract_haro_digest_queries, is_relevant_query, score_relevance, humanize_draft
from blocklist import is_blocked, is_buyer, block_email, add_buyer
from credentials import BREVO_API_KEY, BREVO_ENDPOINT, SENDER_EMAIL, SENDER_NAME, NOTIFY_EMAIL
from n8n_webhook import send_event as n8n_event

# CRM integration
try:
    from crm_client import get_or_create_lead, update_lead, CRMError as CRMErr
    CRM_AVAILABLE = True
except ImportError:
    CRM_AVAILABLE = False
    CRMErr = Exception

STATE_FILE = Path(__file__).parent / "state" / "processed.jsonl"
DRAFTS_DIR = Path(__file__).parent / "state" / "drafts"
STATE_FILE.parent.mkdir(exist_ok=True)
DRAFTS_DIR.mkdir(exist_ok=True)

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


def is_approval_reply(body: str) -> tuple:
    """Detect if email is a forwarded approval reply (YES/SKIP/EDIT).
    Returns (action, email_id) if found, else (None, None)."""
    body_lower = body.lower()
    # Check if it's an approval reply by looking for action keywords
    # The forwarded reply body typically starts with "SKIP", "YES", or "EDIT"
    lines = body.strip().split('\n')
    first_line = lines[0].strip().upper() if lines else ""
    
    action = None
    if first_line in ("SKIP", "YES"):
        action = first_line
    elif body_lower.startswith("edit "):
        action = "EDIT"
    elif "\nskip\n" in body_lower or "\nskip\r" in body_lower:
        action = "SKIP"
    elif "\nyes\n" in body_lower or "\nyes\r" in body_lower:
        action = "YES"
    
    if not action:
        return None, None
    
    # Extract the referenced email ID from "Email ID: 66" in the body
    import re
    match = re.search(r'[Ee]mail\s+[Ii][Dd]:?\s*(\d+)', body)
    if match:
        return action, match.group(1)
    return action, None


def process_approval_reply(email_id: str, action: str, referenced_email_id: str = None) -> bool:
    """Process an approval reply via haro_approve.py."""
    target = referenced_email_id or email_id
    import subprocess
    result = subprocess.run(
        ["python3", str(Path(__file__).parent / "haro_approve.py"), target],
        capture_output=True, text=True, timeout=30,
        cwd=str(Path(__file__).parent.parent)
    )
    success = result.returncode == 0 and "error" not in result.stdout.lower()
    log(f"  [{email_id}] Approval reply ({action}) processed for email {target}: {'✅' if success else '❌ ' + result.stderr[:100]}")
    return success


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
    """Mark an email as processed. Drafts are stored in separate files to avoid JSONL multiline issues."""
    if drafted_response:
        _save_draft(email_id, drafted_response)
    with open(STATE_FILE, "a") as f:
        f.write(json.dumps({
            "email_id": email_id,
            "status": status,
            "drafted_response": drafted_response if drafted_response else "",
            "timestamp": datetime.now().isoformat()
        }) + "\n")


def _save_draft(email_id: str, text: str):
    """Save draft response to a file for reliable multiline storage."""
    draft_file = DRAFTS_DIR / f"{email_id}.txt"
    with open(draft_file, "w") as f:
        f.write(text)


def get_draft(email_id: str) -> str:
    """Retrieve a saved draft from file."""
    draft_file = DRAFTS_DIR / f"{email_id}.txt"
    if draft_file.exists():
        return draft_file.read_text()
    return ""


# ============================================================================
# EMAIL SENDING (Brevo)
# ============================================================================

def send_email(to_email: str, subject: str, html_body: str) -> dict:
    """Send email via Brevo API."""
    payload = {
        "subject": subject,
        "to": [{"email": to_email, "name": "Craig Pauls"}],
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
    """Draft HARO response using Ollama (kimi-k2.6:cloud) with angle guidance."""
    angle_name, angle_guidance = get_angle_name_and_guidance(query_data)
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

## PITCH ANGLE: {angle_name}
## Angle guidance (use this to frame your response):
{angle_guidance}

## TASK
Write a compelling, journalist-friendly HARO response that:
1. Addresses the query directly with valuable expert insights
2. Strongly emphasises the \"{angle_name}\" angle in your answer
3. Positions Craig Pauls as a knowledgeable South African home improvement expert
4. Is STRICTLY 150-250 words (count your words before finishing)
5. Includes a 2-sentence author bio at the end
6. Offers additional value (more details, photos, statistics, etc.)
7. Professional but approachable tone

Start with a brief greeting addressing the journalist by name if known.

End with:
---
Author: Craig Pauls, Fortress Blinds (South Africa)
Website: https://fortressblinds.co.za
Contact: craig@fortressblinds.co.za

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
    """Get all recent envelopes from inbox (himalaya v2 --json format).

    Returns list of {id, subject, sender, date, is_read}. Uses JSON output so
    parsing is robust (the old v1 pipe-table format is gone in himalaya v2).
    """
    result = subprocess.run(
        ["himalaya", "envelope", "list", "--json"],
        capture_output=True, text=True, timeout=30
    )

    envelopes = []
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return envelopes

    for env in data.get("envelopes", []):
        if not isinstance(env, dict):
            continue
        id_part = str(env.get("id", "")).strip()
        if not id_part.isdigit():
            continue
        # sender = first From entry's email
        sender = ""
        from_list = env.get("from") or []
        if from_list and isinstance(from_list, list) and isinstance(from_list[0], dict):
            sender = from_list[0].get("email", "") or from_list[0].get("name", "")
        envelopes.append({
            'id': id_part,
            'subject': env.get("subject", "") or "",
            'sender': sender,
            'date': env.get("date", "") or "",
            'is_read': False
        })

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

        # Check if this is a forwarded approval reply (YES/SKIP/EDIT)
        action, ref_email_id = is_approval_reply(body)
        if action:
            log(f"  [{email_id}] Detected approval reply: {action} (ref email {ref_email_id or email_id})")
            process_approval_reply(email_id, action, ref_email_id)
            mark_processed(email_id, f"REPLY_{action}")
            continue

        # Parse HARO content — modern digests contain MANY queries.
        # Try the digest parser first (returns a list); fall back to the legacy
        # single-forwarded-query parser for older formats.
        queries = extract_haro_digest_queries(body)
        if not queries:
            single = extract_forwarded_haro_content(body)
            if single:
                queries = [single]

        if not queries:
            log(f"  [{email_id}] No HARO query found in email")
            mark_processed(email_id, "NOT_HARO")
            continue

        log(f"  [{email_id}] Found {len(queries)} HARO query/ies in digest")
        for query_data in queries:
            processed_count, drafted_count = _process_haro_query(
                email_id, query_data, processed_count, drafted_count
            )

    log(f"=== Done. Processed: {processed_count}, Drafted: {drafted_count} ===")


def _process_haro_query(email_id, query_data, processed_count, drafted_count):
    """Process a single HARO query: relevance → blocklist → draft → approval."""
    # Check relevance
    relevant = is_relevant_query(query_data)
    score = score_relevance(query_data)
    log(f"  [{email_id}] Relevance: {relevant} (score: {score})")
    log(f"  [{email_id}] Query: {query_data.get('query_text', '')[:80]}...")

    if not relevant:
        log(f"  [{email_id}] Not relevant — marking as skipped")
        mark_processed(email_id, "SKIPPED_NOT_RELEVANT")
        n8n_event("haro_pitch", "skipped_not_relevant",
                   query=query_data.get('query_text','')[:80],
                   extra={"email_id": email_id, "score": score})
        return processed_count, drafted_count

    # Check blocklist — skip blocked addresses
    reply_to = query_data.get('reply_to', '')
    if reply_to and is_blocked(reply_to):
        log(f"  [{email_id}] Reply-to {reply_to} is blocked — skipping")
        mark_processed(email_id, "SKIPPED_BLOCKLISTED")
        n8n_event("haro_pitch", "skipped_blocked",
                   query=query_data.get('query_text','')[:80],
                   extra={"email_id": email_id, "reply_to": reply_to})
        return processed_count, drafted_count

    # Check if this is a confirmed buyer lead
    if reply_to and is_buyer(reply_to):
        log(f"  [{email_id}] Reply-to {reply_to} is a buyer lead — flagging for follow-up")

    # Draft response with angle guidance
    log(f"  [{email_id}] Drafting response with kimi-k2.6:cloud [angle: {select_angle(query_data.get('query_text',''), query_data.get('summary','')).replace('angle_','')}]...")
    drafted = draft_response(query_data)

    if drafted.startswith("Error"):
        log(f"  [{email_id}] Drafting failed: {drafted}")
        mark_processed(email_id, "ERROR_DRAFT")
        return processed_count, drafted_count

    # Polish with angle + word count discipline
    log(f"  [{email_id}] Polishing with pitch angle refinement...")
    drafted = build_pitch_response(query_data, drafted)
    word_count = len(drafted.split())
    log(f"  [{email_id}] Draft complete: {word_count} words")

    # Humanize the drafted response
    log(f"  [{email_id}] Humanizing draft to remove AI patterns...")
    humanization = humanize_draft(drafted, style="formal")
    drafted = humanization["humanized_text"]
    log(f"  [{email_id}] Humanization: {humanization['changes_summary']}")

    # Save drafted response for YES approval
    mark_processed(email_id, "AWAITING_APPROVAL", drafted)

    # Send draft to Craig for approval
    angle_name, _ = get_angle_name_and_guidance(query_data)
    angle_tag = angle_name.replace('angle_', '').upper()
    summary_preview = (query_data.get('summary') or query_data.get('query_text', '') or 'Query')[:60]
    subject = f"📋 [HARO APPROVAL] {query_data.get('outlet', 'Query')} | {angle_tag} — \"{summary_preview}\""

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
        n8n_event("haro_pitch", "pending_approval",
                   prospect=query_data.get('outlet', ''),
                   query=query_data.get('query_text','')[:100],
                   extra={
                       "email_id": email_id,
                       "score": score,
                       "journalist": query_data.get('journalist_name', ''),
                       "angle": angle_name,
                   })

        # ── CRM: Create lead (NEW → REVIEWED → QUALIFIED) ───────────────
        if CRM_AVAILABLE:
            try:
                reply_to = query_data.get('reply_to', '') or ''
                outlet = query_data.get('outlet', 'Unknown')
                journalist = query_data.get('journalist_name', '')
                query_text = query_data.get('query_text', '') or ''

                lead = get_or_create_lead(
                    source="HARO",
                    contact_email=reply_to if reply_to else None,
                    contact_name=journalist or None,
                    company_name=outlet,
                    source_query=query_text[:200] or None,
                    message_excerpt=query_text[:500],
                    quality_score=max(1, min(5, score // 20)),  # 0-100 → 1-5
                    notes=f"Angle: {angle_name} | Relevance: {score}/100",
                )
                # Lead created as NEW → immediately QUALIFIED (HarO pitches are always real opportunities)
                update_lead(lead['id'], status="QUALIFIED", lead_type="VALID")
                log(f"  CRM: created lead {lead['id']} → QUALIFIED")
            except CRMErr as e:
                log(f"  CRM lead creation failed: {e}")
    else:
        log(f"  [{email_id}] Failed to send draft: {send_result.get('error')}")

    processed_count += 1
    return processed_count, drafted_count