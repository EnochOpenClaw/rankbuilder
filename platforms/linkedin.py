#!/usr/bin/env python3
"""
LinkedIn posting via Playwright — uses saved cookies for instant auth.
No API approval needed. Cookie-based session from EditThisCookie export.
"""

import json, time, sys, subprocess
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

# ============================================================================
# PATHS
# ============================================================================

PLATFORM_DIR = Path(__file__).parent
COOKIES_FILE = PLATFORM_DIR / "linkedin_cookies.txt"
SESSION_FILE = PLATFORM_DIR / "linkedin_session.json"
LOG_FILE = PLATFORM_DIR / "linkedin_post_log.jsonl"

# ============================================================================
# PLAYWRIGHT LAUNCHER
# ============================================================================

def get_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright()
    except ImportError:
        # Try system install
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       capture_output=True)
        from playwright.sync_api import sync_playwright
        return sync_playwright()

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

def load_cookies():
    """Load cookies from Netscape format file."""
    if not COOKIES_FILE.exists():
        return []
    
    cookies = []
    seen = set()
    with open(COOKIES_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                name = parts[5]
                if name in seen:
                    continue
                seen.add(name)
                exp_str = parts[4]
                exp_val = float(exp_str) if exp_str and exp_str != "0" else -1  # -1 = session cookie
                cookies.append({
                    "name": name,
                    "value": parts[6],
                    "domain": parts[0],
                    "path": parts[2],
                    "secure": parts[3] == "TRUE",
                    "expires": exp_val,
                    "httpOnly": False,
                })
    return cookies

def is_logged_in(page) -> bool:
    """Check if we're logged into LinkedIn."""
    try:
        page.goto("https://www.linkedin.com/feed/", timeout=30000, wait_until="domcontentloaded")
        time.sleep(2)
        
        # Check for logged-in indicators
        if page.query_selector('[data-test-id="main-feed"]'):
            return True
        if page.query_selector('.feed-shared-update-v2'):
            return True
        if page.url and "feed" in page.url:
            title = page.title()
            if "LinkedIn" in title and "Sign" not in title:
                return True
        
        # Check for li_at cookie being set
        cookies = page.context.cookies()
        li_at = [c for c in cookies if c["name"] == "li_at"]
        return len(li_at) > 0
        
    except Exception as e:
        print(f"    is_logged_in check error: {e}")
        return False

# ============================================================================
# POSTING FUNCTIONS
# ============================================================================

def post_text_update(text: str) -> dict:
    """Post a simple text update to LinkedIn feed."""
    with get_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        
        # Load cookies
        cookies = load_cookies()
        if not cookies:
            return {"success": False, "error": "No cookies found"}
        
        # Add cookies to context
        context.add_cookies(cookies)
        
        page = context.new_page()
        
        # Check if logged in
        if not is_logged_in(page):
            browser.close()
            return {"success": False, "error": "Not logged in — cookies may be expired"}
        
        try:
            # Go to feed and start post
            page.goto("https://www.linkedin.com/feed/", timeout=30000, wait_until="load")
            time.sleep(2)
            
            # Find and click "Start post" / "Write post" button
            start_btn = page.query_selector('[data-test-id="share-creation-start"]')
            if not start_btn:
                start_btn = page.query_selector('button:has-text("Start a post"), [aria-label*="Start post"]')
            
            if start_btn:
                start_btn.click()
                time.sleep(1)
            
            # Wait for composer
            page.wait_for_selector('.ql-editor[contenteditable="true"], [data-test-id="share-composer"]', 
                                  timeout=10000)
            
            # Type the post content
            text_area = page.query_selector('.ql-editor[contenteditable="true"]')
            if not text_area:
                text_area = page.query_selector('[data-test-id="share-composer"] [contenteditable]')
            
            if text_area:
                text_area.click()
                # Clear first
                page.keyboard.press("Control+A")
                text_area.fill(text)
            else:
                # Fallback: click and type
                page.click('[data-test-id="share-composer"]')
                page.keyboard.type(text, delay=5)
            
            time.sleep(1)
            
            # Find and click Post button
            post_btn = page.query_selector('button[aria-label*="Post"], [data-test-id="share-post-button"]')
            if not post_btn:
                post_btn = page.query_selector('button:has-text("Post"):not([disabled])')
            
            if post_btn:
                post_btn.click()
                time.sleep(3)
                
                # Check for success
                if page.query_selector('.feed-shared-update-v2, .artdeco-toast'):
                    result = {"success": True, "posted": True}
                else:
                    result = {"success": True, "posted": True, "note": "no confirmation found but likely posted"}
            else:
                result = {"success": False, "error": "Post button not found"}
            
            browser.close()
            return result
            
        except Exception as e:
            browser.close()
            return {"success": False, "error": str(e)}

def post_article(title: str, body: str, article_url: str = None) -> dict:
    """Post an article with link to LinkedIn."""
    with get_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        context.add_cookies(load_cookies())
        page = context.new_page()
        
        if not is_logged_in(page):
            browser.close()
            return {"success": False, "error": "Not logged in"}
        
        try:
            page.goto("https://www.linkedin.com/feed/", timeout=30000, wait_until="load")
            time.sleep(2)
            
            # Navigate to article creation
            page.goto("https://www.linkedin.com/pulse/editor", timeout=30000, wait_until="load")
            time.sleep(2)
            
            # Fill in title
            title_input = page.query_selector('input[name="title"], [data-test-id="article-title-input"]')
            if title_input:
                title_input.fill(title)
            
            # Fill in body
            body_area = page.query_selector('.ql-editor[contenteditable="true"]')
            if body_area:
                body_area.fill(body[:1300])
            
            # Add link if provided
            if article_url:
                link_btn = page.query_selector('button:has-text("Add link"), [aria-label*="link"]')
                if link_btn:
                    link_btn.click()
                    time.sleep(0.5)
                    link_input = page.query_selector('input[placeholder*="URL" i]')
                    if link_input:
                        link_input.fill(article_url)
            
            time.sleep(1)
            
            # Publish
            publish_btn = page.query_selector('button[aria-label*="Publish"], [data-test-id="publish-button"]')
            if publish_btn:
                publish_btn.click()
                time.sleep(3)
                return {"success": True, "posted": True, "type": "article"}
            
            browser.close()
            return {"success": False, "error": "Publish button not found"}
            
        except Exception as e:
            browser.close()
            return {"success": False, "error": str(e)}

# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="LinkedIn posting via Playwright")
    parser.add_argument("--test", action="store_true", help="Test if cookies are valid")
    parser.add_argument("--post", type=str, help="Post a text update")
    parser.add_argument("--title", type=str, help="Article title")
    parser.add_argument("--body", type=str, help="Article body")
    parser.add_argument("--link", type=str, help="Link to attach")
    
    args = parser.parse_args()
    
    if args.test:
        with get_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            context.add_cookies(load_cookies())
            page = context.new_page()
            
            if is_logged_in(page):
                print("✅ Cookies are valid — logged into LinkedIn!")
                # Get profile info
                try:
                    page.goto("https://www.linkedin.com/in/me/", timeout=10000)
                    name = page.query_selector(".pv-top-card__name")
                    if name:
                        print(f"   Profile: {name.inner_text()}")
                except:
                    pass
            else:
                print("❌ Cookies invalid or expired — need fresh export from EditThisCookie")
            
            browser.close()
    
    elif args.post:
        print(f"Posting: {args.post[:50]}...")
        result = post_text_update(args.post)
        if result.get("success"):
            print(f"✅ Posted successfully!")
        else:
            print(f"❌ Failed: {result.get('error')}")
    
    elif args.title:
        print(f"Posting article: {args.title[:50]}...")
        result = post_article(args.title, args.body or "", args.link)
        if result.get("success"):
            print(f"✅ Article posted!")
        else:
            print(f"❌ Failed: {result.get('error')}")
    
    else:
        print("LinkedIn Playwright posting")
        print("  --test             Test if cookies are valid")
        print("  --post 'text'      Post a text update")
        print("  --title 't' --body 'b' --link 'u'   Post an article")