#!/usr/bin/env python3
"""
End-to-end test of the HARO and Connectively approval → CRM flow.
Mocks Brevo email sending and CRM API calls, verifies NameErrors are gone.
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# ── Mock Brevo email sending ────────────────────────────────────────────────
_mock_emails_sent = []

def _mock_urlopen(req, timeout=None):
    body = json.dumps({"messageId": "TEST_MSG_ID_123"}).encode()
    class FakeResp:
        def read(self): return body
        def __enter__(self): return self
        def __exit__(self, *a): pass
    _mock_emails_sent.append(req)
    return FakeResp()

# ── Mock CRM calls ──────────────────────────────────────────────────────────
_crm_calls = []

def _mock_get_or_create_lead(**kwargs):
    _crm_calls.append(("get_or_create_lead", kwargs))
    return {"id": "LEAD_999", **kwargs}

def _mock_mark_lead_sent(lead_id, **kwargs):
    _crm_calls.append(("mark_lead_sent", lead_id, kwargs))
    return {"id": lead_id, "status": "SENT"}

# ── Helpers ──────────────────────────────────────────────────────────────────
STATE_FILE = Path(__file__).parent / "state" / "processed.jsonl"
DRAFTS_DIR  = Path(__file__).parent / "state" / "drafts"
DRAFTS_DIR.mkdir(exist_ok=True)

def _backup_state():
    return (
        STATE_FILE.read_text() if STATE_FILE.exists() else "",
        list(DRAFTS_DIR.glob("HARO_TEST_*"))
    )

def _restore_state(backup):
    text, drafts = backup
    STATE_FILE.write_text(text)
    for d in drafts:
        d.unlink(missing_ok=True)

# ── Test 1: HARO Approval ──────────────────────────────────────────────────
print("=" * 60)
print("TEST 1: HARO Approval — process_approval('yes', ...)")
print("=" * 60)

orig = _backup_state()

fake_email_id = "HARO_TEST_001"
fake_entry = {
    "email_id": fake_email_id,
    "status": "AWAITING_APPROVAL",
    "reply_to": "jane@SA3news.com",
    "outlet": "SA3 News",
    "query_text": "What are the best home security window solutions?",
    "timestamp": "2026-08-04T08:00:00"
}
STATE_FILE.write_text(json.dumps(fake_entry) + "\n")
(DRAFTS_DIR / f"{fake_email_id}.txt").write_text(
    "URGENT: Aluminium Shutters for Home Security\n\nI recommend Fortress Blinds...")

_mock_emails_sent.clear()
_crm_calls.clear()

with patch("urllib.request.urlopen", _mock_urlopen):
    with patch("haro_approve.get_or_create_lead", _mock_get_or_create_lead):
        with patch("haro_approve.mark_lead_sent", _mock_mark_lead_sent):
            with patch("haro_approve.n8n_event", lambda *a, **kw: None):
                from haro_approve import process_approval
                result = process_approval("yes", fake_email_id)

print(f"Result: {result}")
print(f"Emails sent: {len(_mock_emails_sent)}, CRM calls: {len(_crm_calls)}")

haro_ok = (
    result.get("action") == "SENT"
    and len(_crm_calls) >= 2
    and any(call[0] == "get_or_create_lead" and call[1].get("source") == "HARO"
             for call in _crm_calls)
)
print(f"{'✅' if haro_ok else '❌'} HARO CRM lead created: {haro_ok}")
if not haro_ok:
    print(f"  CRM calls: {_crm_calls}")
_restore_state(orig)
if not haro_ok:
    sys.exit(1)
print()

# ── Test 2: HARO SKIP ───────────────────────────────────────────────────────
print("=" * 60)
print("TEST 2: HARO Skip — process_approval('skip', ...)")
print("=" * 60)

orig = _backup_state()

fake_email_id2 = "HARO_TEST_002"
fake_entry2 = {
    "email_id": fake_email_id2,
    "status": "AWAITING_APPROVAL",
    "reply_to": "reporter@example.com",
    "outlet": "Test Outlet",
    "query_text": "Test query",
    "timestamp": "2026-08-04T08:01:00"
}
STATE_FILE.write_text(json.dumps(fake_entry2) + "\n")
(DRAFTS_DIR / f"{fake_email_id2}.txt").write_text("Some drafted pitch")
_mock_emails_sent.clear()
_crm_calls.clear()

with patch("urllib.request.urlopen", _mock_urlopen):
    with patch("haro_approve.n8n_event", lambda *a, **kw: None):
        from haro_approve import process_approval
        result2 = process_approval("skip", fake_email_id2)

print(f"Result: {result2}")
skip_ok = result2.get("action") == "SKIPPED" and len(_crm_calls) == 0
print(f"{'✅' if skip_ok else '❌'} HARO skip (no CRM call): {skip_ok}")
_restore_state(orig)
if not skip_ok:
    sys.exit(1)
print()

# ── Test 3: Connectively Approval ───────────────────────────────────────────
print("=" * 60)
print("TEST 3: Connectively Approval — process_pending_approvals()")
print("=" * 60)

CSTATE = Path(__file__).parent / "state" / "processed_connectively.jsonl"
cbackup = CSTATE.read_text() if CSTATE.exists() else ""

fake_qid = "CONN_TEST_001"
fake_conn_entry = {
    "query_id": fake_qid,
    "status": "AWAITING_APPROVAL",
    "drafted_response": "Aluminium shutters provide excellent home security...",
    "answer_url": "https://www.forbes.com/answer/12345",
    "outlet": "forbes",
    "timestamp": "2026-08-04T08:00:00"
}
CSTATE.write_text(json.dumps(fake_conn_entry) + "\n")
_mock_emails_sent.clear()
_crm_calls.clear()

with patch("urllib.request.urlopen", _mock_urlopen):
    with patch("connectively_approve.playwright_submit",
               return_value={"success": True, "url": "https://www.forbes.com/answer/12345"}):
        with patch("connectively_approve.playwright_login",
                   return_value={"token": "FAKE_TOKEN"}):
            with patch("connectively_approve.get_recent_emails",
                       return_value=[{"subject": f"YES {fake_qid}",
                                     "body": "yes", "id": "EMAIL_123"}]):
                with patch("connectively_approve.read_email_body",
                           return_value="yes"):
                    with patch("connectively_approve.get_or_create_lead",
                               _mock_get_or_create_lead):
                        with patch("connectively_approve.mark_lead_sent",
                                   _mock_mark_lead_sent):
                            from connectively_approve import process_pending_approvals
                            try:
                                process_pending_approvals()
                            except NameError as e:
                                print(f"❌ NameError raised: {e}")
                                CSTATE.write_text(cbackup)
                                sys.exit(1)

print(f"CRM calls: {len(_crm_calls)}")
conn_ok = any(
    call[0] == "get_or_create_lead" and call[1].get("source") == "CONNECTIVELY"
    for call in _crm_calls
)
print(f"{'✅' if conn_ok else '❌'} Connectively CRM lead created: {conn_ok}")
if not conn_ok:
    print(f"  CRM calls: {_crm_calls}")
    CSTATE.write_text(cbackup)
    sys.exit(1)

CSTATE.write_text(cbackup)
print()

# ── Summary ─────────────────────────────────────────────────────────────────
print("=" * 60)
print("ALL TESTS PASSED ✅")
print("=" * 60)
print("  HARO approval  → CRM lead created:  ✅")
print("  HARO skip      → no CRM call:       ✅")
print("  Connectively   → CRM lead created:  ✅")
print("\nNameError bugs confirmed fixed. CRM integration verified.")
