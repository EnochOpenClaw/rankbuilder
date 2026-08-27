#!/usr/bin/env python3
"""
humanize-cli.py — Mechanical AI pattern fixes + scoring
Run standalone: python humanize_cli.py --text "Your AI text here"
Or pipe text: cat draft.txt | python humanize_cli.py
"""

import re
import sys
import json
import argparse
from typing import List, Tuple

# ---------------------------------------------------------------------------
# AI Vocabulary — Tier 1 (highest priority to remove/replace)
# ---------------------------------------------------------------------------
AI_VOCAB_TIER1 = {
    "delve into": "explore",
    "delving into": "exploring",
    "tapestry": "mix",
    "landscape": "field",
    "showcase": "show",
    "showcasing": "showing",
    "seamless": "smooth",
    "seamlessly": "smoothly",
    "robust": "strong",
    "dynamic": "active",
    "empower": "help",
    "empowering": "helping",
    "transform": "change",
    "transformative": "changing",
    "transforming": "changing",
    "elevate": "improve",
    "elevating": "improving",
    "revolutionize": "change significantly",
    "revolutionizing": "significantly changing",
    "cutting-edge": "current",
    "state-of-the-art": "modern",
    "groundbreaking": "new",
    "innovative": "new",
    "pioneering": "first",
    "best-in-class": "top",
    "world-class": "excellent",
    "unmatched": "the best",
    "unparalleled": "exceptional",
    "exceptional": "great",
    "outstanding": "great",
    "remarkable": "notable",
    "phenomenal": "impressive",
    "utilize": "use",
    "utilizes": "uses",
    "utilizing": "using",
    "utilization": "use",
    "leverage": "use",
    "leverages": "uses",
}

AI_ADVERBS = {
    "meticulously", "seamlessly", "flawlessly", "effortlessly",
    "brilliantly", "exceptionally", "profoundly", "immensely",
}

FILLER_PHRASES = [
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bdue to the fact that\b", re.I), "because"),
    (re.compile(r"\bat this point in time\b", re.I), "now"),
    (re.compile(r"\bin the realm of\b", re.I), "in"),
    (re.compile(r"\bit is worth noting that\b", re.I), ""),
    (re.compile(r"\bwhat it is important to note is that\b", re.I), ""),
    (re.compile(r"\bthe fact of the matter is that\b", re.I), ""),
    (re.compile(r"in today's rapidly evolving", re.I), "in"),
]

CHATBOT_ARTIFACTS = [
    "I hope this helps!",
    "Please let me know if you have any questions.",
    "Please let me know if you need anything else.",
    "Feel free to reach out if you have questions.",
    "Don't hesitate to reach out.",
    "Let me know if you have any questions!",
    "I'm happy to help!",
    "I'm excited to share that",
    "I'm thrilled to share that",
    "I'm delighted to announce that",
    "I wanted to reach out to you because",
]

ACKNOWLEDGMENT_LOOPS = [
    re.compile(r"You're asking about .+?\. ", re.I),
    re.compile(r"You've asked about .+?\. ", re.I),
    re.compile(r"Regarding your question about .+?\. ", re.I),
    re.compile(r"To answer your question about .+?\. ", re.I),
]

HEDGING_PATTERNS = [
    (re.compile(r"\bcould potentially\b", re.I), "could"),
    (re.compile(r"\bmight possibly\b", re.I), "might"),
    (re.compile(r"\bmight arguably\b", re.I), "might"),
    (re.compile(r"\bcould arguably\b", re.I), "could"),
    (re.compile(r"\bmay perhaps\b", re.I), "may"),
    (re.compile(r"\bperhaps potentially\b", re.I), "possibly"),
]

COPULA_AVOIDANCE = [
    (re.compile(r"\bserves as\b", re.I), "is"),
    (re.compile(r"\bboasts\b", re.I), "has"),
    (re.compile(r"\bfeatures\b", re.I), "has"),
    (re.compile(r"\bcomprises\b", re.I), "is"),
    (re.compile(r"\bencompasses\b", re.I), "includes"),
]

SIGNIFICANCE_INFLATION = [
    re.compile(r"\bpivotal moment\b", re.I),
    re.compile(r"\bturning point\b", re.I),
]

GENERIC_CONCLUSIONS = [
    re.compile(r"the future looks bright", re.I),
    re.compile(r"exciting times lie ahead", re.I),
    re.compile(r"the best is yet to come", re.I),
    re.compile(r"we're just getting started", re.I),
]

NEGATIVE_PARALLELISM = re.compile(r"It's not just \w+, it's \w+", re.I)

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def score_text(text: str) -> dict:
    """Score text on AI pattern density. Returns score 0-100 (higher = more AI-like)."""
    words = text.split()
    word_count = len(words)
    if word_count < 5:
        return {"score": 0, "word_count": word_count, "patterns_found": []}

    text_lower = text.lower()
    score = 0.0
    patterns_found = []

    # AI vocabulary
    vocab_hits = sum(1 for term in AI_VOCAB_TIER1 if term in text_lower)
    if vocab_hits > 0:
        density = vocab_hits / word_count * 100
        vocab_score = min(density * 8, 35)
        score += vocab_score
        patterns_found.append(f"AI vocabulary: {vocab_hits} hits ({vocab_score:.0f}pts)")

    # Filler phrases
    filler_hits = sum(1 for p, _ in FILLER_PHRASES if p.search(text))
    if filler_hits > 0:
        filler_score = min(filler_hits * 5, 15)
        score += filler_score
        patterns_found.append(f"Filler phrases: {filler_hits} hits ({filler_score:.0f}pts)")

    # Chatbot artifacts
    chatbot_hits = sum(1 for a in CHATBOT_ARTIFACTS if a.lower() in text_lower)
    if chatbot_hits > 0:
        chatbot_score = chatbot_hits * 8
        score += chatbot_score
        patterns_found.append(f"Chatbot artifacts: {chatbot_hits} ({chatbot_score:.0f}pts)")

    # Significance inflation
    sig_hits = sum(1 for p in SIGNIFICANCE_INFLATION if p.search(text))
    if sig_hits > 0:
        score += sig_hits * 6
        patterns_found.append(f"Significance inflation: {sig_hits} ({sig_hits*6:.0f}pts)")

    # Hedging
    hedge_hits = sum(1 for p, _ in HEDGING_PATTERNS if p.search(text))
    if hedge_hits > 0:
        score += hedge_hits * 4
        patterns_found.append(f"Excessive hedging: {hedge_hits} ({hedge_hits*4:.0f}pts)")

    # Generic conclusions
    gen_hits = sum(1 for p in GENERIC_CONCLUSIONS if p.search(text))
    if gen_hits > 0:
        score += gen_hits * 6
        patterns_found.append(f"Generic conclusions: {gen_hits} ({gen_hits*6:.0f}pts)")

    # Negative parallelisms
    neg_hits = len(NEGATIVE_PARALLELISM.findall(text))
    if neg_hits > 0:
        score += neg_hits * 5
        patterns_found.append(f"Negative parallelisms: {neg_hits}")

    # Em dash overuse
    em_dash_count = text.count("—")
    if em_dash_count >= 3:
        score += em_dash_count * 2
        patterns_found.append(f"Em dash overuse: {em_dash_count} ({em_dash_count*2:.0f}pts)")

    # Sentence length uniformity
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) >= 3:
        lengths = [len(s.split()) for s in sentences]
        avg = sum(lengths) / len(lengths)
        variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
        std_dev = variance ** 0.5
        coef_var = std_dev / avg if avg > 0 else 1
        if coef_var < 0.30:
            score += 15
            patterns_found.append(f"Mechanically uniform sentences (CV={coef_var:.2f}): +15pts")
        elif coef_var > 0.45:
            patterns_found.append(f"Natural sentence variation (CV={coef_var:.2f})")

    # Emoji
    emoji_count = len(re.findall(r"[\U0001F300-\U0001F9FF]", text))
    if emoji_count >= 3:
        score += emoji_count * 3
        patterns_found.append(f"Emoji overuse: {emoji_count} ({emoji_count*3:.0f}pts)")

    score = min(score, 100)
    return {"score": round(score, 1), "word_count": word_count, "patterns_found": patterns_found}


def apply_mechanical_fixes(text: str) -> Tuple[str, List[str]]:
    """Apply all mechanical (non-LLM) fixes. Returns (fixed_text, changes)."""
    changes = []
    fixed = text

    # 1. AI vocabulary replacements
    for old, new in AI_VOCAB_TIER1.items():
        pattern = re.compile(re.escape(old), re.I)
        if pattern.search(fixed):
            fixed = pattern.sub(new, fixed)
            changes.append(f"'{old}' → '{new}'")

    # 2. Filler phrases
    for pattern, replacement in FILLER_PHRASES:
        if pattern.search(fixed):
            count = len(pattern.findall(fixed))
            fixed = pattern.sub(replacement, fixed)
            changes.append(f"Filler '{pattern.pattern}' → '{replacement}' ({count}x)")

    # 3. Chatbot artifacts (sentence-level removal)
    for artifact in CHATBOT_ARTIFACTS:
        artifact_lower = artifact.lower()
        if artifact_lower in fixed.lower():
            # Replace whole sentence
            pattern = re.compile(r"\s*" + re.escape(artifact) + r"\s*", re.I)
            fixed = pattern.sub(" ", fixed)
            changes.append(f"Removed: '{artifact}'")

    # 4. Acknowledgment loops
    for pattern in ACKNOWLEDGMENT_LOOPS:
        if pattern.search(fixed):
            fixed = pattern.sub("", fixed)
            changes.append("Removed acknowledgment loop")

    # 5. Hedging
    for pattern, replacement in HEDGING_PATTERNS:
        if pattern.search(fixed):
            fixed = pattern.sub(replacement, fixed)
            changes.append(f"Hedging: '{pattern.pattern}' → '{replacement}'")

    # 6. Copula avoidance
    for pattern, replacement in COPULA_AVOIDANCE:
        if pattern.search(fixed):
            fixed = pattern.sub(replacement, fixed)
            changes.append(f"Copula: '{pattern.pattern}' → '{replacement}'")

    # 7. Significance inflation → plain
    for pattern in SIGNIFICANCE_INFLATION:
        if pattern.search(fixed):
            fixed = pattern.sub("important development", fixed)
            changes.append("Significance inflation → plain")

    # 8. Generic conclusions
    for pattern in GENERIC_CONCLUSIONS:
        if pattern.search(fixed):
            fixed = pattern.sub("", fixed)
            changes.append("Removed generic conclusion")

    # 9. Em dash clusters → reduce
    em_dash_count = fixed.count("—")
    if em_dash_count >= 3:
        # Replace 3+ consecutive em dashes with a period
        fixed = re.sub(r"—\s*—\s*—", ".", fixed)
        changes.append(f"Em dash cluster ({em_dash_count}) → reduced")

    # 10. Trim whitespace
    fixed = " ".join(fixed.split())

    return fixed, changes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="AI text humanizer — mechanical fixes + scoring"
    )
    parser.add_argument("--text", "-t", help="Text to humanize")
    parser.add_argument("--file", "-f", help="File to process")
    parser.add_argument("--score", "-s", action="store_true", help="Score only, no fixes")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all pattern detections")
    args = parser.parse_args()

    # Read input
    if args.file:
        with open(args.file) as f:
            text = f.read()
    elif args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.print_help()
        sys.exit(1)

    if args.score:
        result = score_text(text)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"AI Score: {result['score']}/100")
            if result["patterns_found"]:
                print("\nPatterns detected:")
                for p in result["patterns_found"]:
                    print(f"  - {p}")
            else:
                print("No obvious AI patterns detected.")
    else:
        fixed_text, changes = apply_mechanical_fixes(text)
        result = score_text(text)
        fixed_result = score_text(fixed_text)
        improvement = round(result["score"] - fixed_result["score"], 1)

        if args.json:
            print(json.dumps({
                "original_score": result["score"],
                "fixed_score": fixed_result["score"],
                "improvement": improvement,
                "changes": changes,
                "fixed_text": fixed_text,
            }, indent=2))
        else:
            print(f"Original AI Score: {result['score']}/100")
            print(f"After mechanical fixes: {fixed_result['score']}/100")
            print(f"Improvement: {improvement} points")
            if changes:
                print(f"\nFixes applied ({len(changes)}):")
                for c in changes:
                    print(f"  [ok] {c}")
            print(f"\n{'='*50}\nHUMANIZED TEXT:\n{'='*50}\n{fixed_text}")


if __name__ == "__main__":
    main()
