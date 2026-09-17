#!/usr/bin/env python3
"""
DeepAPI Email — send + manage email via DeepAPI.
Requires an inbox identity to be set up first (see setup note below).

SETUP (one-time, ~$0.10 for 7-day trial):
    POST /v1/email/identities  with username + displayName
    → creates an inbox identity (e.g. ai@deepapi domain)
    → renewal is OFF by default (safe)

Usage:
    python deepapi_email.py send <to> <subject> <text>    # Send email
    python deepapi_email.py draft <to> <subject> <text>    # Create draft (no send)
    python deepapi_email.py identities                      # List identities
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from deepapi import call, get_balance


def send_email(to, subject, text, send=True):
    body = {
        "to": to,
        "subject": subject,
        "text": text,
        "send": send,
    }
    result = call("/v1/email/send", body)
    return result


def list_identities():
    import urllib.request
    key = os.environ.get("DEEPAPI_API_KEY", "")
    req = urllib.request.Request("https://deepapi.co/v1/email/identities",
                                 headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode())
    return d.get("output", d)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("send")
    s.add_argument("to"); s.add_argument("subject"); s.add_argument("text")
    d = sub.add_parser("draft")
    d.add_argument("to"); d.add_argument("subject"); d.add_argument("text")
    sub.add_parser("identities")
    args = ap.parse_args()

    if args.cmd == "send":
        print(f"📧 Sending email | Balance: ${get_balance():.2f}")
        r = send_email(args.to, args.subject, args.text, send=True)
        print(f"  status: {r.get('status')} | cost: {r.get('debitMicrousd')} micro-USD")
        print(f"  error: {r.get('error')}")
    elif args.cmd == "draft":
        print(f"📧 Creating draft (no send) | Balance: ${get_balance():.2f}")
        r = send_email(args.to, args.subject, args.text, send=False)
        print(f"  status: {r.get('status')} | cost: {r.get('debitMicrousd')} micro-USD")
        print(f"  error: {r.get('error')}")
    elif args.cmd == "identities":
        ids = list_identities()
        print("Email identities:", json.dumps(ids, indent=2)[:500])
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
