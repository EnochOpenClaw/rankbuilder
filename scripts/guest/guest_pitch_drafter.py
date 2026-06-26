#!/usr/bin/env python3
"""
Guest Pitch Drafter
Takes a prospect from the DB, uses Ollama to draft a personalized pitch email,
saves it for Craig's review before sending.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib"))
from credentials import BREVO_API_KEY, SENDER_EMAIL, SENDER_NAME

# ============================================================================
# CONFIG
# ============================================================================

PROSPECTS_DIR = Path(__file__).parent.parent.parent / "prospects"
PROSPECT_DB = PROSPECTS_DIR / "prospect_db.json"
PITCHES_DIR = PROSPECTS_DIR / "pitches"
PITCHES_DIR.mkdir(exist_ok=True)

# Fortress Blinds brand context for pitch generation
BRAND_CONTEXT = {
    "company": "Fortress Blinds",
    "founder": "Craig Pauls",  # Use 'manager' in pitch emails
    "location": "South Africa",
    "website": "https://fortressblinds.co.za",
    "email": "craig@fortressblinds.co.za",
    "specialties": [
        "Custom aluminium shutters",
        "Security shutters and outdoor blinds",
        "Flyscreen doors and windows",
        "Aluminum door and window openings",
        "Residential and commercial installations",
    ],
    "unique_angle": (
        "South African climate expertise — coastal salt air resistance, "
        "heat/UV management, storm protection. 25+ years of hands-on experience. "
        "Works with homeowners, architects, and developers."
    ),
    "topics_offered": [
        ("shutters", [
            "The complete guide to choosing the right shutters for South African homes",
            "Aluminum vs wood shutters: what works best in coastal conditions",
            "Security shutters: peace of mind without sacrificing aesthetics",
            "Motorized vs manual shutters: is automation worth the investment?",
        ]),
        ("flyscreen", [
            "Why flyscreen doors are essential for South African outdoor living",
            "Pet-safe flyscreen solutions: keep your pets in, pests out",
            "How to choose the right mesh for your climate zone",
        ]),
        ("outdoor", [
            "Creating the perfect outdoor entertainment area in SA",
            "Outdoor blinds vs shutters: what's the difference?",
            "Shade solutions for South African summers: what actually works",
            "Patio enclosures: extending your living space year-round",
        ]),
        ("energy", [
            "How shutters can reduce your cooling costs by up to 40%",
            "Thermal efficiency: the often-overlooked benefit of quality shutters",
            "Energy-efficient windows and doors: where to invest your budget",
        ]),
        ("security", [
            "Home security in 2026: what homeowners are prioritizing",
            "Security shutters vs security bars: a practical comparison",
            "Child and pet safety with window screens: what parents need to know",
        ]),
    ]
}

# ============================================================================
# STATE
# ============================================================================

def load_prospect_db() -> dict:
    if PROSPECT_DB.exists():
        return json.loads(PROSPECT_DB.read_text())
    return {"prospects": {}, "pitches_sent": []}

def load_pitches() -> list:
    pitches = []
    for f in PITCHES_DIR.glob("pitch_*.json"):
        pitches.append(json.loads(f.read_text()))
    return sorted(pitches, key=lambda x: x.get("created_at", ""), reverse=True)

# ============================================================================
# PITCH GENERATION — via Ollama
# ============================================================================

def generate_pitch(prospect: dict, topic: str = None) -> dict:
    """
    Use Ollama to generate a personalized guest post pitch.
    Returns dict with: subject, body, topic_used, suggested_article_title
    """
    domain = urlparse(prospect["url"]).netloc
    page_title = prospect.get("page_title", domain)
    contact_email = prospect.get("contact_email", "")
    topics = prospect.get("topics", [])
    da = prospect.get("da_estimate", "?")
    score = prospect.get("score", 0)
    
    # Auto-select best topic if not specified
    if not topic:
        topic = topics[0] if topics else "home improvement"
    
    # Get article ideas for this topic
    article_options = None
    for t, ideas in BRAND_CONTEXT["topics_offered"]:
        if t in topic.lower() or any(t in top.lower() for top in topics):
            article_options = ideas
            break
    
    if not article_options:
        article_options = BRAND_CONTEXT["topics_offered"][0][1]  # Default to shutters
    
    article_options_str = "\n".join(f"- {idea}" for idea in article_options)
    
    prompt = f"""You are drafting a guest post pitch email for a South African home improvement expert.

## THE WEBSITE WE'RE PITCHING
- Domain: {domain}
- Page: {page_title}
- Domain Authority estimate: {da}
- Accepted topics: {', '.join(topics) if topics else 'home improvement'}
- Contact email: {contact_email}

## ABOUT OUR CLIENT
Craig Pauls is the manager at {BRAND_CONTEXT['company']}, a South African company specializing in:
{chr(10).join(f'  - {s}' for s in BRAND_CONTEXT['specialties'])}

Website: {BRAND_CONTEXT['website']}
Unique angle: {BRAND_CONTEXT['unique_angle']}

## ARTICLE IDEAS WE CAN WRITE (choose the best fit or propose your own)
{article_options_str}

## YOUR TASK
Draft a professional, personalized guest post pitch email that:
1. Has a compelling subject line (under 60 chars, no spamminess)
2. Opens with a genuine, specific compliment about their site (1-2 sentences)
3. Briefly introduces Craig as a South African home improvement expert
4. Proposes 1-2 specific article ideas from the list above (or a relevant alternative)
5. Highlights why this article would resonate with their audience
6. Includes a short author bio (2-3 sentences)
7. Ends with a clear, low-pressure call to action
8. Feels personal, not mass-emailed

## TONE
Professional, warm, confident. Not salesy. Just a knowledgeable person offering real value.

## OUTPUT FORMAT
Return JSON with these exact fields:
{{
  "subject": "subject line here",
  "greeting": "Hi [name or 'there']",
  "body": "full email body here",
  "article_proposal": "title of article idea",
  "author_bio": "2-3 sentence bio",
  "signoff": "Kind regards"
}}

Write only valid JSON. No markdown. No explanation. Start with {{ and end with }}."""

    # Call Ollama
    import urllib.request
    import urllib.error
    try:
        payload = json.dumps({
            "model": "kimi-k2.6:cloud",
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.8, "num_predict": 1024}
        }).encode('utf-8')
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
        text = result.get("response", "").strip()

        # Try to extract JSON from response
        # Some models wrap in markdown code blocks
        text = re.sub(r'^```json\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^```\s*', '', text)
        text = text.strip().rstrip('```').rstrip()

        return json.loads(text)
    except Exception as e:
        return {
            "error": str(e),
            "raw_response": text[:500] if 'text' in dir() else '',
            "subject": f"Guest post idea — {domain}",
            "body": f"Could not generate pitch: {e}",
            "article_proposal": "See raw response",
        }

# ============================================================================
# BUILD PITCH — for a specific prospect
# ============================================================================

def build_pitch_for_prospect(prospect_url: str, topic: str = None) -> dict:
    """
    Find prospect in DB, generate pitch, save to pitches dir.
    Returns the pitch dict.
    """
    db = load_prospect_db()
    prospect = db["prospects"].get(prospect_url)
    
    if not prospect:
        print(f"Prospect not found: {prospect_url}")
        return None
    
    print(f"Generating pitch for: {prospect_url}")
    print(f"  DA: {prospect.get('da_estimate')} | Score: {prospect.get('score')}")
    print(f"  Topics: {', '.join(prospect.get('topics', []))}")
    
    pitch_data = generate_pitch(prospect, topic)
    
    pitch_record = {
        "prospect_url": prospect_url,
        "prospect_score": prospect.get("score", 0),
        "prospect_da": prospect.get("da_estimate", 0),
        "contact_email": prospect.get("contact_email", ""),
        "article_proposal": pitch_data.get("article_proposal", ""),
        "subject": pitch_data.get("subject", ""),
        "greeting": pitch_data.get("greeting", "Hi there"),
        "body": pitch_data.get("body", ""),
        "author_bio": pitch_data.get("author_bio", ""),
        "signoff": pitch_data.get("signoff", "Kind regards"),
        "created_at": datetime.now().isoformat(),
        "status": "draft",  # draft → pending → approved → sent
        "error": pitch_data.get("error", ""),
    }
    
    # Save pitch
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', urlparse(prospect_url).netloc)
    pitch_file = PITCHES_DIR / f"pitch_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    pitch_file.write_text(json.dumps(pitch_record, indent=2))
    
    print(f"\n  Pitch saved: {pitch_file.name}")
    print(f"  Article: {pitch_record['article_proposal']}")
    print(f"  Subject: {pitch_record['subject']}")
    
    return pitch_record

# ============================================================================
# LIST / SHOW PITCHES
# ============================================================================

def list_pitches(status: str = None):
    pitches = load_pitches()
    if status:
        pitches = [p for p in pitches if p.get("status") == status]
    
    print(f"\n=== Pitches ({len(pitches)} total) ===")
    for p in pitches:
        status_flag = f"[{p.get('status','?').upper()}]"
        print(f"  {status_flag} {p.get('subject','no subject')}")
        print(f"         → {p.get('article_proposal','no topic')} | {p.get('prospect_url','')[:50]}")
        print(f"         Created: {p.get('created_at','')[:16]}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Guest Pitch Drafter")
    parser.add_argument("--prospect", "-p", type=str,
                        help="Prospect URL to generate pitch for")
    parser.add_argument("--topic", "-t", type=str,
                        help="Specific topic to pitch")
    parser.add_argument("--all", action="store_true",
                        help="Generate pitches for all prospects with score >= 60")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List all pitches")
    parser.add_argument("--status", "-s", type=str,
                        help="Filter pitches by status (draft/pending/approved/sent)")
    
    args = parser.parse_args()
    
    if args.list or args.status:
        list_pitches(args.status)
    elif args.all:
        db = load_prospect_db()
        print(f"Generating pitches for top prospects (score >= 60)...")
        count = 0
        for url, prospect in db["prospects"].items():
            if prospect.get("score", 0) >= 60:
                build_pitch_for_prospect(url, args.topic)
                count += 1
        print(f"\nDone. {count} pitches generated.")
    elif args.prospect:
        result = build_pitch_for_prospect(args.prospect, args.topic)
        if result:
            print("\n=== Generated Pitch ===")
            print(f"Subject: {result['subject']}")
            print(f"Article: {result['article_proposal']}")
            print(f"\n{result['greeting']},\n\n{result['body']}\n\n{result['author_bio']}\n\n{result['signoff']},\nCraig Pauls")
    else:
        print("Usage:")
        print("  --prospect <url>  Generate pitch for specific prospect")
        print("  --all             Generate pitches for all top prospects")
        print("  --list            List all pitches")
        print("  --status <s>      Filter by status (draft/pending/approved/sent)")
        print("\nRun with --status draft to see pitches awaiting Craig's review.")