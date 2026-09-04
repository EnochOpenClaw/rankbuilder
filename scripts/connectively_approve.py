#!/usr/bin/env python3
"""
Connectively Approval Handler — Processes Craig's YES/SKIP/EDIT replies to Connectively approval emails.
On YES: logs in via Playwright and submits the answer via the web form.
On SKIP: marks as skipped in state.
On EDIT: submits the edited text.
"""

import sys
import json
import os
import subprocess
import re
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from credentials import (
    BREVO_API_KEY, BREVO_ENDPOINT,
    SENDER_EMAIL, SENDER_NAME,
    CONNECTIVELY_EMAIL, CONNECTIVELY_PASSWORD
)

# CRM integration
try:
    from lib.crm_client import get_or_create_lead, mark_lead_sent, CRMError as CRMErr
    CRM_AVAILABLE = True
except ImportError:
    CRM_AVAILABLE = False
    CRMErr = Exception

STATE_FILE = Path(__file__).parent / "state" / "processed_connectively.jsonl"
LOG_FILE = Path(__file__).parent / "logs" / "connectively_approvals.log"
LOG_FILE.parent.mkdir(exist_ok=True)

SCRIPT_FILE = Path("/tmp/connectively_pw.js")

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

def get_pending() -> list:
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


def get_all_entries() -> list:
    entries = []
    if not STATE_FILE.exists():
        return entries
    with open(STATE_FILE) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except:
                pass
    return entries


def save_entries(entries: list):
    with open(STATE_FILE, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def update_status(query_id: str, new_status: str):
    entries = get_all_entries()
    for entry in entries:
        if entry.get("query_id") == query_id:
            entry["status"] = new_status
            entry["updated_at"] = datetime.now().isoformat()
    save_entries(entries)


# ============================================================================
# PLAYWRIGHT — LOGIN + GET TOKEN
# ============================================================================

def playwright_login() -> dict:
    """Log in and return session token."""
    script = """
const { chromium } = require('/tmp/node_modules/playwright');
(async () => {
    const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto('https://www.connectively.us/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(3000);
    await page.locator('input[autocomplete="email"]').fill('EMAIL_PLACEHOLDER');
    await page.locator('input[autocomplete="current-password"]').fill('PASS_PLACEHOLDER');
    await page.locator('button[type="submit"]:has-text("Submit")').click();
    await page.waitForTimeout(5000);
    const cookies = await ctx.cookies();
    const token = (cookies.find(c => c.name.includes('session')) || { value: '' }).value;
    console.log(JSON.stringify({ token, url: page.url() }));
    await browser.close();
})().catch(e => { console.error('ERROR:' + e.message); process.exit(1); });
""".replace('EMAIL_PLACEHOLDER', CONNECTIVELY_EMAIL).replace('PASS_PLACEHOLDER', CONNECTIVELY_PASSWORD)

    SCRIPT_FILE.write_text(script)
    result = subprocess.run(
        ["node", str(SCRIPT_FILE)],
        capture_output=True, text=True, timeout=45, cwd="/tmp",
        env={**os.environ, "NODE_PATH": "/tmp/node_modules"}
    )
    try:
        lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
        if lines:
            return json.loads(lines[-1])
    except:
        pass
    return {"error": result.stdout[:300]}


# ============================================================================
# PLAYWRIGHT — SUBMIT ANSWER
# ============================================================================

def playwright_submit(question_url: str, answer_text: str, token: str) -> dict:
    """Submit an answer to a question page."""
    escaped_answer = answer_text.replace('`', '\\`').replace('${', '\\${')
    script = f"""
const {{ chromium }} = require('/tmp/node_modules/playwright');
(async () => {{
    const browser = await chromium.launch({{ headless: true, args: ['--no-sandbox'] }});
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    
    // Set auth cookie
    await ctx.addCookies([{{
        name: '__Secure-better-auth.session_token',
        value: '{token}',
        domain: '.connectively.us',
        path: '/',
        secure: true,
        httpOnly: true
    }}]);
    
    await page.goto('{question_url}', {{ waitUntil: 'domcontentloaded', timeout: 15000 }});
    await page.waitForTimeout(5000);
    
    // Check if already redirected to login
    if (page.url().includes('/login')) {{
        console.log(JSON.stringify({{ success: false, error: 'Session expired - need to re-login' }}));
        await browser.close();
        return;
    }}
    
    // Find and fill textarea
    const textarea = page.locator('textarea, [role="textbox"]').first();
    const count = await textarea.count();
    if (count === 0) {{
        console.log(JSON.stringify({{ success: false, error: 'No textarea found on page' }}));
        await browser.close();
        return;
    }}
    
    await textarea.fill(`{escaped_answer}`);
    
    // Click Submit (the main submit button, not draft/skip)
    const allBtns = await page.evaluate(() =>
        Array.from(document.querySelectorAll('button')).map(b => ({ t: b.textContent.trim(), type: b.type || 'button' }))
    );
    
    // Find Submit button (not "Save Draft" or "Skip")
    let submitBtn = null;
    for (const btn of allBtns) {{
        if (btn.t === 'Submit' && btn.type === 'submit') {{
            submitBtn = btn;
            break;
        }}
    }}
    
    if (!submitBtn) {{
        // Fallback: click last submit button
        await page.locator('button[type="submit"]').last().click();
    }} else {{
        await page.evaluate(() => {{
            const btns = Array.from(document.querySelectorAll('button'));
            const btn = btns.find(b => b.textContent.trim() === 'Submit' && b.type === 'submit');
            if (btn) btn.click();
        }});
    }}
    
    await page.waitForTimeout(4000);
    
    const resultText = await page.evaluate(() => document.body.innerText.substring(0, 300));
    console.log(JSON.stringify({{ success: true, url: page.url(), resultText }}));
    await browser.close();
}})().catch(e => {{ console.error('ERROR:' + e.message); process.exit(1); }});
"""

    SCRIPT_FILE.write_text(script)
    result = subprocess.run(
        ["node", str(SCRIPT_FILE)],
        capture_output=True, text=True, timeout=45, cwd="/tmp",
        env={**os.environ, "NODE_PATH": "/tmp/node_modules"}
    )

    try:
        lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
        if lines:
            return json.loads(lines[-1])
    except:
        pass
    return {"error": result.stdout[:300] + result.stderr[:200]}


# ============================================================================
# EMAIL SENDING (Brevo)
# ============================================================================

def send_email(to_email: str, subject: str, html_body: str, to_name: str = "Guest Post Editor") -> dict:
    payload = {
        "subject": subject,
        "to": [{"email": to_email, "name": to_name}],
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
            return {"success": True, "message_id": json.loads(resp.read().decode())["messageId"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_confirmation(to_email: str, action: str, query_id: str, details: str = ""):
    emoji = {"SUBMITTED": "✅", "SKIPPED": "⏭️", "ERROR": "❌"}.get(action, "📋")
    subject = f"{emoji} [Connectively] {action}: Query {query_id}"
    html = f"""
<!DOCTYPE html>
<html><body style="font-family: Arial; max-width: 600px; margin: 0 auto; padding: 20px;">
<h2>{emoji} Connectively Answer {action}</h2>
<p><strong>Query ID:</strong> {query_id}</p>
<p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
{details}
</body></html>"""
    send_email(to_email, subject, html)


# ============================================================================
# INBOX CHECK — get recent reply emails
# ============================================================================

def get_recent_emails(limit: int = 10) -> list:
    """Get recent emails from inbox via himalaya (v2 --json format)."""
    result = subprocess.run(
        ["himalaya", "envelope", "list", "--json"],
        capture_output=True, text=True, timeout=30
    )
    emails = []
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return emails
    for env in data.get("envelopes", []):
        if not isinstance(env, dict):
            continue
        id_ = str(env.get("id", "")).strip()
        if not id_.isdigit():
            continue
        from_list = env.get("from") or []
        sender = ""
        if from_list and isinstance(from_list, list) and isinstance(from_list[0], dict):
            sender = from_list[0].get("email", "") or from_list[0].get("name", "")
        emails.append({"id": id_, "subject": env.get("subject", "") or "", "sender": sender})
    return emails[:limit]


def read_email_body(email_id: str) -> str:
    """Read email body via himalaya."""
    result = subprocess.run(
        ["himalaya", "message", "read", email_id],
        capture_output=True, text=True, timeout=20
    )
    return result.stdout


def extract_reply_text(body: str) -> str:
    """Extract the non-quoted reply text from an email."""
    # Remove quoted lines (starting with >)
    lines = body.split('\n')
    reply_lines = []
    for line in lines:
        if line.startswith('>'):
            break
        reply_lines.append(line)
    text = '\n'.join(reply_lines).strip()
    # Remove email headers
    text = re.sub(r'^From:.*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^To:.*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^Subject:.*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^On.*wrote:.*', '', text, flags=re.MULTILINE)
    return text.strip()


# ============================================================================
# APPROVAL PROCESSING
# ============================================================================

def process_pending_approvals():
    """Check inbox for approval replies and process them."""
    log("=== Connectively Approval Check ===")

    pending = get_pending()
    if not pending:
        log("No pending approvals")
        return

    log(f"Found {len(pending)} pending approval(s)")

    # Get recent emails
    recent = get_recent_emails(15)
    log(f"Checking {len(recent)} recent emails...")

    for entry in pending:
        query_id = entry["query_id"]
        drafted = entry.get("drafted_response", "")
        answer_url = entry.get("answer_url", "")
        outlet = answer_url.split('/')[-3] if answer_url else "Unknown"  # e.g. 'forbescom'

        # Look for a reply email referencing this query
        matching_email = None
        for email in recent:
            subject = email["subject"].lower()
            # Check for approval keywords in subject
            if query_id.lower() in subject or "connectively" in subject:
                matching_email = email
                break

        if not matching_email:
            log(f"  [{query_id}] No reply found")
            continue

        log(f"  [{query_id}] Found potential reply: {matching_email['subject']}")

        # Read the email body
        body = read_email_body(matching_email["id"])
        reply_text = extract_reply_text(body).lower().strip()

        log(f"  [{query_id}] Reply text: {reply_text[:80]}")

        if not reply_text or len(reply_text) < 2:
            log(f"  [{query_id}] Empty reply, skipping")
            continue

        # Parse action
        if reply_text in ("yes", "send", "approve", "submit", "ok", "go", "do it"):
            action = "YES"
        elif reply_text in ("skip", "no", "cancel", "don't", "do not"):
            action = "SKIP"
        elif reply_text.startswith("edit ") or reply_text.startswith("revise ") or reply_text.startswith("but "):
            action = "EDIT"
            edited_text = reply_text[reply_text.index(' ') + 1:].strip()
        else:
            log(f"  [{query_id}] Unclear response: {reply_text[:50]}, skipping")
            continue

        log(f"  [{query_id}] Action: {action}")

        if action == "SKIP":
            update_status(query_id, "SKIPPED")
            send_confirmation(SENDER_EMAIL, "SKIPPED", query_id)
            log(f"  [{query_id}] ✅ Skipped")
            continue

        if action in ("YES", "EDIT"):
            answer_text = edited_text if action == "EDIT" else drafted
            if not answer_text or len(answer_text) < 20:
                log(f"  [{query_id}] No answer text to submit")
                continue

            # Submit via Playwright
            log(f"  [{query_id}] Submitting answer via Playwright...")
            submit_result = playwright_submit(answer_url, answer_text, "")

            # If session expired, re-login and retry
            if not submit_result.get("success") or "Session expired" in str(submit_result):
                log(f"  [{query_id}] Session expired, re-logging...")
                login_result = playwright_login()
                if login_result.get("token"):
                    submit_result = playwright_submit(answer_url, answer_text, login_result["token"])
                else:
                    log(f"  [{query_id}] Re-login failed")

            if submit_result.get("success"):
                update_status(query_id, "SUBMITTED")
                send_confirmation(
                    SENDER_EMAIL, "SUBMITTED", query_id,
                    f"<p>Submitted to: {answer_url}</p><p>URL after submit: {submit_result.get('url', 'N/A')}</p>"
                )
                log(f"  [{query_id}] ✅ Submitted! URL: {submit_result.get('url')}")

                # ── CRM: Create lead ────────────────────────────────────────
                if CRM_AVAILABLE:
                    try:
                        outlet_name = answer_url.split('/')[-3] if answer_url else "Connectively"
                        lead = get_or_create_lead(
                            source="CONNECTIVELY",
                            company_name=outlet_name.title(),
                            company_website=f"https://{outlet_name}.com" if outlet_name else None,
                            source_query=drafted[:200] or None,
                            message_excerpt=drafted[:500],
                            pitch_sent=drafted[:2000] or None,
                            quality_score=4,
                        )
                        mark_lead_sent(lead["id"], pitch_sent=drafted[:2000] or None)
                        log(f"  CRM: created lead {lead['id']} → SENT")
                    except CRMErr as e:
                        log(f"  CRM lead creation failed: {e}")

            else:
                update_status(query_id, "SUBMIT_ERROR")
                send_confirmation(
                    SENDER_EMAIL, "ERROR", query_id,
                    f"<p>Error: {submit_result.get('error', 'Unknown error')}</p>"
                )
                log(f"  [{query_id}] ❌ Submit failed: {submit_result.get('error')}")

    log("=== Approval Check Done ===")


# ============================================================================
# MANUAL APPROVE (for testing)
# ============================================================================

def manual_approve(query_id: str = None, edited_response: str = None, skip: bool = False):
    """Manually approve/skip a specific query by ID."""
    pending = get_pending()

    if not pending:
        log("No pending approvals")
        return

    if query_id:
        target = next((p for p in pending if p.get("query_id") == query_id), None)
        if not target:
            log(f"Query ID {query_id} not found in pending. Available:")
            for p in pending:
                log(f"  - {p['query_id']}")
            return
    else:
        target = pending[-1]  # Use most recent

    query_id = target["query_id"]
    drafted = target.get("drafted_response", "")
    answer_url = target.get("answer_url", "")
    answer_text = edited_response if edited_response else drafted

    if skip:
        update_status(query_id, "SKIPPED")
        send_confirmation(SENDER_EMAIL, "SKIPPED", query_id)
        log(f"✅ Skipped: {query_id}")
        return

    if not answer_text:
        log(f"No answer text for {query_id}")
        return

    log(f"Submitting answer for {query_id}...")
    result = playwright_submit(answer_url, answer_text, "")

    if not result.get("success") or "Session expired" in str(result):
        log("Re-logging...")
        login = playwright_login()
        if login.get("token"):
            result = playwright_submit(answer_url, answer_text, login["token"])

    if result.get("success"):
        update_status(query_id, "SUBMITTED")
        send_confirmation(SENDER_EMAIL, "SUBMITTED", query_id,
                         f"<p>Submitted to: {answer_url}</p>")
        log(f"✅ Submitted! URL: {result.get('url')}")

        # ── CRM: Create lead ───────────────────────────────────────────────
        if CRM_AVAILABLE:
            try:
                outlet = answer_url.split('/')[-3] if answer_url else "Connectively"
                lead = get_or_create_lead(
                    source="CONNECTIVELY",
                    company_name=outlet.title() if outlet else "Connectively",
                    company_website=f"https://{outlet}.com" if outlet else None,
                    source_query=answer_text[:200] if answer_text else None,
                    message_excerpt=answer_text[:500] if answer_text else None,
                    pitch_sent=answer_text[:2000] if answer_text else None,
                    quality_score=4,
                )
                mark_lead_sent(lead["id"], pitch_sent=answer_text[:2000] if answer_text else None)
                log(f"  CRM: created lead {lead['id']} → SENT")
            except CRMErr as e:
                log(f"  CRM lead creation failed: {e}")
    else:
        log(f"❌ Failed: {result.get('error')}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    if len(sys.argv) < 2:
        # List pending approvals
        pending = get_pending()
        print("\n=== Pending Connectively Approvals ===")
        if not pending:
            print("No pending approvals.")
        else:
            for p in pending:
                print(f"\nQuery ID: {p.get('query_id')}")
                print(f"Answer URL: {p.get('answer_url', 'N/A')}")
                print(f"Timestamp: {p.get('timestamp')}")
                draft = p.get('drafted_response', '')[:150]
                print(f"Draft preview: {draft}...")
        print()
        sys.exit(0)

    arg = sys.argv[1]

    if arg == "--check":
        # Run inbox check
        process_pending_approvals()
    elif arg == "--approve":
        # Manual approve: --approve [query_id] [edited_text]
        qid = sys.argv[2] if len(sys.argv) > 2 else None
        edited = sys.argv[3] if len(sys.argv) > 3 else None
        manual_approve(qid, edited)
    elif arg == "--skip":
        # Manual skip: --skip [query_id]
        qid = sys.argv[2] if len(sys.argv) > 2 else None
        manual_approve(qid, skip=True)
    elif arg == "--login":
        # Test login
        result = playwright_login()
        print("Login result:", result)
    else:
        print(f"Unknown: {arg}")
        print("Usage: connectively_approve.py [--check|--approve [qid] [--skip [qid]|--login]")


if __name__ == "__main__":
    main()