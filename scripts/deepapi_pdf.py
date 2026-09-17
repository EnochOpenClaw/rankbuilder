#!/usr/bin/env python3
"""
DeepAPI PDF Extraction — powered by DeepAPI.
Extracts text from PDFs (supplier catalogs, spec sheets, contracts).

Usage:
    python deepapi_pdf.py <url> [-o output.txt]    # Extract PDF from URL
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from deepapi import call, get_balance


def extract_pdf(url):
    """Extract text from a PDF via DeepAPI. Output is list of page objects."""
    result = call("/v1/scrape/pdf", {"url": url})
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="PDF URL to extract")
    ap.add_argument("-o", "--output", help="Output text file")
    args = ap.parse_args()

    print(f"📄 Extracting PDF | Balance: ${get_balance():.2f}")
    result = extract_pdf(args.url)
    print(f"  status: {result.get('status')} | cost: {result.get('debitMicrousd')} micro-USD")
    if result.get("error"):
        print(f"  error: {result['error']}")
        return

    out = result.get("output")
    print(f"  output type: {type(out)}")

    # Extract text
    pages_text = []
    if isinstance(out, list):
        for page in out:
            if isinstance(page, dict):
                text = page.get("text") or page.get("markdown") or ""
                pages_text.append(text)
    elif isinstance(out, dict):
        pages_text.append(str(out.get("text") or out.get("markdown") or out))

    full_text = "\n\n".join([t for t in pages_text if t])
    print(f"  extracted {len(full_text)} chars")

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(full_text)
        print(f"  💾 Saved to {args.output}")
    else:
        print("\n--- Content ---")
        print(full_text[:2000])


if __name__ == "__main__":
    main()
