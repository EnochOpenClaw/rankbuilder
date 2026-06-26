#!/usr/bin/env python3
"""
LinkedIn posting via Chrome DevTools Protocol (CDP).
Uses Craig's existing Chrome session on Windows — no new browser needed.
Page ID: 1CEAE53C8795E3539E1C5497A21C2D77 (LinkedIn Feed)
"""

import pychrome
import time
import json
from datetime import datetime

# ============================================================================
# CONFIG
# ============================================================================

CHROME_HOST = "localhost"
CHROME_PORT = 9222
LINKEDIN_PAGE_ID = "1CEAE53C8795E3539E1C5497A21C2D77"  # Your current LinkedIn tab

# ============================================================================
# CDP BROWSER CONNECTION
# ============================================================================

def get_tab_by_url(url_contains: str = None):
    """Find a Chrome tab by URL pattern."""
    try:
        tabs = pychrome.list_tabs(f"http://{CHROME_HOST}:{CHROME_PORT}")
        if url_contains:
            for t in tabs:
                if url_contains.lower() in t.get("url", "").lower():
                    return t
            return tabs[0] if tabs else None
        return tabs[0] if tabs else None
    except Exception as e:
        print(f"Tab lookup error: {e}")
        return None

# ============================================================================
# POSTING VIA CDP
# ============================================================================

def click_element(tab, selector: str, timeout: int = 5000):
    """Click an element via CDP."""
    try:
        # First, find the element
        result = tab.Runtime.evaluate(
            expression=f"""
                () => {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.scrollIntoViewIfNeeded();
                        const rect = el.getBoundingClientRect();
                        return {{ found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2, text: el.innerText?.slice(0,50) }};
                    }}
                    return {{ found: false }};
                }}
            """,
            awaitPromise=False
        )
        
        obj = result.get("result", {}).get("value", {})
        if not obj or not obj.get("found"):
            return False
        
        # Click at the element's center
        tab.Input.dispatchMouseEvent(
            type="mousePressed",
            x=obj["x"],
            y=obj["y"],
            button="left",
            clickCount=1
        )
        tab.Input.dispatchMouseEvent(
            type="mouseReleased",
            x=obj["x"],
            y=obj["y"],
            button="left",
            clickCount=1
        )
        return True
    except Exception as e:
        print(f"Click error: {e}")
        return False

def type_text(tab, text: str):
    """Type text via CDP."""
    for char in text:
        tab.Input.dispatchKeyEvent(type="char", text=char)
        time.sleep(0.01)

def post_via_cdp(text: str) -> dict:
    """Post a text update using Chrome's existing session via CDP."""
    try:
        # Connect to Chrome
        browser = pychrome.Browser(host=CHROME_HOST, port=CHROME_PORT)
        
        # Find the LinkedIn tab
        tabs = browser.list_tabs()
        linkedin_tab = None
        for t in tabs:
            if "linkedin.com/feed" in t.get("url", ""):
                linkedin_tab = t
                break
        
        if not linkedin_tab:
            return {"success": False, "error": "LinkedIn feed tab not found"}
        
        tab_id = linkedin_tab["id"]
        tab = browser.new_tab(tab_id)
        
        # Activate the tab
        browser.activate_tab(tab_id)
        time.sleep(1)
        
        # Check if we're on the feed
        current_url = tab.Page.getResourceTree().get("frame", {}).get("url", "")
        
        # Click "Start a post" button
        print("  Looking for Start a post button...")
        
        # Find and click the share box
        result = tab.Runtime.evaluate(
            expression="""
                () => {
                    // Try various share button selectors
                    const selectors = [
                        '[data-test-id="share-creation-start"]',
                        'button[aria-label*="Start post"]',
                        'button:has-text("Start a post")',
                        '.share-creation-icon',
                        '[data-control-name="share.sponsored"]'
                    ];
                    for (const s of selectors) {
                        const el = document.querySelector(s);
                        if (el) {
                            el.scrollIntoViewIfNeeded();
                            const rect = el.getBoundingClientRect();
                            return {
                                found: true,
                                selector: s,
                                x: rect.x + rect.width/2,
                                y: rect.y + rect.height/2,
                                text: el.innerText?.slice(0,50)
                            };
                        }
                    }
                    return { found: false };
                }
            """,
            awaitPromise=False
        )
        
        obj = result.get("result", {}).get("value", {})
        
        if obj and obj.get("found"):
            print(f"  Found: {obj.get('selector')} — {obj.get('text')}")
            # Click it
            tab.Input.dispatchMouseEvent(type="mousePressed", x=obj["x"], y=obj["y"], button="left", clickCount=1)
            tab.Input.dispatchMouseEvent(type="mouseReleased", x=obj["x"], y=obj["y"], button="left", clickCount=1)
            time.sleep(2)
            
            # Now find the text input in the composer
            result2 = tab.Runtime.evaluate(
                expression="""
                    () => {
                        const selectors = [
                            '.ql-editor[contenteditable="true"]',
                            '[data-test-id="share-composer"] [contenteditable="true"]',
                            '.feed-composer__input',
                            '[aria-label*="Write"]'
                        ];
                        for (const s of selectors) {
                            const el = document.querySelector(s);
                            if (el) {
                                el.focus();
                                const rect = el.getBoundingClientRect();
                                return {
                                    found: true,
                                    selector: s,
                                    x: rect.x + rect.width/2,
                                    y: rect.y + rect.height/2
                                };
                            }
                        }
                        return { found: false };
                    }
                """,
                awaitPromise=False
            )
            
            obj2 = result2.get("result", {}).get("value", {})
            
            if obj2 and obj2.get("found"):
                print(f"  Found composer input: {obj2.get('selector')}")
                # Click and type
                tab.Input.dispatchMouseEvent(type="mousePressed", x=obj2["x"], y=obj2["y"], button="left", clickCount=1)
                tab.Input.dispatchMouseEvent(type="mouseReleased", x=obj2["x"], y=obj2["y"], button="left", clickCount=1)
                time.sleep(0.5)
                
                # Type the post
                type_text(tab, text)
                time.sleep(1)
                
                # Find and click Post button
                result3 = tab.Runtime.evaluate(
                    expression="""
                        () => {
                            const selectors = [
                                'button[aria-label*="Post"]',
                                '[data-test-id="share-post-button"]',
                                'button:has-text("Post"):not([disabled])'
                            ];
                            for (const s of selectors) {
                                const el = document.querySelector(s);
                                if (el && !el.disabled) {
                                    el.scrollIntoViewIfNeeded();
                                    const rect = el.getBoundingClientRect();
                                    return {
                                        found: true,
                                        x: rect.x + rect.width/2,
                                        y: rect.y + rect.height/2,
                                        disabled: el.disabled
                                    };
                                }
                            }
                            return { found: false };
                        }
                    """,
                    awaitPromise=False
                )
                
                obj3 = result3.get("result", {}).get("value", {})
                if obj3 and obj3.get("found"):
                    print("  Clicking Post button...")
                    tab.Input.dispatchMouseEvent(type="mousePressed", x=obj3["x"], y=obj3["y"], button="left", clickCount=1)
                    tab.Input.dispatchMouseEvent(type="mouseReleased", x=obj3["x"], y=obj3["y"], button="left", clickCount=1)
                    time.sleep(3)
                    return {"success": True, "posted": True}
                else:
                    return {"success": False, "error": "Post button not found in composer"}
            else:
                return {"success": False, "error": "Composer input not found"}
        else:
            return {"success": False, "error": "Start post button not found"}
        
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "trace": traceback.format_exc()[:500]}

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="LinkedIn CDP posting")
    parser.add_argument("--post", type=str, help="Text to post")
    parser.add_argument("--test", action="store_true", help="Test CDP connection")
    
    args = parser.parse_args()
    
    if args.test:
        try:
            browser = pychrome.Browser(host=CHROME_HOST, port=CHROME_PORT)
            tabs = browser.list_tabs()
            print(f"✅ Connected to Chrome! {len(tabs)} tabs open.")
            for t in tabs:
                print(f"  - {t.get('title','')[:60]} | {t.get('url','')[:60]}")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
    
    elif args.post:
        print(f"Posting via CDP: {args.post[:50]}...")
        result = post_via_cdp(args.post)
        if result.get("success"):
            print("✅ Posted successfully!")
        else:
            print(f"❌ Failed: {result.get('error')}")
    
    else:
        print("LinkedIn CDP posting")
        print("  --test        Test connection to Chrome")
        print("  --post 'txt'  Post text update via CDP")