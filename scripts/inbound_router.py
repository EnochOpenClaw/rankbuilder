#!/usr/bin/env python3
"""
RankBuilder Inbound Router — Unified inbound lead monitor + router.

Watches the subscriber inbox (info@fortressblinds.co.za, primary) and the
forwarded-email inbox (agentdevelopmentops@gmail.com, secondary) for inbound
requests, classifies each into a route, and handles it:

  ROUTE A — SALES leads (quote requests, direct enquiries)
      → Create CRM lead (source: WEBSITE/CALL_IN/etc), notify Tiaan.
      → Fast auto-response.

  ROUTE B — BLOG / BACKLINK requests (bylined article requests, guest posts,
            backlink/contribute requests)
      → Auto-generate proposal (with humanization)
      → Post/submit the proposal to the requesting party
      → Create CRM lead assigned to Craig, record what+who in notes
      → Notify Craig.

Channels detected:
  - HARO query emails (helpareporter.com format)
  - Connectively alerts (Q&A + Bylined Article requests, magic-link format)
  - Direct guest-post/backlink/contribute emails

Run: python inbound_router.py [--dry-run] [--account info|agentdev|all]
"""

import sys
import json
import re
import os
import warnings
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Optional

warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / 'lib'))
sys.path.insert(0, str(Path(__file__).parent))

from haro_responder import read_email, extract_forwarded_haro_content, humanize_draft
from blocklist import is_blocked, is_buyer
from credentials import BREVO_API_KEY, BREVO_ENDPOINT, SENDER_EMAIL, SENDER_NAME

# CRM integration
try:
    from lib.crm_client import get_or_create_lead, update_lead, CRMError as CRMErr
    CRM_AVAILABLE = True
except ImportError:
    CRM_AVAILABLE = False
    CRMErr = Exception

# ── Config ─────────────────────────────────────────────────────────────────────
PRIMARY_ACCOUNT = "info"       # info@fortressblinds.co.za (subscriber inbox)
SECONDARY_ACCOUNT = "agentdev" # agentdevelopmentops@gmail.com (forwards)
DEFAULT_ACCOUNTS = ["info", "agentdev"]

# IMAP credentials for direct Gmail access (fallback when himalaya is not
# installed, e.g. on the VPS). Keyed by account name.
# app passwords:
#   info      — zpwzuioojiatdxsu
#   agentdev  — uefvxqfsmpquasky
IMAP_ACCOUNTS = {
    "info": {
        "host": "imap.gmail.com", "port": 993,
        "login": "info@fortressblinds.co.za", "password": "zpwzuioojiatdxsu",
    },
    "agentdev": {
        "host": "imap.gmail.com", "port": 993,
        "login": "agentdevelopmentops@gmail.com", "password": "uefvxqfsmpquasky",
    },
    "enoch": {
        "host": "imap.gmail.com", "port": 993,
        "login": "enoch@fortressblinds.co.za", "password": "dmdl epoy afdf zjmo".replace(" ", ""),
    },
}

# Prefer himalaya if available, else use IMAP fallback
import shutil
USE_HIMALAYA = shutil.which("himalaya") is not None

STATE_FILE = Path(__file__).parent / "state" / "processed_inbound.jsonl"
STATE_FILE.parent.mkdir(exist_ok=True)
LOG_FILE = Path(__file__).parent / "logs" / "inbound_router.log"

DRY_RUN = False  # set in main()

# Assignment targets
SALES_NOTIFY_EMAIL = "tiaan@houseofsupreme.co.za"
CRAIG_EMAIL = "craig@fortressblinds.co.za"

# Classification keywords
SALES_KEYWORDS = [
    "quote", "quotation", "price", "cost", "estimate", "install", "installation",
    "buy", "purchase", "order", "shutter", "flyscreen", "blind", "security screen",
    "windows", "doors", "how much", "supply", "measure", "survey", "book",
]
BLOG_KEYWORDS = [
    "guest post", "guestpost", "write for us", "contribute", "backlink",
    "bylined article", "byline", "guest article", "sponsored post", "link building",
    "guest blog", "submit an article", "article request", "expert article",
    "do-follow", "do follow", "guest author",
]


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

def _is_processed(msg_id: str) -> bool:
    if not STATE_FILE.exists():
        return False
    try:
        for line in STATE_FILE.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("msg_id") == msg_id:
                return True
    except Exception:
        pass
    return False


def _mark_processed(msg_id: str, msg_type: str, route: str, detail: str = ""):
    if DRY_RUN:
        return  # dry-run must not mutate state
    with open(STATE_FILE, "a") as f:
        f.write(json.dumps({
            "msg_id": msg_id,
            "type": msg_type,
            "route": route,
            "detail": detail,
            "processed_at": datetime.utcnow().isoformat(),
        }) + "\n")


def read_email_from_account(email_id: str, account: str) -> str:
    """Read a full email body from a specific account (himalaya or IMAP)."""
    if USE_HIMALAYA:
        try:
            result = subprocess.run(
                ["himalaya", "message", "read", "-a", account, email_id],
                capture_output=True, text=True, timeout=30,
            )
            return result.stdout if result.returncode == 0 else ""
        except Exception as e:
            log(f"  ERROR reading email via himalaya {email_id}: {e}")
            return ""
    # IMAP fallback
    try:
        import imaplib
        import email as email_lib
        from email.header import decode_header
        cfg = IMAP_ACCOUNTS.get(account)
        if not cfg:
            return ""
        mail = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
        mail.login(cfg["login"], cfg["password"])
        mail.select("INBOX")
        # Gmail UID is the numeric part
        uid = email_id
        status, data = mail.fetch(uid, "(RFC822)")
        mail.logout()
        if status != "OK" or not data or not data[0]:
            return ""
        msg = email_lib.message_from_bytes(data[0][1])
        # Build a plain-text representation
        parts = []
        if msg["From"]:
            parts.append(f"From: {msg['From']}")
        if msg["Subject"]:
            try:
                decoded = decode_header(msg["Subject"])
                subject = "".join(
                    part.decode(ch or "utf-8", errors="replace") if isinstance(part, bytes) else part
                    for part, ch in decoded
                )
            except Exception:
                subject = str(msg["Subject"])
            parts.append(f"Subject: {subject}")
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and not part.get("Content-Disposition") == "attachment":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            parts.append(payload.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                parts.append(payload.decode("utf-8", errors="replace"))
        return "\n".join(parts)
    except Exception as e:
        log(f"  ERROR reading email via IMAP {email_id}: {e}")
        return ""


# ============================================================================
# INBOX READING (himalaya or IMAP)
# ============================================================================

def get_inbox_envelopes(account: str, limit: int = 20) -> list:
    """Get recent envelope metadata from an account (himalaya or IMAP)."""
    if USE_HIMALAYA:
        return _get_envelopes_himalaya(account, limit)
    return _get_envelopes_imap(account, limit)


def _get_envelopes_himalaya(account: str, limit: int = 20) -> list:
    """Get recent envelope metadata via himalaya CLI."""
    try:
        result = subprocess.run(
            ["himalaya", "envelope", "list", "-a", account, "-s", str(limit)],
            capture_output=True, text=True, timeout=30,
        )
        envelopes = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if not line.startswith('|') or '---' in line or 'WARN' in line:
                continue
            if '+00:00' not in line and not re.search(r'[+-]\d{2}:\d{2}', line):
                continue
            # Parse: | ID | FLAGS | SUBJECT | FROM | DATE |
            parts = [p.strip() for p in line.strip('|').split('|')]
            if len(parts) < 5:
                continue
            envelopes.append({
                "id": parts[0],
                "flags": parts[1],
                "subject": parts[2],
                "from": parts[3],
                "date": parts[4],
            })
        return envelopes
    except Exception as e:
        log(f"  ERROR reading {account} inbox: {e}")
        return []


def _get_envelopes_imap(account: str, limit: int = 20) -> list:
    """Get recent envelope metadata via IMAP (stdlib imaplib) — VPS fallback."""
    try:
        import imaplib
        import email as email_lib
        from email.header import decode_header
        cfg = IMAP_ACCOUNTS.get(account)
        if not cfg:
            log(f"  No IMAP config for account {account}")
            return []
        mail = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
        mail.login(cfg["login"], cfg["password"])
        mail.select("INBOX")
        status, data = mail.search(None, "ALL")
        envelopes = []
        if status == "OK":
            ids = data[0].split()
            # Take the most recent `limit`
            recent = ids[-limit:]
            for uid in recent:
                uid_str = uid.decode()
                fstatus, fdata = mail.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if fstatus != "OK" or not fdata or not fdata[0]:
                    continue
                raw = fdata[0][1].decode("utf-8", errors="replace")
                msg = email_lib.message_from_string(raw)
                def _decode(val):
                    if not val:
                        return ""
                    try:
                        parts = decode_header(val)
                        return "".join(
                            p.decode(c or "utf-8", errors="replace") if isinstance(p, bytes) else p
                            for p, c in parts
                        )
                    except Exception:
                        return str(val)
                envelopes.append({
                    "id": uid_str,
                    "flags": "",
                    "subject": _decode(msg["Subject"]),
                    "from": _decode(msg["From"]),
                    "date": _decode(msg["Date"]),
                })
        mail.logout()
        return envelopes
    except Exception as e:
        log(f"  ERROR reading {account} inbox via IMAP: {e}")
        return []


def extract_connectively_content(body: str) -> Optional[dict]:
    """
    Extract Connectively query/request from an email body.
    Handles Q&A Alerts and Bylined Article Alerts.
    Returns dict with: type (qa|bylined), outlet, query_text, deadline, reply_to
    """
    if 'connectively.us' not in body.lower() and 'Connectively' not in body:
        return None

    data = {}
    lower = body.lower()

    # Detect bylined article request vs Q&A
    if 'bylined article' in lower:
        data['type'] = 'bylined'
    else:
        data['type'] = 'qa'

    # Outlet — first company/brand name near "New query from" or "alerts"
    outlet_match = re.search(r'[Nn]ew query from\s+([A-Za-z0-9 &]+?)[:.]', body)
    if outlet_match:
        data['outlet'] = outlet_match.group(1).strip()
    else:
        outlet_match = re.search(r'[Ff]avicon for\s+([A-Za-z0-9 &]+)', body)
        if outlet_match:
            data['outlet'] = outlet_match.group(1).strip()

    # Query text — first substantial paragraph
    # Find text after the alert headers
    qa_match = re.search(r'(?:Q&A Alerts|shutters|Questions matching)[^\n]*\n(.+?)(?:\n\[|https://connectively)', body, re.DOTALL)
    if qa_match:
        data['query_text'] = qa_match.group(1).strip()[:2000]

    # Deadline
    deadline_match = re.search(r'[Aa]nswer by\s+([A-Za-z0-9 ,]+)', body)
    if deadline_match:
        data['deadline'] = deadline_match.group(1).strip()

    # Reply/magic link
    link_match = re.search(r'(https://connectively\.us/api/auth/magic-link/verify\?token=[^\s>]+)', body)
    if link_match:
        data['reply_url'] = link_match.group(1).strip()

    # Only return if we found real query/request content — not just the word
    # "Connectively" (avoids false positives on system/error emails)
    has_content = bool(data.get('query_text')) or (
        data.get('type') == 'bylined' and bool(re.search(r'bylined|article|guest|pitch', lower))
    )
    if has_content:
        return data
    return None


def extract_blog_request(body: str, subject: str = "") -> dict:
    """
    Detect a blog/backlink request in an email.
    Returns dict with: is_blog (bool), requested_topic, requesting_site, notes
    """
    text = (subject + "\n" + body).lower()
    result = {"is_blog": False}

    for kw in BLOG_KEYWORDS:
        if kw in text:
            result["is_blog"] = True
            result["matched_keyword"] = kw
            break

    # Extract requesting site/email
    from_match = re.search(r'[Ff]rom:\s*([^\n]+)', body)
    if from_match:
        result["requesting_party"] = from_match.group(1).strip()[:200]

    # Extract a hint of the requested topic (first sentence of body)
    if result["is_blog"]:
        # Find a line with substantive content
        for line in body.split('\n'):
            line = line.strip()
            if len(line) > 40 and not line.startswith('[') and not line.startswith('#'):
                result["requested_topic"] = line[:300]
                break

    return result


# Senders/emails to skip entirely (not leads — system/billing/notifications)
SKIP_SENDERS = [
    "google.com", "googlecloud", "microsoft.com", "github.com", "asana.com",
    "notifications", "noreply", "no-reply", "youtube.com", "linkedin.com",
    "lovable", "canva", "cloudflare", "openai", "anthropic", "stripe.com",
]

# STRONG sales-intent keywords — need 1+ of these (specific buying intent)
STRONG_SALES_KEYWORDS = [
    "quote", "quotation", "price for", "estimate", "cost to install",
    "install a shutter", "install shutters", "flyscreen install", "blind install",
    "how much to install", "book a measurement", "book a survey",
    "supply and install", "get a quote", "request a quote", "need a quote",
]


def is_skip_email(subject: str = "", from_addr: str = "") -> bool:
    """Return True if the email is a known non-lead sender/system message."""
    text = (subject + " " + from_addr).lower()
    for s in SKIP_SENDERS:
        if s in text:
            return True
    return False


def is_sales_request(body: str, subject: str = "", from_addr: str = "") -> bool:
    """
    Determine if a request is a genuine SALES lead (quote/enquiry).
    Requires strong sales intent — not just any keyword match.
    """
    if is_skip_email(subject, from_addr):
        return False
    text = (subject + "\n" + body).lower()

    blog_hits = sum(1 for kw in BLOG_KEYWORDS if kw in text)
    # Strong sales intent — specific buying words
    strong_hits = sum(1 for kw in STRONG_SALES_KEYWORDS if kw in text)
    # Weaker product-word hits (shutter/flyscreen/blind/install)
    weak_hits = sum(1 for kw in SALES_KEYWORDS if kw in text)

    # Blog/backlink takes priority when clearly flagged
    if blog_hits > 0 and strong_hits == 0:
        return False

    # Genuine sales: strong buying intent, OR product mention + contact-ish context
    if strong_hits > 0:
        return True
    if weak_hits >= 2:
        return True

    return False


# ============================================================================
# CRM LEAD CREATION (with assignment)
# ============================================================================

def create_crm_lead(source: str, route: str, lead_data: dict, assigned_user: str) -> Optional[str]:
    """Create a lead in the CRM. Returns lead id or None."""
    if not CRM_AVAILABLE:
        log("  ⚠️ CRM not available — skipping lead creation")
        return None
    try:
        lead = get_or_create_lead(
            client_id="e74119b9-17e3-4f74-b218-67ef0e66f1cc",  # HOS
            source=source,
            contact_email=lead_data.get("contact_email"),
            company_name=lead_data.get("company_name"),
            contact_name=lead_data.get("contact_name"),
            company_website=lead_data.get("company_website"),
            message_excerpt=lead_data.get("message_excerpt"),
            source_query=lead_data.get("source_query"),
            quality_score=lead_data.get("quality_score", 3),
            notes=lead_data.get("notes"),
        )
        log(f"  CRM: created/updated lead {lead.get('id','?')[:8]} (assigned: {assigned_user})")
        return lead.get("id")
    except CRMErr as e:
        log(f"  CRM lead creation failed: {e}")
        return None


# ============================================================================
# EMAIL SEND (Brevo)
# ============================================================================

def _brevo_send(to_email: str, subject: str, html_body: str, to_name: str = "",
                sender_email: str = None, sender_name: str = None) -> dict:
    """Send email via Brevo."""
    sender_email = sender_email or SENDER_EMAIL
    sender_name = sender_name or SENDER_NAME
    payload = {
        "subject": subject,
        "to": [{"email": to_email, "name": to_name}] if to_name else [{"email": to_email}],
        "htmlContent": html_body,
        "sender": {"name": sender_name, "email": sender_email},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BREVO_ENDPOINT, data=data,
        headers={"Content-Type": "application/json", "api-key": BREVO_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return {"success": True, "message_id": result.get("messageId", "")}
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def notify_craig(route: str, company: str, detail: str, lead_id: str = None) -> dict:
    """Notify Craig of a handled inbound request."""
    subject = f"📥 [Inbound] {route}: {company}"
    body = f"""
<p>A new inbound request was auto-handled by the router:</p>
<p><strong>Route:</strong> {route}</p>
<p><strong>Company/Source:</strong> {company}</p>
<p><strong>Detail:</strong> {detail}</p>
{f"<p><strong>CRM Lead:</strong> <a href='https://dashboard.fortressblinds.co.za'>View in portal</a></p>" if lead_id else ""}
"""
    return _brevo_send(CRAIG_EMAIL, subject, body, sender_email=SENDER_EMAIL)


# ============================================================================
# ROUTE HANDLING
# ============================================================================

def handle_blog_request(req: dict, msg_id: str) -> None:
    """Route B — blog/backlink: auto-propose (humanized), create lead, notify Craig."""
    log(f"  → ROUTE B (BLOG/BACKLINK): {req.get('requesting_party','?')}")

    # 1. Draft a proposal response (humanized)
    topic = req.get("requested_topic") or "your requested topic"
    proposal = (
        f"Hi there,\n\n"
        f"Thank you for reaching out about contributing to {req.get('requesting_party','your publication')}.\n\n"
        f"Fortress Blinds (fortressblinds.co.za) would be glad to provide a guest article. "
        f"We specialise in custom aluminium shutters, security screens, flyscreen doors and "
        f"outdoor blinds for South African homes, with 25+ years of hands-on industry expertise. "
        f"Our founder Craig Pauls writes practical, no-nonsense content for homeowners, architects "
        f"and developers.\n\n"
        f"Regarding '{topic}', here are a few angles we can cover:\n"
        f"  • Security shutters vs. traditional burglar bars: what actually protects your home\n"
        f"  • The rise of aluminium flyscreen doors in modern SA home design\n"
        f"  • How outdoor blinds cut cooling costs and extend your living space\n\n"
        f"We can deliver an original, publish-ready article. Happy to provide it as a guest post "
        f"with a link back to fortressblinds.co.za.\n\n"
        f"Let me know if any of these angles fit your audience.\n\n"
        f"Best regards,\nCraig Pauls\nFortress Blinds"
    )

    # Humanize the proposal
    try:
        human = humanize_draft(proposal, level="formal")
        proposal = human.get("text", proposal)
        log(f"  Humanized proposal (score {human.get('scores',{}).get('final',{}).get('human_score','?')})")
    except Exception as e:
        log(f"  Humanize failed (using base draft): {e}")

    # 2. Record what was proposed + to who (for CRM note)
    notes = (f"AUTO-PROPOSED to {req.get('requesting_party','?')}. "
             f"Topic: {req.get('requested_topic','?')}. "
             f"Proposal posted automatically. Assigned to Craig for follow-up. "
             f"Proposal snippet: {proposal[:300]}")

    # 3. Create CRM lead assigned to Craig (route = blog/backlink)
    lead_id = create_crm_lead(
        source="GUEST_OUTREACH",
        route="BLOG",
        lead_data={
            "company_name": req.get("requesting_party") or "Blog Request",
            "contact_email": req.get("reply_to"),
            "message_excerpt": req.get("requested_topic") or "",
            "source_query": f"Blog/backlink request: {req.get('matched_keyword','')}",
            "notes": notes,
            "quality_score": 3,
        },
        assigned_user="Craig",
    )

    # 4. Notify Craig
    notify_craig("BLOG/BACKLINK", req.get("requesting_party","?"), notes, lead_id)

    # 5. Optionally send the proposal back to the requester (post it)
    if req.get("reply_to") and req.get("auto_post", True):
        send_result = _brevo_send(
            req["reply_to"],
            f"Re: Guest article contribution — {req.get('requesting_party','')}",
            f"<pre style='white-space:pre-wrap;font-family:Arial,sans-serif;'>{proposal}</pre>",
            sender_email=SENDER_EMAIL,
        )
        log(f"  Proposal posted to requester: {'OK' if send_result.get('success') else send_result.get('error')}")

    _mark_processed(msg_id, "blog", "BLOG", req.get("requesting_party",""))


def handle_sales_request(req: dict, msg_id: str) -> None:
    """Route A — sales: create lead (routed to Tiaan by CRM), notify."""
    log(f"  → ROUTE A (SALES): {req.get('company_name','?')}")
    lead_id = create_crm_lead(
        source="WEBSITE",
        route="SALES",
        lead_data={
            "company_name": req.get("company_name"),
            "contact_email": req.get("contact_email"),
            "contact_name": req.get("contact_name"),
            "message_excerpt": req.get("message_excerpt"),
            "source_query": req.get("source_query"),
            "notes": req.get("notes"),
            "quality_score": req.get("quality_score", 4),
        },
        assigned_user="Tiaan",
    )
    # CRM routing notification fires automatically (leads.py → notify_new_lead → Tiaan)
    _mark_processed(msg_id, "sales", "SALES", req.get("company_name",""))


# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_account(account: str):
    """Scan one inbox and route new inbound messages."""
    log(f"=== Scanning {account} inbox ===")
    envelopes = get_inbox_envelopes(account)
    if not envelopes:
        log("  No envelopes")
        return

    processed_any = False
    for env in envelopes:
        msg_id = f"{account}:{env['id']}"
        if _is_processed(msg_id):
            continue

        subject = env.get("subject", "")
        from_addr = env.get("from", "")
        # Skip obvious non-request emails
        lower_subj = subject.lower()
        if any(skip in lower_subj for skip in [
            "security alert", "2-step", "welcome to", "verify your", "boost productivity",
            "your sign up link", "google workspace team", "electronic signatures",
            "gemini in gmail", "booking pages", "invited you", "access to their gmail",
            "kasada bypass", "bypass not configured", "account does not exist",
            "deployment not found", "script error", "cron", "health check",
        ]):
            continue
        if is_skip_email(subject, from_addr):
            continue

        # Read the body
        try:
            body = read_email_from_account(env["id"], account)
        except Exception as e:
            log(f"  ERROR reading {msg_id}: {e}")
            continue

        # 1. HARO format — defer to the existing HARO monitor (haro_monitor.py
        #    handles relevance filtering + Craig approval + submission).
        #    The router just marks it processed so it doesn't re-scan it.
        haro = extract_forwarded_haro_content(body)
        if haro:
            log(f"  [{msg_id}] HARO query detected (deferred to HARO monitor): {haro.get('summary','')[:60]}")
            _mark_processed(msg_id, "haro", "DEFERRED", "Handled by haro_monitor.py")
            processed_any = True
            continue

        # 2. Connectively format
        conn = extract_connectively_content(body)
        if conn:
            log(f"  [{msg_id}] Connectively {conn.get('type','?')} detected: {conn.get('outlet','?')}")
            if DRY_RUN:
                log(f"    (dry-run) would route Connectively {conn.get('type')}")
            elif conn.get("type") == "bylined":
                # Bylined article = blog/backlink route
                handle_blog_request({
                    "requesting_party": conn.get("outlet") or "Connectively outlet",
                    "requested_topic": conn.get("query_text","")[:300],
                    "reply_to": conn.get("reply_url"),
                    "auto_post": False,  # Connectively needs web submission, not email reply
                }, msg_id)
            else:
                handle_sales_request({
                    "company_name": conn.get("outlet") or "Connectively Query",
                    "contact_email": conn.get("reply_url"),
                    "message_excerpt": conn.get("query_text"),
                    "source_query": conn.get("query_text","")[:200],
                }, msg_id)
            processed_any = True
            continue

        # 3. Blog/backlink direct request
        blog_req = extract_blog_request(body, subject)
        if blog_req.get("is_blog"):
            log(f"  [{msg_id}] Blog/backlink request: {blog_req.get('requesting_party','?')}")
            if DRY_RUN:
                log(f"    (dry-run) would route blog request")
            else:
                handle_blog_request(blog_req, msg_id)
            processed_any = True
            continue

        # 4. Sales/quote request
        if is_sales_request(body, subject, from_addr):
            log(f"  [{msg_id}] Sales/enquiry request")
            if DRY_RUN:
                log(f"    (dry-run) would route sales enquiry")
            else:
                handle_sales_request({
                    "company_name": env.get("from","?"),
                    "contact_email": None,
                    "message_excerpt": body[:500],
                }, msg_id)
            processed_any = True
            continue

    if not processed_any:
        log(f"  No new actionable messages in {account}")


def main():
    global DRY_RUN
    DRY_RUN = "--dry-run" in sys.argv
    accounts = DEFAULT_ACCOUNTS

    # Allow account override: --account info|agentdev|all
    if "--account" in sys.argv:
        idx = sys.argv.index("--account")
        if idx + 1 < len(sys.argv):
            val = sys.argv[idx + 1]
            accounts = ["info", "agentdev"] if val == "all" else [val]

    mode = "DRY-RUN" if DRY_RUN else "LIVE"
    log(f"=== Inbound Router [{mode}] — accounts: {accounts} ===")
    for acct in accounts:
        try:
            process_account(acct)
        except Exception as e:
            log(f"  ERROR processing {acct}: {e}")
    log("=== Inbound Router complete ===\n")


if __name__ == "__main__":
    main()
