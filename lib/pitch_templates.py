#!/usr/bin/env python3
"""
Pitch Asset Library — Pre-approved expert angle templates for HARO/Connectively responses.
Each template is a callable that takes query_data and returns a crafted response,
or a dict with structure for the AI to flesh out.
"""

import re
from typing import Optional

# ============================================================================
# HOUSE OF SUPREME — BRAND CONTEXT
# ============================================================================

BRAND_BIO = (
    "Craig Pauls is the founder of House of Supreme, a South African company "
    "specialising in custom aluminium and wood shutters, flyscreen doors and windows, "
    "security shutters, outdoor blinds, and a full range of window and door solutions "
    "across South Africa. With years of hands-on industry experience, Craig brings "
    "practical, no-nonsense expertise to homeowners, architects, and developers."
)

BRAND_VOICE = (
    "Practical, no-nonsense, South African home improvement expert. "
    "Years of hands-on experience. Focused on quality, durability, and real value. "
    "Speaks to both trade professionals and homeowners."
)

EXPERT_SIGNATURE = """
---
Author: Craig Pauls, House of Supreme (South Africa)
Website: https://houseofsupreme.co.za | Contact: craig@houseofsupreme.co.za
"""

# ============================================================================
# PITCH ANGLES — each angle is a callable that returns response text
# ============================================================================

def angle_security(query_data: dict) -> str:
    """
    SECURITY & STORM PROTECTION angle.
    Use when query involves: home security, break-ins, storm protection,
    hurricane shutters, wind protection, weather protection, safety doors,
    security shutters, security gates, home safety, child safety.
    """
    return """REPLACE_WITH_DRAFT"""


def angle_energy_climate(query_data: dict) -> str:
    """
    ENERGY EFFICIENCY & CLIMATE angle.
    Use when query involves: heat reduction, energy efficiency, cooling costs,
    UV protection, sun control, thermal efficiency, heat management, home insulation,
    climate control, solar control, temperature regulation.
    """
    return """REPLACE_WITH_DRAFT"""


def angle_diy_homeowner(query_data: dict) -> str:
    """
    DIY & HOMEOWNER angle.
    Use when query involves: DIY, home maintenance, window installation,
    home improvement, home renovation, window replacement, door replacement,
    shutter installation, awning installation, screen repair, window repair.
    """
    return """REPLACE_WITH_DRAFT"""


def angle_aesthetics_design(query_data: dict) -> str:
    """
    AESTHETICS & HOME DESIGN angle.
    Use when query involves: interior shutters, exterior shutters, window coverings,
    window dressing, blinds and shutters, home exterior, home remodeling,
    home upgrade, renovation contractor, property upgrade, plantation shutters,
    coastal living, subtropical climate, tropical homes.
    """
    return """REPLACE_WITH_DRAFT"""


def angle_pest_comfort(query_data: dict) -> str:
    """
    PEST CONTROL & COMFORT angle.
    Use when query involves: pest control, insect protection, flyscreen, fly screen,
    mosquito screens, mesh screens, ventilation, privacy solutions, privacy screen,
    pool safety, pet screens, outdoor entertaining, outdoor living.
    """
    return """REPLACE_WITH_DRAFT"""


def angle_outdoor_living(query_data: dict) -> str:
    """
    OUTDOOR LIVING & LIFESTYLE angle.
    Use when query involves: patio covers, patio enclosures, balcony screens,
    outdoor living, outdoor entertaining, deck shutters, pergola, veranda,
    shade sails, shade structures, outdoor kitchen, braai area, pool enclosures,
    carport, garage doors.
    """
    return """REPLACE_WITH_DRAFT"""


def angle_regional_climate(query_data: dict) -> str:
    """
    REGIONAL CLIMATE angle — South African context.
    Use when query mentions or implies: South Africa, Australian climate, Florida,
    Texas, California, coastal living, tropical homes, subtropical climate,
    salt air, coastal grade, marine grade, heat, humidity.
    """
    return """REPLACE_WITH_DRAFT"""


def angle_durability_materials(query_data: dict) -> str:
    """
    DURABILITY & MATERIALS angle.
    Use when query involves: aluminium construction, powder coating, impact resistant,
    corrosion resistant, UV resistant, low maintenance, durability, coastal shutters,
    storm shutters, hurricane shutters, weather protection, salt air resistant,
    marine grade, composite shutters, PVC shutters.
    """
    return """REPLACE_WITH_DRAFT"""


def angle_general_home_improvement(query_data: dict) -> str:
    """
    GENERAL HOME IMPROVEMENT angle — default fallback.
    Use when no specific angle matches above, but query is broadly relevant
    to home improvement, shutters, windows, doors, outdoor living.
    """
    return """REPLACE_WITH_DRAFT"""


# ============================================================================
# TEMPLATE DISPATCHER
# ============================================================================

# Ordered list of (keyword_list, angle_function) tuples.
# First matching angle wins. General fallback is always last.
ANGLE_RULES = [
    # Security / storm
    (
        ["security", "burglary", "break-in", "safety", "storm", "hurricane",
         "wind protection", "weather protection", "security shutter", "security door",
         "security gate", "safety door", "child safety", "pet safety"],
        angle_security
    ),
    # Energy / climate
    (
        ["energy", "heat reduction", "cooling", "uv", "sun control", "thermal",
         "insulation", "climate control", "solar", "temperature", "heat management"],
        angle_energy_climate
    ),
    # DIY / homeowner
    (
        ["diy", "home maintenance", "installation", "window replacement",
         "door replacement", "shutter installation", "awning installation",
         "screen repair", "window repair", "renovation contractor"],
        angle_diy_homeowner
    ),
    # Aesthetics / design
    (
        ["interior", "exterior", "design", "aesthetic", "remodel", "upgrade",
         "plantation shutter", "window covering", "window dressing", "home exterior",
         "coastal living", "tropical", "subtropical"],
        angle_aesthetics_design
    ),
    # Pest / comfort
    (
        ["pest", "insect", "flyscreen", "fly screen", "mosquito", "mesh",
         "ventilation", "privacy", "pool safety", "pet screen", "outdoor living",
         "outdoor entertaining"],
        angle_pest_comfort
    ),
    # Outdoor living
    (
        ["patio", "balcony", "deck", "pergola", "veranda", "shade sail",
         "outdoor kitchen", "braai", "pool enclosure", "carport", "garage"],
        angle_outdoor_living
    ),
    # Durability / materials (check before regional — "coastal" can match both)
    (
        ["aluminium", "aluminum", "powder coat", "impact", "corrosion",
         "uv resistant", "low maintenance", "durability", "composite", "pvc",
         "material", "shutter material", "best material"],
        angle_durability_materials
    ),
    # Regional / climate context
    (
        ["south africa", "australian", "florida", "texas", "california",
         "salt air", "coastal", "marine", "humidity", "tropical"],
        angle_regional_climate
    ),
    # General fallback
    (
        ["shutter", "blind", "screen", "window", "door", "awning",
         "home improvement", "renovation"],
        angle_general_home_improvement
    ),
]


# ============================================================================
# ANGLE GUIDANCE EXTRACTOR
# ============================================================================

def get_angle_guidance(angle_fn) -> str:
    """
    Extract the real guidance text from an angle function's docstring.
    Returns the "Use when query involves: ..." section as a usable string.
    """
    doc = angle_fn.__doc__ or ""
    # Extract "Use when query involves: ..." block
    match = re.search(r'Use when query involves:\s*(.+?)(?:\n    \"\"\"|\n    #|\Z)', doc, re.DOTALL)
    if match:
        return match.group(1).strip()
    return doc.strip()


def select_angle(query_text: str, summary: str = "") -> str:
    """
    Scan query text and return the name of the best-matching angle function.
    Returns the function name as a string.
    """
    text = (query_text + " " + summary).lower()

    for keywords, angle_fn in ANGLE_RULES:
        for kw in keywords:
            if kw.lower() in text:
                return angle_fn.__name__

    return "angle_general_home_improvement"


def get_angle_for_query(query_data: dict):
    """Return the angle function best suited for this query."""
    query_text = query_data.get("query_text", "")
    summary = query_data.get("summary", "")
    angle_name = select_angle(query_text, summary)

    for keywords, angle_fn in ANGLE_RULES:
        if angle_fn.__name__ == angle_name:
            return angle_fn

    return angle_general_home_improvement


def get_angle_name_and_guidance(query_data: dict) -> tuple:
    """
    Return (angle_name, angle_guidance_text) for a given query.
    Use this when building prompts — it gives the AI concrete guidance to work with.
    """
    angle_fn = get_angle_for_query(query_data)
    angle_name = angle_fn.__name__
    guidance = get_angle_guidance(angle_fn)
    return angle_name, guidance


# ============================================================================
# RESPONSE BUILDER
# ============================================================================

def build_pitch_response(query_data: dict, drafted_text: str) -> str:
    """
    Given a raw drafted response and query metadata, refine and polish it
    using the selected pitch angle as context. This is the final polish step.
    Adds word count discipline (150-250 words) and angle-specific emphasis.
    """
    angle_fn = get_angle_for_query(query_data)
    angle_name = angle_fn.__name__
    angle_guidance = get_angle_guidance(angle_fn)

    prompt = f"""You are refining a HARO/Connectively pitch response for a journalist query.

## QUERY
{query_data.get('query_text', '')}

## JOURNALIST DETAILS
- Name: {query_data.get('journalist_name', 'Unknown')}
- Outlet: {query_data.get('outlet', 'Unknown')}
- Deadline: {query_data.get('deadline', 'Not specified')}

## PITCH ANGLE: {angle_name}
## Angle guidance (use this to frame your response):
{angle_guidance}

## RAW DRAFT (before refinement)
{drafted_text}

## BRAND BIO
{BRAND_BIO}

## YOUR TASK
1. Read the raw draft above
2. Refine it so it strongly emphasises the "{angle_name}" angle
3. STRICTLY keep it to 150-250 words (count yours before finishing)
4. Make it journalist-friendly, punchy, and valuable — not a sales pitch
5. Include the expert signature at the end

## FORMAT
Write ONLY the refined email response. No preamble. No explanation.

Start with a brief professional greeting addressing the journalist by name if known.

{EXPERT_SIGNATURE}"""

    import json
    import urllib.request
    import urllib.error

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
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('response', '').strip()
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================================================
# PRE-BUILT TEMPLATE RESPONSES (for common query patterns)
# These are ready-to-send as-is, no AI needed
# ============================================================================

GENERIC_SCREEN_SHUTTER_PITCH = """Hi {journalist_name},

Thank you for the query — I'd love to contribute.

When it comes to {topic}, homeowners are increasingly looking for solutions that tick multiple boxes: security, comfort, aesthetics, and long-term durability. That's exactly what we specialise in at House of Supreme.

{angle_specific_content}

With {years_experience} years in the industry, we've seen what works — and what doesn't — in South African conditions, from coastal salt air to inland heat. We supply and install across the country and work with architects, developers, and homeowners directly.

I'm happy to provide more details, case studies, product specifications, or high-resolution images to support the piece.

Looking forward to contributing.

{EXPERT_SIGNATURE}"""

# ============================================================================
# MAIN TEST
# ============================================================================

if __name__ == "__main__":
    print("=== Pitch Asset Library ===")
    print(f"Angle rules loaded: {len(ANGLE_RULES)}")
    print("\nAngles:")
    for _, fn in ANGLE_RULES:
        print(f"  - {fn.__name__}: {fn.__doc__.split(chr(10))[0] if fn.__doc__ else 'No description'}")

    # Test angle selection
    test_queries = [
        ("My windows need security shutters - live in hurricane zone", ""),
        ("How can I reduce my cooling costs this summer?", ""),
        ("Thinking of installing plantation shutters in my home", ""),
        ("Need to keep mosquitoes out this summer - patio enclosure ideas?", ""),
        ("Building a deck and want some shade solutions", ""),
        ("What's the best material for coastal shutters in Durban?", ""),
    ]
    print("\n=== Angle Selection Tests ===")
    for q, s in test_queries:
        angle = select_angle(q, s)
        print(f"  Query: '{q[:50]}...'")
        print(f"  → Angle: {angle}\n")
