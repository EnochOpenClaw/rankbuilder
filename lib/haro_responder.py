#!/usr/bin/env python3
"""
HARO Responder - Core Library
Handles parsing of forwarded HARO emails and drafting responses via Claude.
"""

import re
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Humanize via Ollama — no external API needed
import urllib.request, urllib.error, json as _json
from pathlib import Path

# Resolve humanize_cli path: container (/app/...) or local (~/.openclaw/...)
_candidates = [
    Path("/app/skills/humanize-text/scripts"),
    Path.home() / ".openclaw" / "workspace" / "skills" / "humanize-text" / "scripts",
]
_hc_path = next((p for p in _candidates if p.exists()), _candidates[0])
import sys as _sys_hc
_sys_hc.path.append(str(_hc_path))
import humanize_cli as _hc


def _ollama_humanize(text: str, style: str = "formal") -> str:
    """Call local Ollama with the humanize-text skill system prompt."""
    import urllib.request, urllib.error, json as _json

    system = (
        "You are a text humanization editor. Rewrite the following text so it sounds "
        "like a real person wrote it — not an AI. Remove all signs of AI writing: "
        "significance inflation, filler phrases, chatbot artifacts, hedging, generic "
        "conclusions. Use natural sentence length variation (some short, some long). "
        "Match this tone: " + style + ". Preserve all facts and core message. "
        "Output only the humanized text, no preamble or notes."
    )
    payload = {
        "model": "kimi-k2.6:cloud",
        "system": system,
        "prompt": text,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.6, "num_predict": 1500},
    }
    data = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = _json.loads(resp.read().decode())
            # kimi-k2.6:cloud uses thinking mode — actual response may be in 'thinking' field
            response = result.get("response", "").strip()
            if not response and result.get("thinking"):
                response = result["thinking"].strip()
            return response or text
    except Exception:
        return text  # degrade gracefully


def humanize_draft(draft_text: str, level: str = "formal", style: str = "formal") -> dict:
    """
    Apply humanization to a drafted HARO response using Ollama.

    Args:
        draft_text: The LLM-drafted response text.
        level: Ignored (kept for API compat) — always uses Ollama LLM rewrite.
        style: 'formal' (HARO/pitch), 'casual' (LinkedIn), 'technical'.

    Returns:
        dict with original_score, humanized_score, humanized_text, changes_summary.
    """
    # Score original
    orig_result = _hc.score_text(draft_text)

    # Mechanical pre-fix (vocab/filler fixes — no LLM needed)
    fixed_text, mechanical_changes = _hc.apply_mechanical_fixes(draft_text)

    # LLM rewrite via Ollama
    humanized = _ollama_humanize(fixed_text, style=style)

    # Score result
    hum_result = _hc.score_text(humanized)

    # Build summary
    score_diff = hum_result["score"] - orig_result["score"]
    direction = "\u2191" if score_diff > 0 else ("\u2193" if score_diff < 0 else "\u2192")
    summary = (
        f"AI score: {orig_result['score']}\u2192{hum_result['score']} {direction}{abs(score_diff):.0f}pts | "
        f"Mechanical fixes: {len(mechanical_changes)}"
    )

    return {
        "original_score": orig_result["score"],
        "humanized_score": hum_result["score"],
        "original_verdict": "AI",
        "humanized_verdict": "HUMAN" if hum_result["score"] < orig_result["score"] else "MIXED",
        "humanized_text": humanized,
        "changes_summary": summary,
        "mechanical_changes": mechanical_changes,
    }

# ============================================================================
# CONFIG
# ============================================================================

# Add rankbuilder root to path so 'lib.pitch_templates' resolves
import sys as _sys_lib
_sys_lib.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Brand context — imported from pitch_templates to avoid duplication
from lib.pitch_templates import BRAND_BIO, BRAND_VOICE

TARGET_KEYWORDS = [
    # === CORE PRODUCTS ===
    "shutters", "fly screen", "flyscreen", "window screens", "door screens",
    "security shutters", "storm shutters", "outdoor blinds", "roller shutters",
    "vertical screens", "vertical blinds", "zebra blinds", "panel blinds",
    "plantation shutters", "hurricane shutters", "folding shutters", "sliding shutters",
    "motorized shutters", "electric shutters", "smart shutters", "battery shutters",
    "retractable screens", "retractable blinds", "zip track", "zip screen",
    "aluminum shutters", "wood shutters", "pvc shutters", "composite shutters",
    # === WINDOW & DOOR SOLUTIONS ===
    "aluminum doors", "aluminum windows", "window replacements", "door replacements",
    "security doors", "security screens", "security gates", "safety doors",
    "flyscreen doors", "mesh screens", "pet screens", "pool fencing", "pool screens",
    "window security", "door security", "window coverings", "door coverings",
    # === HOME IMPROVEMENT ===
    "home improvement", "home renovation", "home remodeling", "home upgrade",
    "home exterior", "exterior shutters", "interior shutters", "window treatments",
    "window dressing", "blinds and shutters", "awnings and shutters", "renovation contractor",
    # === OUTDOOR & LIFESTYLE ===
    "patio covers", "patio enclosures", "balcony screens", "deck shutters",
    "pergola", "veranda", "outdoor living", "outdoor entertaining",
    "sun shading", "sun control", "shade sails", "shade structures",
    "pool enclosures", "braai area", "outdoor kitchen", "patio shade",
    # === CLIMATE & ENERGY ===
    "heat reduction", "energy efficiency", "cooling costs", "home insulation",
    "UV protection", "sun protection", "heat management", "thermal efficiency",
    "hurricane preparedness", "storm preparedness", "storm protection", "weather protection",
    "wind protection", "rain protection", "coastal shutters", "salt air resistant",
    # === SECURITY & SAFETY ===
    "home security", "home safety", "break-in prevention", "burglary prevention",
    "child safety windows", "pet safety windows", "window safety", "home protection",
    # === PEST & COMFORT ===
    "pest control", "insect protection", "ventilation", "privacy solutions",
    "privacy screen", "privacy shutters", "pool safety", "mosquito screens",
    # === INSTALLATION & TRADE ===
    "diy", "home maintenance", "window installation", "door installation",
    "shutter installation", "awning installation", "screen repair", "window repair",
    # === REGIONAL MARKETS ===
    "south africa", "australian shutters", "florida shutters", "texas shutters",
    "california windows", "coastal living", "tropical homes", "subtropical climate",
    # === GARAGE & ACCESS ===
    "garage doors", "garage shutters", "carport", "car port", "carport cover",
    # === MATERIALS & DURABILITY ===
    "powder coating", "aluminum construction", "impact resistant", "corrosion resistant",
    "UV resistant", "marine grade", "coastal grade", "durability", "low maintenance",
    # === GENERAL CATCH-ALLS ===
    "awnings", "canopy", "shade sail", "external blinds", "external shutters"
]

EXCLUDED_KEYWORDS = [
    "crypto", "bitcoin", "blockchain", "flight", "airline", "travel agent",
    "ornithologist", "bird", "chef", "louisiana", "bookshop", "coffee shop",
    "barista", "sex life", "interview", "podcast", "chicken", "recipe",
    "FDA", "oncologist", "vitamin", "dermatologist", "anti-aging", "mental health"
]


# ============================================================================
# EMAIL PARSING (via himalaya CLI)
# ============================================================================

def get_unread_envelopes():
    """Get list of envelopes from himalaya (v2 --json format)."""
    result = subprocess.run(
        ["himalaya", "envelope", "list", "--json"],
        capture_output=True, text=True, cwd=Path.home()
    )
    if result.returncode != 0:
        return []

    envelopes = []
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return envelopes

    for env in data.get("envelopes", []):
        if not isinstance(env, dict):
            continue
        env_id = str(env.get("id", "")).strip()
        if not env_id.isdigit():
            continue
        flags = [f.get("iana", "") for f in (env.get("flags") or []) if isinstance(f, dict)]
        envelopes.append({
            'id': env_id,
            'flags': ",".join(flags),
            'subject': env.get("subject", "") or "",
            'date': env.get("date", "") or ""
        })
    return envelopes


def read_email(email_id: str) -> str:
    """Read full email body via himalaya (v2 --json, extracts text_body)."""
    result = subprocess.run(
        ["himalaya", "message", "read", email_id, "--json"],
        capture_output=True, text=True, cwd=Path.home()
    )
    if result.returncode != 0:
        return ""
    try:
        data = json.loads(result.stdout)
        body = data.get("text_body") or ""
        return body if isinstance(body, str) else str(body)
    except (json.JSONDecodeError, TypeError):
        # fallback: raw stdout
        return result.stdout


def extract_forwarded_haro_content(email_body: str) -> Optional[dict]:
    """
    Extract HARO query from a forwarded email.
    Returns dict with: journalist_name, outlet, category, deadline, query_text, reply_to
    """
    # Check if this is a HARO forward
    if 'helpareporter.com' not in email_body.lower() and 'HARO' not in email_body:
        return None
    
    data = {}
    
    # Extract journalist name - look for "Name: Name" or similar patterns
    name_match = re.search(r'Name:\s*(.+?)(?:\n|Email:|$)', email_body, re.IGNORECASE | re.DOTALL)
    if name_match:
        data['journalist_name'] = name_match.group(1).strip()
    
    # Extract outlet
    outlet_match = re.search(r'Media Outlet:\s*(.+?)(?:\n|https://|$)', email_body, re.IGNORECASE | re.DOTALL)
    if outlet_match:
        data['outlet'] = outlet_match.group(1).strip()
        # Remove URL if present
        data['outlet'] = re.sub(r'https?://\S+', '', data['outlet']).strip()
    
    # Extract category
    cat_match = re.search(r'Category:\s*(.+?)(?:\n|Query:|$)', email_body, re.IGNORECASE | re.DOTALL)
    if cat_match:
        data['category'] = cat_match.group(1).strip()
    
    # Extract deadline
    deadline_match = re.search(r'Deadline:\s*(.+?)(?:\n|Query:|$)', email_body, re.IGNORECASE | re.DOTALL)
    if deadline_match:
        data['deadline'] = deadline_match.group(1).strip()
    
    # Extract query text - between "Query:" and "Back to Top" or next query
    query_match = re.search(
        r'(?:Query|Query:)\s*(.+?)(?:\n\s*Back to Top|\n\s*-+|\n\s*\d+\))',
        email_body, re.IGNORECASE | re.DOTALL
    )
    if query_match:
        data['query_text'] = query_match.group(1).strip()
    
    # Extract reply-to email - HARO uses reply+hash@helpareporter.com format
    reply_match = re.search(
        r'Email:\s*([^\s<>]+@helpareporter\.com[^\s<>]*)',
        email_body, re.IGNORECASE
    )
    if reply_match:
        data['reply_to'] = reply_match.group(1).strip()
    else:
        # Try generic email pattern
        reply_match = re.search(r'Email:\s*([^\s\n<>]+@[^\s\n<>]+)', email_body, re.IGNORECASE)
        if reply_match:
            data['reply_to'] = reply_match.group(1).strip()
    
    # Extract HARO journalist profile URL
    profile_match = re.search(
        r'Journalist Profile URL:\s*(https?://[^\s\n]+)',
        email_body, re.IGNORECASE
    )
    if profile_match:
        data['journalist_profile'] = profile_match.group(1).strip()
    
    # Summary field
    summary_match = re.search(
        r'\d+\)\s*Summary:\s*(.+?)(?:\n|Name:|Category:|$)',
        email_body, re.IGNORECASE | re.DOTALL
    )
    if summary_match:
        data['summary'] = summary_match.group(1).strip()
    
    return data if data.get('query_text') else None


# ============================================================================
# RELEVANCE FILTERING
# ============================================================================

def is_relevant_query(query_data: dict) -> bool:
    """Check if query is relevant to Fortress Blinds / home improvement."""
    text = ' '.join([
        query_data.get('summary', ''),
        query_data.get('query_text', ''),
        query_data.get('category', ''),
        query_data.get('outlet', '')
    ]).lower()
    
    # Check excluded keywords first
    for kw in EXCLUDED_KEYWORDS:
        if kw.lower() in text:
            return False
    
    # Check for target keywords
    matches = sum(1 for kw in TARGET_KEYWORDS if kw.lower() in text)
    return matches >= 1


def score_relevance(query_data: dict) -> int:
    """Score query relevance 0-100."""
    text = ' '.join([
        query_data.get('summary', ''),
        query_data.get('query_text', ''),
        query_data.get('category', '')
    ]).lower()
    
    score = 0
    for kw in TARGET_KEYWORDS:
        if kw.lower() in text:
            score += 20
    
    # Home improvement context bonus
    if any(w in text for w in ['home', 'house', 'property', 'renovation']):
        score += 15
    
    # South Africa bonus (local relevance)
    if 'south africa' in text or 'sa' in text:
        score += 10
    
    return min(score, 100)


# ============================================================================
# RESPONSE DRAFTING (via Claude API)
# ============================================================================

def draft_response(query_data: dict, api_key: str) -> str:
    """Use Claude to draft a HARO response."""
    prompt = f"""You are drafting a professional response to a HARO (Help A Reporter Out) query.

## JOURNALIST DETAILS
- Name: {query_data.get('journalist_name', 'Unknown')}
- Outlet: {query_data.get('outlet', 'Unknown')}
- Profile: {query_data.get('journalist_profile', 'N/A')}

## QUERY
{query_data.get('query_text', 'No query text found')}

## DEADLINE
{query_data.get('deadline', 'Not specified')}

## BRAND BIO (your client)
{BRAND_BIO}

## BRAND VOICE
{BRAND_VOICE}

## TASK
Write a compelling, journalist-friendly response that:
1. Addresses the query directly with valuable insights
2. Positions Craig Pauls as a knowledgeable South African expert
3. Is 150-300 words
4. Includes a 2-sentence author bio at the end
5. Offers additional value (e.g., to provide more details, photos, etc.)
6. Uses a professional but approachable tone

## RESPONSE FORMAT
Subject line: (brief, professional)

Body:
[Your response here - direct answers to the query, expert insights, then author bio]

---
Author: Craig Pauls, Fortress Blinds (South Africa)
Website: https://fortressblinds.co.za
Contact: craig@fortressblinds.co.za

Write ONLY the response. No preamble. No explanation."""

    # Call Claude API
    import urllib.request
    import urllib.error
    
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response = json.loads(resp.read().decode('utf-8'))
            return response['content'][0]['text']
    except urllib.error.HTTPError as e:
        return f"Error calling Claude API: {e.read()}"
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================================================
# HUMANIZER INTEGRATION
# ============================================================================



def format_approval_email(query_data: dict, draft: str, humanization: dict) -> str:
    """
    Format the approval email sent to Craig, including humanization score.
    
    Args:
        query_data: Parsed HARO query data.
        draft: The LLM-drafted response.
        humanization: Output from humanize_draft().
    
    Returns:
        Formatted email body string.
    """
    original_score = humanization['original_score']
    humanized_score = humanization['humanized_score']
    original_verdict = humanization['original_verdict'].upper()
    humanized_verdict = humanization['humanized_verdict'].upper()
    
    # Emoji indicators
    verdict_emoji = {'HUMAN': '✅', 'MIXED': '⚠️', 'AI': '🤖'}
    orig_icon = verdict_emoji.get(original_verdict, '❓')
    human_icon = verdict_emoji.get(humanized_verdict, '❓')
    
    email = f"""📧 HARO Response Draft — Approval Needed

📰 JOURNALIST: {query_data.get('journalist_name', 'Unknown')}
🏢 OUTLET: {query_data.get('outlet', 'Unknown')}
📂 CATEGORY: {query_data.get('category', 'Unknown')}
⏰ DEADLINE: {query_data.get('deadline', 'Unknown')}

--- ORIGINAL QUERY ---
{query_data.get('query_text', 'No query text')[:500]}

--- HUMANIZATION REPORT ---
{orig_icon} Original AI score: {original_score}/100 ({original_verdict})
{human_icon} Humanized score: {humanized_score}/100 ({humanized_verdict})
📊 {humanization['changes_summary']}

--- DRAFTED RESPONSE (Humanized) ---
{humanization['humanized_text']}

---
Reply YES to approve and submit, or NO to skip.
"""
    return email


# ============================================================================
# MAIN TEST
# ============================================================================

if __name__ == "__main__":
    print("=== HARO Responder Library ===")
    print(f"Target keywords: {len(TARGET_KEYWORDS)}")
    print(f"Excluded keywords: {len(EXCLUDED_KEYWORDS)}")
    
    # Test envelope reading
    print("\n=== Recent Emails ===")
    envelopes = get_unread_envelopes()
    for env in envelopes[:5]:
        print(f"  [{env['id']}] {env['subject']}")
    
    # Test parsing a HARO email if we have one
    if len(sys.argv) > 1:
        email_id = sys.argv[1]
        print(f"\n=== Parsing email {email_id} ===")
        body = read_email(email_id)
        data = extract_forwarded_haro_content(body)
        if data:
            print(f"Journalist: {data.get('journalist_name')}")
            print(f"Outlet: {data.get('outlet')}")
            print(f"Category: {data.get('category')}")
            print(f"Deadline: {data.get('deadline')}")
            print(f"Reply-to: {data.get('reply_to')}")
            print(f"Query: {data.get('query_text', '')[:200]}...")
            print(f"Relevant: {is_relevant_query(data)}")
            print(f"Relevance score: {score_relevance(data)}")
        else:
            print("Not a HARO query")