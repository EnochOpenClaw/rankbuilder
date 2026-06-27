#!/usr/bin/env python3
"""Replace Node.js Playwright section with Python Playwright in connectively_monitor.py"""

filepath = '/home/enoch/.openclaw/workspace/rankbuilder/scripts/connectively_monitor.py'
with open(filepath, 'r') as f:
    content = f.read()

# The new Python Playwright section - using chr(10) to avoid escape issues
nl = '\n'
new_section = (
    "# ============================================================================" + nl +
    "# PLAYWRIGHT (Python Playwright — no Node.js required)" + nl +
    "# ============================================================================" + nl +
    nl +
    "def run_playwright(script_fn, timeout: int = 60) -> dict:" + nl +
    "    from playwright.sync_api import sync_playwright" + nl +
    "    try:" + nl +
    "        with sync_playwright() as p:" + nl +
    "            return script_fn(p)" + nl +
    "    except Exception as e:" + nl +
    "        return {\"error\": str(e)}" + nl +
    nl +
    nl +
    "def playwright_login_and_scrape_questions() -> dict:" + nl +
    "    def _run(p):" + nl +
    "        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])" + nl +
    "        ctx = browser.new_context()" + nl +
    "        page = ctx.new_page()" + nl +
    nl +
    "        page.goto('https://www.connectively.us/login', wait_until='domcontentloaded', timeout=15000)" + nl +
    "        page.wait_for_timeout(2000)" + nl +
    "        page.locator('input[autocomplete=\"email\"]').fill(CONNECTIVELY_EMAIL)" + nl +
    "        page.locator('input[autocomplete=\"current-password\"]').fill(CONNECTIVELY_PASSWORD)" + nl +
    "        page.locator('button[type=\"submit\"]:has-text(\"Submit\")').click()" + nl +
    "        page.wait_for_function(lambda: '/login' not in page.url, timeout=30000)" + nl +
    "        page.wait_for_timeout(3000)" + nl +
    '        log(f"Logged in. URL: {page.url()}")' + nl +
    nl +
    "        page.goto('https://www.connectively.us/expert-questions', wait_until='domcontentloaded', timeout=15000)" + nl +
    "        page.wait_for_timeout(5000)" + nl +
    nl +
    "        qscript = \"\"\"() => {" + nl +
    "            const results = [];" + nl +
    "            const table = document.querySelector('table');" + nl +
    "            if (!table) return { error: 'no table' };" + nl +
    "            const tbody = table.querySelector('tbody');" + nl +
    "            if (!tbody) return { error: 'no tbody' };" + nl +
    "            const rows = tbody.querySelectorAll('tr');" + nl +
    "            rows.forEach(row => {" + nl +
    "                const cells = row.querySelectorAll('td');" + nl +
    "                if (cells.length >= 4) {" + nl +
    "                    const links = cells[cells.length - 1].querySelectorAll('a');" + nl +
    "                    const answerLink = Array.from(links).find(a => a.textContent.trim() === 'Answer');" + nl +
    "                    const qCell = cells[1];" + nl +
    "                    const pubCell = cells[2];" + nl +
    "                    const dlCell = cells[3];" + nl +
    "                    let qText = qCell ? qCell.textContent.trim() : '';" + nl +
    "                    qText = qText.replace(/^Question\\s*/i, '').replace(/^Questions\\s*/i, '').trim();" + nl +
    "                    results.push({" + nl +
    "                        question: qText.substring(0, 500)," + nl +
    "                        publication: pubCell ? pubCell.textContent.trim().replace(/\\s+/g, ' ') : ''," + nl +
    "                        deadline: dlCell ? dlCell.textContent.trim().replace(/\\s+/g, ' ') : ''," + nl +
    "                        answerUrl: answerLink ? answerLink.href : ''" + nl +
    "                    });" + nl +
    "                }" + nl +
    "            });" + nl +
    "            return { results, rowCount: rows.length };" + nl +
    "        }\"\"\"" + nl +
    "        queries = page.evaluate(qscript)" + nl +
    nl +
    "        cookies = ctx.cookies()" + nl +
    "        session_token = next((c['value'] for c in cookies if 'session' in c['name'] or 'auth' in c['name']), '')" + nl +
    '        log(f"Scraped {len(queries.get(\"results\", []))} queries")' + nl +
    "        browser.close()" + nl +
    "        return {" + nl +
    "            'queries': queries.get('results', [])," + nl +
    "            'token': session_token," + nl +
    "            'url': page.url," + nl +
    "            'cookieNames': [c['name'] for c in cookies]" + nl +
    "        }" + nl +
    "    return run_playwright(_run)" + nl +
    nl +
    nl +
    "def playwright_get_query_text(question_url: str, token: str) -> dict:" + nl +
    "    def _run(p):" + nl +
    "        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])" + nl +
    "        ctx = browser.new_context()" + nl +
    "        ctx.add_cookies([{" + nl +
    "            'name': '__Secure-better-auth.session_token'," + nl +
    "            'value': token," + nl +
    "            'domain': '.connectively.us'," + nl +
    "            'path': '/'" + nl +
    "        }])" + nl +
    "        page = ctx.new_page()" + nl +
    "        page.goto(question_url, wait_until='domcontentloaded', timeout=15000)" + nl +
    "        page.wait_for_timeout(5000)" + nl +
    nl +
    "        qtext_script = \"\"\"() => {" + nl +
    "            const selectors = [" + nl +
    "                '[class*=\"question\"]', '[class*=\"Query\"]', '[class*=\"query\"]'," + nl +
    "                'h1', 'h2', '[role=\"heading\"]'," + nl +
    "                'div[class*=\"Card\"]', 'div[class*=\"Content\"]'" + nl +
    "            ];" + nl +
    "            for (const sel of selectors) {" + nl +
    "                const el = document.querySelector(sel);" + nl +
    "                if (el && el.textContent.length > 50) {" + nl +
    "                    return el.textContent.trim().substring(0, 3000);" + nl +
    "                }" + nl +
    "            }" + nl +
    "            return document.body.innerText.substring(0, 3000);" + nl +
    "        }\"\"\"" + nl +
    "        question_text = page.evaluate(qtext_script)" + nl +
    nl +
    "        pub_script = \"\"\"() => {" + nl +
    "            const els = document.querySelectorAll('[class*=\"pub\" i], [class*=\"source\" i], [class*=\"outlet\" i]');" + nl +
    "            for (const el of els) {" + nl +
    "                const t = el.textContent.trim();" + nl +
    "                if (t.length > 1 && t.length < 100) return t;" + nl +
    "            }" + nl +
    "            return window.location.hostname;" + nl +
    "        }\"\"\"" + nl +
    "        publication = page.evaluate(pub_script)" + nl +
    nl +
    "        dl_script = \"\"\"() => {" + nl +
    "            const els = document.querySelectorAll('[class*=\"deadline\" i], [class*=\"date\" i], [class*=\"time\" i]');" + nl +
    "            for (const el of els) {" + nl +
    "                const t = el.textContent.trim();" + nl +
    "                if (t.length > 1 && t.length < 50) return t;" + nl +
    "            }" + nl +
    "            return '';" + nl +
    "        }\"\"\"" + nl +
    "        deadline = page.evaluate(dl_script)" + nl +
    nl +
    "        has_form = page.locator('textarea, [role=\"textbox\"]').count() > 0" + nl +
    "        browser.close()" + nl +
    "        return {" + nl +
    "            'questionText': question_text," + nl +
    "            'publication': publication," + nl +
    "            'deadline': deadline," + nl +
    "            'hasForm': has_form," + nl +
    "            'url': page.url" + nl +
    "        }" + nl +
    "    return run_playwright(_run)" + nl +
    nl +
    nl +
    "def playwright_submit_answer(question_url: str, answer_text: str, token: str) -> dict:" + nl +
    "    def _run(p):" + nl +
    "        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])" + nl +
    "        ctx = browser.new_context()" + nl +
    "        ctx.add_cookies([{" + nl +
    "            'name': '__Secure-better-auth.session_token'," + nl +
    "            'value': token," + nl +
    "            'domain': '.connectively.us'," + nl +
    "            'path': '/'" + nl +
    "        }])" + nl +
    "        page = ctx.new_page()" + nl +
    "        page.goto(question_url, wait_until='domcontentloaded', timeout=15000)" + nl +
    "        page.wait_for_timeout(5000)" + nl +
    nl +
    "        textarea = page.locator('textarea, [role=\"textbox\"]').first" + nl +
    "        if textarea.count() == 0:" + nl +
    "            browser.close()" + nl +
    "            return {'success': False, 'error': 'No textarea found'}" + nl +
    nl +
    "        safe_answer = answer_text.replace('`', '\\\\`')" + nl +
    "        textarea.fill(safe_answer)" + nl +
    "        log('Filled textarea')" + nl +
    nl +
    "        page.locator('button[type=\"submit\"], button:has-text(\"Submit\")').last.click()" + nl +
    "        log('Clicked submit')" + nl +
    "        page.wait_for_timeout(5000)" + nl +
    nl +
    "        result_text = page.evaluate('() => document.body.innerText.substring(0, 500)')" + nl +
    "        final_url = page.url" + nl +
    "        browser.close()" + nl +
    "        return {'success': True, 'url': final_url, 'resultText': result_text}" + nl +
    "    return run_playwright(_run)" + nl +
    nl +
    nl
)

# Find the section to replace
start_marker = '# ============================================================================\n# PLAYWRIGHT SCRIPTS'
end_marker = '# ============================================================================\n# MAIN SCRAPE'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker) + len('# ============================================================================\n# MAIN SCRAPE')

print(f"start_idx: {start_idx}, end_idx: {end_idx}")

if start_idx == -1:
    print("ERROR: start marker not found")
    exit(1)
elif end_idx < start_idx:
    print("ERROR: end marker not found")
    exit(1)

old_len = end_idx - start_idx
new_content = content[:start_idx] + new_section + content[end_idx:]
with open(filepath, 'w') as f:
    f.write(new_content)
print(f"Replaced {old_len} chars with {len(new_section)} chars")
print(f"New file length: {len(new_content)} (was {len(content)})")
