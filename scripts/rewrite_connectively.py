#!/usr/bin/env python3
filepath = '/home/enoch/.openclaw/workspace/rankbuilder/scripts/connectively_monitor.py'
with open(filepath, 'r') as f:
    lines = f.readlines()

nl = '\n'

new_run_pw = (
    "def _make_stealth_browser(p):" + nl +
    "    from playwright_stealth import stealth" + nl +
    "    browser = p.chromium.launch(" + nl +
    "        headless=True," + nl +
    "        args=[" + nl +
    "            '--no-sandbox'," + nl +
    "            '--disable-setuid-sandbox'," + nl +
    "            '--disable-blink-features=AutomationControlled'," + nl +
    "            '--disable-webgl'," + nl +
    "            '--disable-dev-shm-usage'," + nl +
    "        ]" + nl +
    "    )" + nl +
    "    ctx = browser.new_context(" + nl +
    "        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'," + nl +
    "        locale='en-US'," + nl +
    "        timezone_id='Africa/Johannesburg'," + nl +
    "        viewport={'width': 1920, 'height': 1080}," + nl +
    "        extra_http_headers={" + nl +
    "            'Accept-Language': 'en-US,en;q=0.9'," + nl +
    "            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'," + nl +
    "        }," + nl +
    "    )" + nl +
    "    page = ctx.new_page()" + nl +
    "    s = stealth.Stealth(" + nl +
    "        navigator_webdriver=True, navigator_plugins=True," + nl +
    "        navigator_user_agent=True, navigator_hardware_concurrency=True," + nl +
    "        navigator_languages=True, navigator_platform=True," + nl +
    "        webgl_vendor=True, chrome_load_times=True," + nl +
    "        iframe_content_window=True," + nl +
    "    )" + nl +
    "    s.apply_stealth_sync(page)" + nl +
    "    ctx._browser = browser" + nl +
    "    return browser, ctx, page" + nl +
    "" + nl +
    "def run_playwright(script_fn, timeout: int = 60) -> dict:" + nl +
    "    from playwright.sync_api import sync_playwright" + nl +
    "    try:" + nl +
    "        with sync_playwright() as p:" + nl +
    "            browser, ctx, page = _make_stealth_browser(p)" + nl +
    "            result = script_fn(p, ctx, page)" + nl +
    "            browser.close()" + nl +
    "            return result" + nl +
    "    except Exception as e:" + nl +
    "        return {'error': str(e)}" + nl +
    "" + nl
)

new_login = (
    "def playwright_login_and_scrape_questions() -> dict:" + nl +
    "    def _run(p, ctx, page):" + nl +
    "        page.goto('https://www.connectively.us/login', wait_until='domcontentloaded', timeout=20000)" + nl +
    "        page.wait_for_timeout(3000)" + nl +
    "        page_title = page.title()" + nl +
    "        log(f\"Login page: title='{page_title}', URL={page.url()}\")" + nl +
    "        if 'vercel' in page_title.lower() or 'security' in page_title.lower():" + nl +
    "            return {'error': 'Blocked by bot protection: ' + page_title}" + nl +
    "        try:" + nl +
    "            page.wait_for_selector('input[type=\"email\"], input[name=\"email\"], input[id=\"email\"]'," + nl +
    "                                   timeout=10000, state='attached')" + nl +
    "        except Exception as e:" + nl +
    "            return {'error': 'Form elements not found: ' + str(e)}" + nl +
    "        email_field = (page.locator('input[type=\"email\"]').first" + nl +
    "                      .or_(page.locator('input[name=\"email\"]').first)" + nl +
    "                      .or_(page.locator('input[id=\"email\"]').first)" + nl +
    "                      .or_(page.locator('input[autocomplete=\"email\"]').first))" + nl +
    "        password_field = (page.locator('input[type=\"password\"]').first" + nl +
    "                         .or_(page.locator('input[name=\"password\"]').first)" + nl +
    "                         .or_(page.locator('input[id=\"password\"]').first))" + nl +
    "        email_field.fill(CONNECTIVELY_EMAIL)" + nl +
    "        password_field.fill(CONNECTIVELY_PASSWORD)" + nl +
    "        page.locator('button[type=\"submit\"]').click()" + nl +
    "        page.wait_for_function(lambda: '/login' not in page.url, timeout=30000)" + nl +
    "        page.wait_for_timeout(3000)" + nl +
    "        log(f\"After login URL: {page.url()}\")" + nl +
    "        page.goto('https://www.connectively.us/expert-questions', wait_until='domcontentloaded', timeout=15000)" + nl +
    "        page.wait_for_timeout(5000)" + nl +
    "        qscript = (\"() => { var t = document.querySelector('table tbody'); \" +\n" +
    "                   \"if (!t) return {error: 'no tbody'}; var rows = t.querySelectorAll('tr'); \" +\n" +
    "                   \"var r = []; rows.forEach(function(row) { var c = row.querySelectorAll('td'); \" +\n" +
    "                   \"if (c.length >= 4) { var links = c[c.length-1].querySelectorAll('a'); \" +\n" +
    "                   \"var al = null; for (var i=0;i<links.length;i++) { \" +\n" +
    "                   \"if (links[i].textContent.trim() === 'Answer') { al = links[i]; break; } } \" +\n" +
    "                   \"var qt = c[1].textContent.trim().replace(/^Question\\\\s*/i,'').replace(/^Questions\\\\s*/i,'').trim(); \" +\n" +
    "                   \"r.push({question: qt.substring(0,500), \" +\n" +
    "                   \"publication: c[2].textContent.trim().replace(/\\\\s+/g,' '), \" +\n" +
    "                   \"deadline: c[3].textContent.trim().replace(/\\\\s+/g,' '), \" +\n" +
    "                   \"answerUrl: al ? al.href : ''}); } }); return {results: r}; }\")" + nl +
    "        queries = page.evaluate(qscript)" + nl +
    "        cookies = ctx.cookies()" + nl +
    "        session_token = next((c['value'] for c in cookies if 'session' in c['name'] or 'auth' in c['name']), '')" + nl +
    "        log(f\"Scraped {len(queries.get('results', []))} queries\")" + nl +
    "        return {" + nl +
    "            'queries': queries.get('results', [])," + nl +
    "            'token': session_token," + nl +
    "            'url': page.url," + nl +
    "            'cookieNames': [c['name'] for c in cookies]" + nl +
    "        }" + nl +
    "    return run_playwright(_run)" + nl +
    "" + nl
)

new_get_text = (
    "def playwright_get_query_text(question_url: str, token: str) -> dict:" + nl +
    "    def _run(p, ctx, page):" + nl +
    "        ctx.add_cookies([{" + nl +
    "            'name': '__Secure-better-auth.session_token'," + nl +
    "            'value': token," + nl +
    "            'domain': '.connectively.us'," + nl +
    "            'path': '/'" + nl +
    "        }])" + nl +
    "        page.goto(question_url, wait_until='domcontentloaded', timeout=15000)" + nl +
    "        page.wait_for_timeout(5000)" + nl +
    "        question_text = page.evaluate((\"() => { \" +\n" +
    "            \"var selectors = ['[class*=question]', '[class*=Query]', 'h1', 'h2', \" +\n" +
    "            \"'div[class*=Card]', 'div[class*=Content]']; \" +\n" +
    "            \"for (var i=0; i<selectors.length; i++) { \" +\n" +
    "            \"var el = document.querySelector(selectors[i]); \" +\n" +
    "            \"if (el && el.textContent.length > 50) return el.textContent.trim().substring(0, 3000); } \" +\n" +
    "            \"return document.body.innerText.substring(0, 3000); }\"))" + nl +
    "        publication = page.evaluate((\"() => { \" +\n" +
    "            \"var els = document.querySelectorAll('[class*=pub i], [class*=source i], [class*=outlet i]'); \" +\n" +
    "            \"for (var i=0; i<els.length; i++) { var t = els[i].textContent.trim(); \" +\n" +
    "            \"if (t.length>1 && t.length<100) return t; } return window.location.hostname; }\"))" + nl +
    "        deadline = page.evaluate((\"() => { \" +\n" +
    "            \"var els = document.querySelectorAll('[class*=deadline i], [class*=date i], [class*=time i]'); \" +\n" +
    "            \"for (var i=0; i<els.length; i++) { var t = els[i].textContent.trim(); \" +\n" +
    "            \"if (t.length>1 && t.length<50) return t; } return ''; }\"))" + nl +
    "        has_form = page.locator('textarea, [role=\"textbox\"]').count() > 0" + nl +
    "        return {" + nl +
    "            'questionText': question_text," + nl +
    "            'publication': publication," + nl +
    "            'deadline': deadline," + nl +
    "            'hasForm': has_form," + nl +
    "            'url': page.url" + nl +
    "        }" + nl +
    "    return run_playwright(_run)" + nl +
    "" + nl
)

new_submit = (
    "def playwright_submit_answer(question_url: str, answer_text: str, token: str) -> dict:" + nl +
    "    def _run(p, ctx, page):" + nl +
    "        ctx.add_cookies([{" + nl +
    "            'name': '__Secure-better-auth.session_token'," + nl +
    "            'value': token," + nl +
    "            'domain': '.connectively.us'," + nl +
    "            'path': '/'" + nl +
    "        }])" + nl +
    "        page.goto(question_url, wait_until='domcontentloaded', timeout=15000)" + nl +
    "        page.wait_for_timeout(5000)" + nl +
    "        textarea = page.locator('textarea, [role=\"textbox\"]').first" + nl +
    "        if textarea.count() == 0:" + nl +
    "            return {'success': False, 'error': 'No textarea found'}" + nl +
    "        safe_answer = answer_text.replace('`', '\\\\`')" + nl +
    "        textarea.fill(safe_answer)" + nl +
    "        log('Filled textarea')" + nl +
    "        page.locator('button[type=\"submit\"], button:has-text(\"Submit\")').last.click()" + nl +
    "        log('Clicked submit')" + nl +
    "        page.wait_for_timeout(5000)" + nl +
    "        result_text = page.evaluate('() => document.body.innerText.substring(0, 500)')" + nl +
    "        final_url = page.url" + nl +
    "        return {'success': True, 'url': final_url, 'resultText': result_text}" + nl +
    "    return run_playwright(_run)" + nl +
    "" + nl
)

# Verify line numbers
print(f"Lines: {len(lines)}")
# run_pw at line 217, ends at line 241 (0-indexed 216-240)
# login at line 243 (0-indexed 242)
# get at line 348
# submit at line 407

# Check exact line numbers
for i, line in enumerate(lines):
    if i in (216, 241, 242, 347, 348, 405, 406, 437, 438):
        print(f"  Line {i+1}: {repr(line[:60])}")

# Replace
new_lines = (
    lines[:216] +
    [new_run_pw] +
    [new_login] +
    [new_get_text] +
    [new_submit] +
    lines[438:]
)

print(f"New lines: {len(new_lines)}")
with open(filepath, 'w') as f:
    f.writelines(new_lines)
print("Written")
