#!/usr/bin/env python3
"""
HARO Approval Handler — Processes Craig's YES/EDIT/SKIP replies.
Runs when Craig responds to a draft approval email.
Usage: haro_approve.py <email_id>
"""

import sys
import json
import re
import subprocess
import logging
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from credentials import BREVO_API_KEY, BREVO_ENDPOINT, SENDER_EMAIL, SENDER_NAME

CAREER_EMAIL = "craig@fortressblinds.co.za"
BLIND_CC = "craig@fortressblinds.co.za"

STATE_FILE = Path(__file__).parent / "state" / "processed.jsonl"
DRAFTS_DIR = Path(__file__).parent / "state" / "drafts"
STATE_FILE.parent.mkdir(exist_ok=True)
DRAFTS_DIR.mkdir(exist_ok=True)
LOG_FILE = Path(__file__).parent / "logs" / "approvals.log"


# ============================================================================
# LOGGING
# ============================================================================

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ============================================================================
# STATE
# ============================================================================

def get_pending_approvals() -> list:
    """Get all emails awaiting approval."""
    pending = []
    if not STATE_FILE.exists():
        return pending
    
    with open(STATE_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("status") == "AWAITING_APPROVAL":
                    pending.append(entry)
            except:
                pass
    return pending


def get_draft(email_id: str) -> str:
    """Retrieve a saved draft from file."""
    draft_file = DRAFTS_DIR / f"{email_id}.txt"
    if draft_file.exists():
        return draft_file.read_text()
    return ""


def update_status(email_id: str, new_status: str):
    """Update status of a processed email."""
    if not STATE_FILE.exists():
        return
    
    # Read all entries
    entries = []
    with open(STATE_FILE) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except:
                pass
    
    # Update
    for entry in entries:
        if entry.get("email_id") == email_id:
            entry["status"] = new_status
            entry["updated_at"] = datetime.now().isoformat()
    
    # Write back
    with open(STATE_FILE, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


# ============================================================================
# EMAIL SENDING
# ============================================================================

def send_to_journalist(reply_to: str, subject: str, body: str) -> dict:
    """Send approved response to journalist via Brevo."""
    # Clean reply-to (might have mailto: or angle brackets)
    reply_to_clean = re.sub(r'[<>]', '', reply_to).strip()
    
    payload = {
        "subject": subject,
        "to": [{"email": reply_to_clean}],
        "htmlContent": f"<pre style='white-space: pre-wrap; font-family: Arial, sans-serif;'>{body}</pre>",
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "bcc": [{"email": BLIND_CC}],  # Blind CC to Craig
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

        # Log to tracker
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from outreach_tracker import make_entry, log_event
            tracker_entry = make_entry(
                event='pitch_sent',
                prospect_email=reply_to_clean,
                subject=subject,
                pitch_topic=(body or '')[:80],
                source='haro',
                notes='HARO submission via Brevo BCC'
            )
            log_event(tracker_entry, quiet=True)
        except Exception as ex:
            logging.warning(f"Tracker logging failed: {ex}")

        return {"success": True, "message_id": result.get("messageId")}
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.read().decode()}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_confirmation(from_email: str, to_email: str, subject: str, status: str, details: str = ""):
    """Send confirmation back to Craig about what happened."""
    status_emoji = {"SENT": "✅", "SKIPPED": "⏭️", "EDITED": "✏️"}.get(status, "📋")
    
    payload = {
        "subject": f"{status_emoji} [HARO] {status}: {subject[:60]}",
        "to": [{"email": to_email}],
        "htmlContent": f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
<h2>{status_emoji} HARO Response {status}</h2>
<p><strong>Subject:</strong> {subject}</p>
<p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
{details}
</body>
</html>""",
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
            return json.loads(resp.read().decode('utf-8'))
    except:
        return {"success": False}


# ============================================================================
# APPROVAL PROCESSING
# ============================================================================

def process_approval(approval_email_body: str, approval_email_id: str) -> dict:
    """
    Process Craig's approval reply.
    Returns dict with action taken.
    """
    body_lower = approval_email_body.lower().strip()
    
    # Parse Craig's response
    if body_lower == 'yes' or body_lower == 'send' or body_lower == 'approve':
        action = "APPROVE"
    elif body_lower.startswith('skip') or body_lower == 'no' or body_lower == 'cancel':
        action = "SKIP"
    elif body_lower.startswith('edit ') or body_lower.startswith('revise '):
        action = "EDIT"
        edited_text = body_lower[body_lower.index(' ') + 1:].strip()
    else:
        action = "UNKNOWN"
    
    # Find matching pending approval by checking the approval email subject
    # Craig's reply will reference the original query
    pending = get_pending_approvals()
    
    if not pending:
        return {"action": "NO_PENDING", "message": "No pending approvals found"}
    
    # Use the most recent pending approval
    # In production, we'd match by email threading, but for MVP take latest
    latest = pending[-1]
    original_email_id = latest.get("email_id")
    drafted_response = get_draft(original_email_id)
    
    if action == "SKIP":
        update_status(original_email_id, "SKIPPED")
        return {
            "action": "SKIPPED",
            "original_email_id": original_email_id,
            "message": "Response skipped by Craig"
        }
    
    elif action == "APPROVE":
        # Extract subject line from drafted response (first line)
        lines = drafted_response.strip().split('\n')
        subject = lines[0].strip() if lines else "HARO Response"
        
        # Extract reply-to from state or parse from original
        reply_to = "reply@helpareporter.com"  # Default, would be stored in state
        
        # Send to journalist
        send_result = send_to_journalist(
            reply_to=reply_to,
            subject=subject,
            body=drafted_response
        )
        
        if send_result.get("success"):
            update_status(original_email_id, "SENT")
            return {
                "action": "SENT",
                "original_email_id": original_email_id,
                "message_id": send_result.get("message_id"),
                "message": f"Response sent! Message ID: {send_result.get('messageId')}"
            }
        else:
            update_status(original_email_id, "SEND_FAILED")
            return {
                "action": "SEND_FAILED",
                "original_email_id": original_email_id,
                "error": send_result.get("error")
            }
    
    elif action == "EDIT":
        # Craig wants to edit - we'd need to send them the draft to edit
        # For now, just note it
        update_status(original_email_id, "EDIT_REQUESTED")
        return {
            "action": "EDIT_REQUESTED",
            "edited_text": edited_text,
            "original_email_id": original_email_id
        }
    
    return {"action": "UNKNOWN", "message": f"Could not understand response: {body_lower[:50]}"}


# ============================================================================
# MANUAL APPROVE (for testing / one-off use)
# ============================================================================

def manual_approve(email_id: str, edited_response: str = None):
    """Manually approve a specific email by email_id."""
    pending = get_pending_approvals()
    
    target = None
    for p in pending:
        if p.get("email_id") == email_id:
            target = p
            break
    
    if not target:
        log(f"No pending approval found for email ID: {email_id}")
        log(f"Available pending: {[p.get('email_id') for p in pending]}")
        return
    
    drafted = edited_response if edited_response else get_draft(email_id)
    
    # Parse reply-to from original email
    from haro_responder import read_email, extract_forwarded_haro_content
    body = read_email(email_id)
    query_data = extract_forwarded_haro_content(body)
    reply_to = query_data.get("reply_to", "reply@helpareporter.com") if query_data else "reply@helpareporter.com"
    outlet = query_data.get("outlet", "HARO") if query_data else "HARO"
    summary = query_data.get("summary", "Query") if query_data else "Query"
    
    # Extract subject from drafted
    lines = drafted.strip().split('\n')
    subject = lines[0].strip() if lines else f"HARO Response: {summary}"
    
    log(f"Sending to: {reply_to}")
    log(f"Subject: {subject}")
    
    send_result = send_to_journalist(reply_to, subject, drafted)
    
    if send_result.get("success"):
        update_status(email_id, "SENT")
        log(f"✅ Response sent! Message ID: {send_result.get('messageId')}")
        send_confirmation(SENDER_EMAIL, SENDER_EMAIL, summary, "SENT", 
                         f"<p>Response sent to journalist at {reply_to}</p>")
    else:
        log(f"❌ Send failed: {send_result.get('error')}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    if len(sys.argv) < 2:
        # List pending approvals
        pending = get_pending_approvals()
        print("\n=== Pending HARO Approvals ===")
        if not pending:
            print("No pending approvals.")
        else:
            for p in pending:
                print(f"\nEmail ID: {p.get('email_id')}")
                print(f"Timestamp: {p.get('timestamp')}")
                draft = get_draft(p.get('email_id', ''))[:200]
                print(f"Draft preview: {draft}...")
        print()
        sys.exit(0)

    email_id = sys.argv[1]

    if email_id == "--list" or email_id == "--check":
        # List pending approvals
        pending = get_pending_approvals()
        print(f"\n=== Pending HARO Approvals: {len(pending)} ===")
        if not pending:
            print("No pending approvals.")
        else:
            for p in pending:
                print(f"\nEmail ID: {p.get('email_id')}")
                print(f"Timestamp: {p.get('timestamp')}")
                draft = get_draft(p.get('email_id', ''))[:200]
                print(f"Draft preview: {draft}...")
        print()
        sys.exit(0)
    elif email_id == "--approve" and len(sys.argv) >= 3:
        # manual_approve <email_id> [edited_response]
        target_id = sys.argv[2]
        edited = sys.argv[3] if len(sys.argv) > 3 else None
        manual_approve(target_id, edited)
    elif email_id.isdigit():
        # It's an email ID to approve manually
        manual_approve(email_id)
    else:
        print(f"Unknown argument: {email_id}")
        print("Usage: haro_approve.py [--list]")
        print("       haro_approve.py <email_id>")
        print("       haro_approve.py --approve <email_id> [edited_response]")
        sys.exit(1)


if __name__ == "__main__":
    main()
