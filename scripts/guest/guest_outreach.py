#!/usr/bin/env python3
"""
Guest Outreach Manager
Sends pitch emails via Brevo, manages approval workflow:
  - Email Craig for approval (pitch summary + full content)
  - Craig replies YES → email sent to target
  - Craig replies SKIP → discarded
  - Craig replies EDIT → edited version sent
  - Tracks sent status in DB
"""

import json
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib"))
from credentials import BREVO_API_KEY, SENDER_EMAIL, SENDER_NAME, NOTIFY_EMAIL


def _run_webwright_discovery(skipped_pitches: list):
    """
    Fallback: trigger Webwright contact discovery for pitches missing contact emails.
    Uses hard subprocess timeout to prevent runaway processes.
    """
    urls = [p.get("prospect_url", "") for p in skipped_pitches if p.get("prospect_url")]
    if not urls:
        return

    script = Path(__file__).parent / "webwright_engine" / "prospect_discovery.py"
    if not script.exists():
        print(f"  ⚠️ Webwright discovery script not found at {script}")
        return

    # Build URL list file for batch processing
    urls_file = Path("/tmp/webwright_discovery_urls.txt")
    urls_file.write_text("\n".join(urls))

    print(f"  🔍 Triggering Webwright contact discovery for {len(urls)} prospects...")
    try:
        result = subprocess.run(
            ["timeout", "90", "python3", str(script), "--batch-urls-file", str(urls_file)],
            capture_output=True,
            text=True,
            timeout=95
        )
        if result.returncode == 0:
            print(f"  ✅ Webwright discovery complete")
        else:
            print(f"  ⚠️ Webwright discovery returned code {result.returncode}")
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ Webwright discovery timed out after 90s")
    except Exception as e:
        print(f"  ⚠️ Webwright discovery error: {e}")
    finally:
        urls_file.unlink(missing_ok=True)

# ============================================================================
# CONFIG
# ============================================================================

PROSPECTS_DIR = Path(__file__).parent.parent.parent / "prospects"
PITCHES_DIR = PROSPECTS_DIR / "pitches"
OUTREACH_LOG = PROSPECTS_DIR / "outreach_log.jsonl"

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
MAX_DAILY_SENDS = 10
COOLDOWN_DAYS = 14  # Don't re-pitch same domain within 14 days

# ============================================================================
# EMAIL SENDING (Brevo API)
# ============================================================================

def send_email(to_email: str, subject: str, html_body: str, bcc: str = None) -> dict:
    """Send email via Brevo API. Returns success/error dict."""
    import urllib.request
    import urllib.error
    
    payload = {
        "sender": {"email": SENDER_EMAIL, "name": SENDER_NAME},
        "to": [{"email": to_email, "name": to_email.split("@")[0]}],
        "subject": subject,
        "htmlContent": html_body,
    }
    if bcc:
        payload["bcc"] = [{"email": bcc}]
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        BREVO_ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/json",
            "api-key": BREVO_API_KEY,
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return {"success": True, "message_id": result.get("messageId", "")}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='ignore')
        return {"success": False, "error": f"HTTP {e.code}: {error_body[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# APPROVAL EMAIL — Send pitch to Craig for review
# ============================================================================

def email_craig_for_approval(pitch: dict) -> dict:
    """Email Craig a pitch summary for approval."""
    prospect_url = pitch.get("prospect_url", "")
    subject = pitch.get("subject", "Guest post pitch")
    article = pitch.get("article_proposal", "")
    body = pitch.get("body", "")
    author_bio = pitch.get("author_bio", "")
    contact_email = pitch.get("contact_email", "unknown")
    score = pitch.get("prospect_score", "?")
    da = pitch.get("prospect_da", "?")
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto;">
      <h2 style="color: #1a1a2e;">📋 Guest Post Pitch — Approval Needed</h2>
      
      <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <p><strong>📌 Article:</strong> {article}</p>
        <p><strong>🎯 Target:</strong> <a href="{prospect_url}">{prospect_url}</a></p>
        <p><strong>📧 To:</strong> {contact_email}</p>
        <p><strong>⭐ Score:</strong> {score} | <strong>🌐 DA:</strong> {da}</p>
      </div>
      
      <h3>Subject:</h3>
      <p style="background: #e8f4fd; padding: 10px; border-radius: 5px;">{subject}</p>
      
      <h3>Email Body:</h3>
      <div style="background: #fff; border: 1px solid #ddd; padding: 20px; border-radius: 5px; white-space: pre-wrap;">{body}</div>
      
      <h3>Author Bio:</h3>
      <p style="color: #555;">{author_bio}</p>
      
      <hr style="margin: 30px 0;">
      
      <h3>🚀 To Send:</h3>
      <p><strong>Reply YES</strong> → Send this pitch now<br>
      <strong>Reply SKIP</strong> → Discard this pitch<br>
      <strong>Reply EDIT [new text]</strong> → Send with your edits</p>
      
      <p style="color: #888; font-size: 12px; margin-top: 20px;">
        Generated by RankBuilder AI on {datetime.now().strftime('%Y-%m-%d %H:%M')}
      </p>
    </div>
    """
    
    return send_email(
        to_email=NOTIFY_EMAIL,
        subject=f"📋 [GUEST POST APPROVAL] {subject}",
        html_body=html
    )

# ============================================================================
# SEND APPROVED PITCH — to the target contact
# ============================================================================

def send_approved_pitch(pitch: dict) -> dict:
    """Send the pitch to the target contact email.
    
    Returns error dict if no contact email is available.
    """
    to_email = pitch.get("contact_email")
    
    if not to_email:
        return {
            "success": False,
            "error": "No contact email available for this prospect. Pitch needs contact enrichment before sending.",
            "skipped": True,
        }
    subject = pitch.get("subject", "")
    body = pitch.get("body", "")
    author_bio = pitch.get("author_bio", "")
    signoff = pitch.get("signoff", "Kind regards")
    
    # Build full email HTML
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px;">
      <p>{pitch.get('greeting', 'Hi')},</p>
      <div style="white-space: pre-wrap;">{body}</div>
      <br>
      <p style="white-space: pre-wrap;">{author_bio}</p>
      <br>
      <p>{signoff},<br>{SENDER_NAME}<br>
      <a href="https://houseofsupreme.co.za">houseofsupreme.co.za</a></p>
    </div>
    """
    
    # Idempotency: skip if already logged as sent today
    today = datetime.now().strftime('%Y-%m-%d')
    if OUTREACH_LOG.exists():
        for line in OUTREACH_LOG.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                if (entry.get('timestamp','').startswith(today) and
                    entry.get('status') == 'sent' and
                    entry.get('prospect_url') == pitch.get('prospect_url')):
                    return {"success": True, "skipped": True, "note": "Already logged as sent today"}
    
    result = send_email(to_email, subject, html_body, bcc=NOTIFY_EMAIL)
    
    # Log the send
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "prospect_url": pitch.get("prospect_url"),
        "contact_email": to_email,
        "subject": subject,
        "article": pitch.get("article_proposal"),
        "status": "sent" if result["success"] else "failed",
        "result": result,
    }
    with open(OUTREACH_LOG, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    return result

# ============================================================================
# PARSE CRAIG'S REPLIES — via himalaya
# ============================================================================

def get_recent_craig_replies(lookback_hours: int = 48) -> list:
    """Get recent emails from Craig (sent to our approval address)."""
    import subprocess
    from datetime import datetime, timedelta
    
    result = subprocess.run(
        ["himalaya", "envelope", "list", "-o", "plain"],
        capture_output=True, text=True, cwd=Path.home()
    )
    if result.returncode != 0:
        return []
    
    replies = []
    cutoff = datetime.now() - timedelta(hours=lookback_hours)
    
    for line in result.stdout.strip().split('\n'):
        if not line or line.startswith('ID'):
            continue
        parts = [p.strip() for p in line.split('|') if p.strip()]
        if len(parts) >= 4:
            env_id = parts[0]
            subject = parts[1]
            date_str = parts[3]
            
            # Only look at approval-related emails (strict check)
            if '[GUEST POST APPROVAL]' in subject:
                # Parse date
                try:
                    # Handle various date formats: YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM+00:00, etc.
                    date_clean = re.sub(r'[+-]\d{2}:\d{2}$', '', date_str).strip()
                    email_date = datetime.strptime(date_clean, "%Y-%m-%d %H:%M")
                    if email_date >= cutoff:
                        replies.append({
                            "id": env_id,
                            "subject": subject,
                            "date": date_str,
                            "body": subprocess.run(
                                ["himalaya", "message", "read", env_id],
                                capture_output=True, text=True, cwd=Path.home()
                            ).stdout
                        })
                except:
                    pass
    
    return replies

def parse_approval_reply(body: str) -> dict:
    """Parse Craig's reply to extract action (YES/SKIP/EDIT).
    
    Handles both plain replies and forwarded emails where the approval
    request is quoted below Craig's response. Only checks Craig's actual
    reply text (before the ___ separator), not the quoted original.
    """
    import re as _re
    # Strip ANSI terminal codes (himalaya uses colored output)
    body = _re.sub(r'\x1b\[[0-9;]*[mKHF]', '', body)
    
    # Split on the ___ separator that marks start of quoted original email
    # This leaves only Craig's actual reply text
    body_craig = body.split('________________________________')[0].strip()
    
    # Now check only the first ~600 chars of Craig's reply (enough for YES/SKIP/EDIT)
    first = body_craig[:600].upper()
    
    # SKIP is a full word
    if _re.search(r'\bSKIP\b', first):
        return {"action": "skip"}
    
    # EDIT — check if EDIT appears in Craig's reply (not in the quoted original)
    if _re.search(r'\bEDIT\b', first):
        # Extract the text following EDIT (Craig's edited pitch content)
        edit_match = _re.search(r'\bEDIT\s+([\s\S]{10,})', body_craig[:2000], _re.IGNORECASE)
        if edit_match:
            return {"action": "edit", "new_text": edit_match.group(1).strip()}
        return {"action": "yes"}
    
    # YES is a full word
    if _re.search(r'\bYES\b', first):
        return {"action": "yes"}
    
    return {"action": "unknown"}

# ============================================================================
# APPROVAL WORKFLOW — Check for replies and process
# ============================================================================

def check_and_process_approvals():
    """Check for Craig's approval replies and process them."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Checking for approval replies...")
    
    replies = get_recent_craig_replies(lookback_hours=48)
    
    if not replies:
        print("  No new approval replies found.")
        return
    
    processed = 0
    for reply in replies:
        body = reply.get("body", "")
        parsed = parse_approval_reply(body)
        action = parsed.get("action")
        
        # Find the pitch this refers to
        subject = reply.get("subject", "")
        
        if action == "yes":
            print(f"  ✅ APPROVED: {subject[:60]}")
            pitch = find_pitch_by_subject(subject)
            if not pitch:
                print(f"     → Pitch not found in DB")
                continue
            result = send_approved_pitch(pitch)
            if result.get("skipped") and result.get("note") == "Already logged as sent today":
                print(f"     → Already sent earlier today. Skipping.")
            elif pitch.get("status") in ("sent", "skipped"):
                print(f"     → Already marked as {pitch['status']}. Skipping.")
            elif result.get("skipped"):
                print(f"     → No contact email. Marking for enrichment.")
                pitch["status"] = "needs_contact"
                save_pitch(pitch)
            else:
                pitch["status"] = "sent" if result["success"] else "send_failed"
                pitch["sent_at"] = datetime.now().isoformat()
                save_pitch(pitch)
                print(f"     → {'Sent! ✓' if result['success'] else 'Failed: ' + str(result.get('error',''))}")
        

        elif action == "edit":
            print(f"  ✏️  EDITED: {subject[:60]}")
            pitch = find_pitch_by_subject(subject)
            if not pitch:
                print(f"     → Pitch not found in DB")
                continue
            pitch["body"] = parsed["new_text"]
            result = send_approved_pitch(pitch)
            if pitch.get("status") in ("sent", "skipped"):
                print(f"     → Already marked as {pitch['status']}. Skipping update.")
            elif result.get("skipped"):
                print(f"     → No contact email. Marking for enrichment.")
                pitch["status"] = "needs_contact"
                save_pitch(pitch)
            else:
                pitch["sent_at"] = datetime.now().isoformat()
                pitch["status"] = "sent" if result["success"] else "send_failed"
                save_pitch(pitch)
                print(f"     → {'Sent with edits! ✓' if result['success'] else 'Failed: ' + str(result.get('error',''))}")
        elif action == "skip":
            print(f"  ⏭️  SKIPPED: {subject[:60]}")
            pitch = find_pitch_by_subject(subject)
            if pitch:
                pitch["status"] = "skipped"
                pitch["skipped_at"] = datetime.now().isoformat()
                save_pitch(pitch)
        else:
            print(f"  ❓ UNKNOWN action in: {subject[:60]}")
        
        processed += 1
    
    print(f"\n  Processed {processed} replies.")

def find_pitch_by_subject(subject: str) -> dict:
    """Find the pitch file matching this approval email subject.
    
    Strips email prefixes (Re:, Fw:, Fwd:) to extract the actual pitch subject.
    Uses multiple strategies: exact subject match → URL domain match → article title match.
    """
    # Strip common email prefixes
    clean = re.sub(r'^(?:Re?:?\s*|Fwd?:?\s*)+', '', subject, flags=re.IGNORECASE).strip()
    
    # Extract the pitch subject from [GUEST POST APPROVAL] wrapper
    match = re.search(r'\[GUEST POST APPROVAL\]\s*(.+)', clean)
    if not match:
        return None
    pitch_subject = match.group(1).strip()
    
    # Strategy 1: exact subject match
    for f in PITCHES_DIR.glob("pitch_*.json"):
        pitch = json.loads(f.read_text())
        if pitch.get("subject") == pitch_subject:
            return pitch
    
    # Strategy 2: URL/domain match — extract domain like "www.linksmanagement.com"
    url_match = re.search(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9][a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[\w.-]*)?)', pitch_subject)
    if url_match:
        domain = url_match.group(1).lower()
        for f in PITCHES_DIR.glob("pitch_*.json"):
            pitch = json.loads(f.read_text())
            pitch_url = pitch.get("prospect_url", "").lower()
            if domain in pitch_url or pitch_url.startswith(f"https?://{domain}"):
                return pitch
    
    # Strategy 3: article title keyword match (for "coastal shutter expertise" type subjects)
    # Extract key phrase (remove common filler words)
    key_phrase = re.sub(r'\b(guest post|idea|for us|write for us|article)\b', '', pitch_subject, flags=re.IGNORECASE).strip()
    key_phrase = re.sub(r'\s+', ' ', key_phrase).strip()
    if len(key_phrase) >= 10:
        for f in PITCHES_DIR.glob("pitch_*.json"):
            pitch = json.loads(f.read_text())
            article = pitch.get("article_proposal", "")
            if key_phrase.lower() in article.lower() or article.lower() in key_phrase.lower():
                return pitch
    
    # Strategy 4: fuzzy contains (pitch subject in email clean, or vice versa)
    for f in PITCHES_DIR.glob("pitch_*.json"):
        pitch = json.loads(f.read_text())
        p_subj = pitch.get("subject", "")
        if p_subj and (p_subj in clean or clean in p_subj):
            return pitch
    
    return None

def save_pitch(pitch: dict):
    """Find and update the pitch file."""
    for f in PITCHES_DIR.glob("pitch_*.json"):
        existing = json.loads(f.read_text())
        if existing.get("prospect_url") == pitch.get("prospect_url") and \
           existing.get("created_at") == pitch.get("created_at"):
            f.write_text(json.dumps(pitch, indent=2))
            return

# ============================================================================
# SUBMIT PITCHES FOR APPROVAL — Queue pending pitches
# ============================================================================

def submit_pending_pitches(max_pitches: int = 3):
    """
    Find pitches with status='draft' and email Craig for approval.
    Only submits up to max_pitches per run to avoid spamming.
    """
    pitches = sorted(
        [json.loads(f.read_text()) for f in PITCHES_DIR.glob("pitch_*.json")],
        key=lambda x: x.get("prospect_score", 0), reverse=True
    )
    
    pending = [p for p in pitches if p.get("status") == "draft" and p.get("contact_email")][:max_pitches]
    skipped_no_email = [p for p in pitches if p.get("status") == "draft" and not p.get("contact_email")]
    
    if skipped_no_email:
        print(f"  Skipping {len(skipped_no_email)} pitches with no contact email (will submit when enriched)")
        # Trigger Webwright fallback to discover contact emails
        _run_webwright_discovery(skipped_no_email)

    if not pending:
        print("  No pending pitches to submit.")
        return
    
    print(f"  Submitting {len(pending)} pitches for approval...")
    for pitch in pending:
        result = email_craig_for_approval(pitch)
        if result.get("success"):
            pitch["status"] = "pending"
            pitch["submitted_at"] = datetime.now().isoformat()
            save_pitch(pitch)
            print(f"  ✅ Submitted: {pitch.get('article_proposal', 'unknown')}")
        else:
            print(f"  ❌ Failed to submit: {pitch.get('prospect_url', '')}")
            print(f"     Error: {result.get('error', 'unknown')}")

# ============================================================================
# DAILY LIMITS CHECK
# ============================================================================

def get_today_send_count() -> int:
    """Count how many pitches we've sent today."""
    if not OUTREACH_LOG.exists():
        return 0
    
    today = datetime.now().strftime('%Y-%m-%d')
    count = 0
    for line in OUTREACH_LOG.read_text().splitlines():
        if line.strip():
            entry = json.loads(line)
            if entry.get("timestamp", "").startswith(today) and entry.get("status") == "sent":
                count += 1
    return count

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Guest Outreach Manager")
    parser.add_argument("--submit", action="store_true",
                        help="Submit pending pitches to Craig for approval")
    parser.add_argument("--check", action="store_true",
                        help="Check for Craig's approval replies")
    parser.add_argument("--status", action="store_true",
                        help="Show outreach status")
    parser.add_argument("--dry", action="store_true",
                        help="Dry run — show what would be sent without sending")
    
    args = parser.parse_args()
    
    if args.status:
        # Show current outreach status
        pitches = sorted(
            [json.loads(f.read_text()) for f in PITCHES_DIR.glob("pitch_*.json")],
            key=lambda x: x.get("created_at", ""), reverse=True
        )
        print(f"\n=== Guest Outreach Status ===")
        print(f"Total pitches: {len(pitches)}")
        
        by_status = {}
        for p in pitches:
            s = p.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        
        for status, count in sorted(by_status.items()):
            print(f"  {status}: {count}")
        
        print(f"\nToday's sends: {get_today_send_count()} / {MAX_DAILY_SENDS}")
        
        if pitches:
            print(f"\nRecent pitches:")
            for p in pitches[:5]:
                print(f"  [{p.get('status','?')}] {p.get('article_proposal','no topic')}")
                print(f"           → {p.get('prospect_url','')[:50]}")
    else:
        check_and_process_approvals()
        
        if args.submit:
            if get_today_send_count() >= MAX_DAILY_SENDS:
                print(f"\n⚠️  Daily send limit ({MAX_DAILY_SENDS}) reached. Try again tomorrow.")
            else:
                remaining = MAX_DAILY_SENDS - get_today_send_count()
                print(f"\n📤 Submitting pitches for approval (max {remaining} today)...")
                submit_pending_pitches(max_pitches=remaining)