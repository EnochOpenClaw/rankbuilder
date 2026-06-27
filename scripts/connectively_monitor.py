#!/usr/bin/env python3
"""
Connectively HARO Monitor — Full automation for Connectively HARO queries.
- Logs in via Playwright (headless Chromium)
- Scrapes HARO questions from expert-questions page
- Gets full query text from each question page
- Filters by keyword relevance
- Drafts responses via kimi-k2.6:cloud
- Sends approval email to Craig via Brevo
- On YES: submits answer via Playwright
- On SKIP: marks as skipped
- On EDIT: submits edited version
"""

import sys
import json
import re
import os
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from haro_responder import (
    BRAND_BIO, BRAND_VOICE,
    TARGET_KEYWORDS, EXCLUDED_KEYWORDS,
    is_relevant_query, score_relevance
)
from pitch_templates import select_angle, get_angle_for_query, get_angle_guidance, build_pitch_response
from credentials import (
    BREVO_API_KEY, BREVO_ENDPOINT,
    SENDER_EMAIL, SENDER_NAME, NOTIFY_EMAIL,
    CONNECTIVELY_EMAIL, CONNECTIVELY_PASSWORD
)
from blocklist import is_blocked, block_email

STATE_FILE = Path(__file__).parent / "state" / "processed_connectively.jsonl"
STATE_FILE.parent.mkdir(exist_ok=True)

LOG_FILE = Path(__file__).parent / "logs" / "connectively_monitor.log"
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
# STATE TRACKING
# ============================================================================

def is_processed(query_id: str) -> bool:
    if not STATE_FILE.exists():
        return False
    with open(STATE_FILE) as f:
        for line in f:
            try:
                if json.loads(line).get("query_id") == query_id:
                    return True
            except:
                pass
    return False


def mark_processed(query_id: str, status: str, drafted: str = "", submission_url: str = "", answer_url: str = ""):
    with open(STATE_FILE, "a") as f:
        f.write(json.dumps({
            "query_id": query_id,
            "status": status,
            "drafted_response": drafted,
            "submission_url": submission_url,
            "answer_url": answer_url,
            "timestamp": datetime.now().isoformat()
        }) + "\n")


def get_draft(query_id: str) -> str:
    """Get drafted response for a query."""
    if not STATE_FILE.exists():
        return ""
    with open(STATE_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("query_id") == query_id:
                    return entry.get("drafted_response", "")
            except:
                pass
    return ""


# ============================================================================
# EMAIL SENDING (Brevo)
# ============================================================================

def send_email(to_email: str, subject: str, html_body: str) -> dict:
    payload = {
        "subject": subject,
        "to": [{"email": to_email, "name": SENDER_NAME}],
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
# HARO RESPONSE DRAFTING (kimi-k2.6:cloud)
# ============================================================================

def draft_response(query_data: dict) -> str:
    """Draft a response using the pitch angle system for smarter, more targeted pitches."""
    query_text = query_data.get('query_text', '')
    summary = query_data.get('summary', '')
    outlet = query_data.get('outlet', 'Unknown')
    deadline = query_data.get('deadline', 'Not specified')
    journalist_name = query_data.get('journalist_name', 'Unknown')

    # Select the best pitch angle and get its guidance
    angle_fn = get_angle_for_query(query_data)
    angle_name = angle_fn.__name__
    angle_guidance = get_angle_guidance(angle_fn)

    # Build angle-specific context
    angle_context = f"""## PITCH ANGLE: {angle_name}
## Angle guidance (use this to frame your response):
{angle_guidance}"""

    prompt = f"""You are drafting a professional response to a HARO (Help A Reporter Out) query.

## JOURNALIST DETAILS
- Name: {journalist_name}
- Outlet: {outlet}
- Deadline: {deadline}

## QUERY
{query_text}

## BRAND BIO
{BRAND_BIO}

## BRAND VOICE
{BRAND_VOICE}

{angle_context}

## TASK
Write a compelling, journalist-friendly HARO response that:
1. Addresses the query directly with valuable expert insights
2. Strongly emphasises the "{angle_name}" angle in your answer
3. Positions Craig Pauls as a knowledgeable South African home improvement expert
4. Is 150-250 words
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
# PLAYWRIGHT SCRIPTS
# ============================================================================

def run_playwright_script(script: str, timeout: int = 60) -> dict:
    """Run a Playwright Node.js script and return parsed JSON output."""
    script_path = SCRIPT_FILE
    script_path.write_text(script)

    result = subprocess.run(
        ["node", str(script_path)],
        capture_output=True, text=True, timeout=timeout,
        cwd="/tmp",
        env={**os.environ, "NODE_PATH": "/tmp/node_modules"}
    )

    if result.stderr:
        log(f"PW stderr: {result.stderr[:200]}")

    try:
        # Last line should be JSON
        lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
        if lines:
            return json.loads(lines[-1])
    except:
        pass
    return {"error": result.stdout[:500]}


def playwright_login_and_scrape_questions() -> dict:
    """Log in to Connectively via email/password and scrape the questions table."""
    script = r"""
const { chromium } = require('/tmp/node_modules/playwright');
(async () => {
    const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    
    await page.goto('https://www.connectively.us/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(2000);
    
    await page.locator('input[autocomplete="email"]').fill('__EMAIL__');
    await page.locator('input[autocomplete="current-password"]').fill('__PASSWORD__');
    
    await Promise.all([
        page.waitForFunction(
            () => !window.location.href.includes('/login'),
            { timeout: 30000 }
        ),
        page.locator('button[type="submit"]:has-text("Submit")').click()
    ]);
    
    await page.waitForTimeout(3000);
    console.log('Logged in. URL: ' + page.url());
    
    await page.goto('https://www.connectively.us/expert-questions', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(5000);
    
    console.log('Questions page: ' + page.url());
    
    const queries = await page.evaluate(() => {
        const results = [];
        const table = document.querySelector('table');
        if (!table) return { error: 'no table' };
        const tbody = table.querySelector('tbody');
        if (!tbody) return { error: 'no tbody' };
        const rows = tbody.querySelectorAll('tr');
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 4) {
                const links = cells[cells.length - 1].querySelectorAll('a');
                const answerLink = Array.from(links).find(a => a.textContent.trim() === 'Answer');
                const qCell = cells[1];
                const pubCell = cells[2];
                const dlCell = cells[3];
                let qText = qCell ? qCell.textContent.trim() : '';
                qText = qText.replace(/^Question\s*/i, '').replace(/^Questions\s*/i, '').trim();
                results.push({
                    question: qText.substring(0, 500),
                    publication: pubCell ? pubCell.textContent.trim().replace(/\s+/g, ' ') : '',
                    deadline: dlCell ? dlCell.textContent.trim().replace(/\s+/g, ' ') : '',
                    answerUrl: answerLink ? answerLink.href : ''
                });
            }
        });
        return { results, rowCount: rows.length };
    });
    
    const cookies = await ctx.cookies();
    const sessionToken = cookies.find(c => c.name.includes('session') || c.name.includes('auth'));
    
    console.log(JSON.stringify({
        queries: queries.results || [],
        token: sessionToken ? sessionToken.value : '',
        url: page.url(),
        cookieNames: cookies.map(c => c.name),
        error: queries.error
    }));
    await browser.close();
})().catch(e => { console.error('ERROR:' + e.message); process.exit(1); });
"""
    script = script.replace('__EMAIL__', CONNECTIVELY_EMAIL).replace('__PASSWORD__', CONNECTIVELY_PASSWORD)
    return run_playwright_script(script)


def playwright_get_query_text(question_url: str, token: str) -> dict:
    """Get full query text from a question page (requires auth)."""
    # Extract slug from URL
    slug = question_url.rstrip('/').split('/')[-1]

    script = fr"""
const {{ chromium }} = require('/tmp/node_modules/playwright');
(async () => {{
    const browser = await chromium.launch({{ headless: true, args: ['--no-sandbox'] }});
    const ctx = await browser.newContext();
    const page = await ctx.newPage();

    // Set auth cookies
    await ctx.addCookies([
        {{ name: '__Secure-better-auth.session_token', value: '{token}', domain: '.connectively.us', path: '/' }}
    ]);

    await page.goto('{question_url}', {{ waitUntil: 'domcontentloaded', timeout: 15000 }});
    await page.waitForTimeout(5000);

    // Extract question text - it's usually in a prominent div
    const questionText = await page.evaluate(() => {{
        // Try common selectors for question content
        const selectors = [
            '[class*="question"]', '[class*="Query"]', '[class*="query"]',
            'h1', 'h2', '[role="heading"]',
            'div[class*="Card"]', 'div[class*="Content"]'
        ];
        for (const sel of selectors) {{
            const el = document.querySelector(sel);
            if (el && el.textContent.length > 50) {{
                return el.textContent.trim().substring(0, 3000);
            }}
        }}
        // Fallback: body text
        return document.body.innerText.substring(0, 3000);
    }});

    // Extract publication name
    const publication = await page.evaluate(() => {{
        const els = document.querySelectorAll('[class*="pub" i], [class*="source" i], [class*="outlet" i]');
        for (const el of els) {{
            const t = el.textContent.trim();
            if (t.length > 1 && t.length < 100) return t;
        }}
        return window.location.hostname;
    }});

    // Extract deadline
    const deadline = await page.evaluate(() => {{
        const els = document.querySelectorAll('[class*="deadline" i], [class*="date" i], [class*="time" i]');
        for (const el of els) {{
            const t = el.textContent.trim();
            if (t.length > 1 && t.length < 50) return t;
        }}
        return '';
    }});

    // Check for textarea
    const hasForm = await page.locator('textarea, [role="textbox"]').count() > 0;

    console.log(JSON.stringify({{ questionText, publication, deadline, hasForm, url: page.url() }}));
    await browser.close();
}})().catch(e => {{ console.error('ERROR:' + e.message); process.exit(1); }});
"""
    result = run_playwright_script(script)
    if "error" in result:
        return result
    return result


def playwright_submit_answer(question_url: str, answer_text: str, token: str) -> dict:
    """Submit an answer to a Connectively question."""
    script = fr"""
const {{ chromium }} = require('/tmp/node_modules/playwright');
(async () => {{
    const browser = await chromium.launch({{ headless: true, args: ['--no-sandbox'] }});
    const ctx = await browser.newContext();
    const page = await ctx.newPage();

    // Set auth cookies
    await ctx.addCookies([
        {{ name: '__Secure-better-auth.session_token', value: '{token}', domain: '.connectively.us', path: '/' }}
    ]);

    await page.goto('{question_url}', {{ waitUntil: 'domcontentloaded', timeout: 15000 }});
    await page.waitForTimeout(5000);

    // Fill the answer textarea
    const textarea = page.locator('textarea, [role="textbox"]').first();
    const count = await textarea.count();
    if (count === 0) {{
        console.log(JSON.stringify({{ success: false, error: 'No textarea found' }}));
        await browser.close();
        return;
    }}

    safe_answer = answer_text.replace('`', '\\`')
    await textarea.fill(`{safe_answer}`);
    console.log('Filled textarea');

    // Find and click Submit
    const submitBtn = page.locator('button[type="submit"], button:has-text("Submit")').last();
    await submitBtn.click();
    console.log('Clicked submit');
    await page.waitForTimeout(5000);

    // Check result
    const resultText = await page.evaluate(() => document.body.innerText.substring(0, 500));
    const url = page.url();

    console.log(JSON.stringify({{ success: true, url, resultText }}));
    await browser.close();
}})().catch(e => {{ console.error('ERROR:' + e.message); process.exit(1); }});
"""
    result = run_playwright_script(script)
    if "error" in result:
        return result
    return result


# ============================================================================
# MAIN SCRAPE + PROCESS
# ============================================================================

def main():
    log("=== Connectively Monitor Run ===")

    # Step 1: Login and scrape questions table
    log("Logging in and scraping questions...")
    result = playwright_login_and_scrape_questions()

    if "error" in result:
        log(f"Login/scrape error: {result['error']}")
        return

    queries = result.get("queries", [])
    token = result.get("token", "")
    log(f"Found {len(queries)} queries, session token: {'present' if token else 'MISSING'}")

    if not token:
        log("ERROR: No session token - login may have failed")
        return

    if not queries:
        log("No queries found on page")
        return

    processed_count = 0
    drafted_count = 0

    for q in queries:
        answer_url = q.get("answerUrl", "")
        if not answer_url:
            # Try to construct from question text
            continue

        # Extract query ID from URL
        query_id = answer_url.rstrip('/').split('/')[-1]
        if not query_id:
            query_id = q.get("publication", "") + "_" + q.get("deadline", "")

        if is_processed(query_id):
            log(f"  [{query_id}] Already processed, skipping")
            continue

        question_text = q.get("question", "")
        if not question_text:
            log(f"  [{query_id}] No question text, skipping")
            mark_processed(query_id, "SKIPPED_NO_TEXT")
            continue

        # Step 2: Get full query text from question page
        log(f"  [{query_id}] Fetching full query text from {answer_url}...")
        detail = playwright_get_query_text(answer_url, token)
        full_text = detail.get("questionText", question_text)[:3000]
        outlet = detail.get("publication", q.get("publication", ""))
        deadline = detail.get("deadline", q.get("deadline", ""))

        if not full_text or len(full_text) < 20:
            log(f"  [{query_id}] Could not get full query text, using truncated")
            full_text = question_text

        log(f"  [{query_id}] Full text ({len(full_text)} chars): {full_text[:100]}...")

        # Build query_data for filtering
        query_data = {
            "query_text": full_text,
            "outlet": outlet,
            "deadline": deadline,
            "summary": full_text[:200],
            "journalist_name": "Unknown",
            "reply_to": detail.get("reply_to", "")
        }

        # Check blocklist — skip blocked outlets (e.g. guest-post sellers)
        outlet_lower = outlet.lower()
        if is_blocked(outlet):
            log(f"  [{query_id}] Outlet '{outlet}' is blocklisted — skipping")
            mark_processed(query_id, "SKIPPED_BLOCKLISTED")
            processed_count += 1
            continue

        # Check relevance
        relevant = is_relevant_query(query_data)
        score = score_relevance(query_data)
        log(f"  [{query_id}] Relevance: {relevant} (score: {score})")

        if not relevant:
            log(f"  [{query_id}] Not relevant — marking as skipped")
            mark_processed(query_id, "SKIPPED_NOT_RELEVANT")
            processed_count += 1
            continue

        # Draft response
        log(f"  [{query_id}] Drafting response with kimi-k2.6:cloud...")
        drafted = draft_response(query_data)

        if drafted.startswith("Error"):
            log(f"  [{query_id}] Drafting failed: {drafted}")
            mark_processed(query_id, "ERROR_DRAFT")
            continue

        # Save drafted response
        mark_processed(query_id, "AWAITING_APPROVAL", drafted, answer_url, answer_url)

        # Send approval email to Craig
        summary_preview = full_text[:80].replace('\n', ' ')
        angle_fn = get_angle_for_query(query_data)
        angle_name = angle_fn.__name__
        angle_tag = angle_name.replace('angle_', '').upper()
        word_count = len(drafted.split())
        subject = f"📋 [CONNECTIVELY APPROVAL] {angle_tag} | {outlet} — {summary_preview}"

        query_display = full_text[:800].replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        drafted_display = drafted.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')

        html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px;">
<div style="background: #f8f9fa; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
<h2 style="margin-top: 0;">📋 Connectively HARO Response — Ready for Approval</h2>
<p><strong>Outlet:</strong> {outlet}<br>
<strong>Deadline:</strong> {deadline}<br>
<strong>Relevance Score:</strong> {score}/100<br>
<strong>Pitch Angle:</strong> <span style="background: #e3f2fd; padding: 2px 8px; border-radius: 4px;">{angle_name.replace('angle_', '').upper()}</span></p>
<p><strong>Query:</strong></p>
<p style="background: white; padding: 15px; border-radius: 4px; border-left: 4px solid #0066cc;">{query_display}</p>
<p><strong>Query ID:</strong> {query_id}</p>
<p><strong>Answer URL:</strong> <a href="{answer_url}">{answer_url}</a></p>
</div>

<div style="background: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
<h3 style="margin-top: 0;">✍️ Drafted Response <span style="font-size:12px; color:#666; font-weight:normal;">({word_count} words)</span></h3>
<pre style="white-space: pre-wrap; font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;">{drafted_display}</pre>
</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 20px; text-align: center; margin-bottom: 20px;">
<h3 style="margin-top: 0; color: #2e7d32;">✅ APPROVE & SUBMIT</h3>
<p>Reply with <strong>YES</strong> to submit this response to Connectively now.</p>
<p>Reply with <strong>SKIP</strong> to discard this response.</p>
<p>Reply with <strong>EDIT</strong> followed by your revised text to send an edited version.</p>
</div>

<p style="color: #666; font-size: 12px; margin-top: 20px;">
Query ID: {query_id} | Processed: {datetime.now().isoformat()}
</p>
</body>
</html>"""

        send_result = send_email(NOTIFY_EMAIL, subject, html_body)
        if send_result.get("success"):
            log(f"  [{query_id}] Draft sent to Craig for approval ✅")
            drafted_count += 1
        else:
            log(f"  [{query_id}] Failed to send draft: {send_result.get('error')}")

        processed_count += 1

    log(f"=== Done. Processed: {processed_count}, Drafted: {drafted_count} ===")


if __name__ == "__main__":
    main()