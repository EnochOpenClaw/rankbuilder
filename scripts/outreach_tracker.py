#!/usr/bin/env python3
"""
outreach_tracker.py — Tracks every outreach touchpoint, reply, publication, and link acquisition.
Maintains a structured JSONL log + a summary JSON for reporting.

Usage:
    python3 outreach_tracker.py --report           # Full performance report
    python3 outreach_tracker.py --report --days 7   # Last 7 days only
    python3 outreach_tracker.py --backfill          # Build tracker from outreach_log.jsonl
    python3 outreach_tracker.py --prospect <domain>  # Single prospect history
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

DB_FILE         = Path(__file__).parent.parent / 'prospects' / 'prospect_db.json'
OUTREACH_LOG    = Path(__file__).parent.parent / 'prospects' / 'outreach_log.jsonl'
TRACKER_FILE    = Path(__file__).parent.parent / 'prospects' / 'outreach_tracker.jsonl'
SUMMARY_FILE    = Path(__file__).parent.parent / 'prospects' / 'outreach_summary.json'
LOG_FILE        = Path(__file__).parent.parent / 'scripts' / 'logs' / 'tracker.log'


# ============================================================================
# TRACKER ENTRY SCHEMA
# ============================================================================

def make_entry(
    event: str,          # 'pitch_sent' | 'reply_received' | 'article_published' | 'link_acquired' | 'rejected' | 'bounced'
    prospect_url: str = '',
    prospect_domain: str = '',
    prospect_email: str = '',
    subject: str = '',
    pitch_topic: str = '',
    pitch_angle: str = '',
    reply_status: str = '',
    article_url: str = '',
    link_url: str = '',
    notes: str = '',
    source: str = 'guest_outreach',  # 'guest_outreach' | 'haro' | 'connectively'
    campaign: str = 'default',
) -> dict:
    """Create a structured tracker entry."""
    return {
        "event":         event,
        "timestamp":     datetime.now().isoformat(),
        "prospect_url":  prospect_url,
        "prospect_domain": prospect_domain or extract_domain(prospect_url),
        "prospect_email": prospect_email,
        "subject":       subject,
        "pitch_topic":   pitch_topic,
        "pitch_angle":   pitch_angle,
        "reply_status":  reply_status,
        "article_url":   article_url,
        "link_url":      link_url,
        "notes":         notes,
        "source":        source,
        "campaign":      campaign,
        "date":          datetime.now().strftime("%Y-%m-%d"),
    }


def extract_domain(url: str) -> str:
    if not url:
        return ''
    url = url.strip().lower().replace('https://', '').replace('http://', '')
    return url.split('/')[0]


# ============================================================================
# LOG OPERATIONS
# ============================================================================

def log_event(entry: dict, quiet: bool = False):
    """Append a tracker entry to the JSONL file."""
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    if not quiet:
        print(f"  📝 [{entry['event']}] {entry['prospect_domain']}")


def load_tracker() -> list:
    """Load all tracker entries."""
    if not TRACKER_FILE.exists():
        return []
    entries = []
    with open(TRACKER_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    return entries


def update_summary(entries: list):
    """Compute + write outreach_summary.json."""
    if not entries:
        return

    cutoff = datetime.now() - timedelta(days=30)
    cutoff_iso = cutoff.isoformat()

    # Aggregate by prospect_domain
    by_domain = defaultdict(lambda: {
        'pitches': [], 'replies': 0, 'published': 0,
        'links': 0, 'last_contact': None, 'first_contact': None,
    })

    for e in entries:
        d = e['prospect_domain']
        by_domain[d]['pitches'].append(e)
        ts = e.get('timestamp', '')
        existing_first = by_domain[d].get('first_contact')
        if existing_first is None or (ts and ts < existing_first):
            by_domain[d]['first_contact'] = ts
        existing_last = by_domain[d].get('last_contact')
        if ts and (existing_last is None or ts > existing_last):
            by_domain[d]['last_contact'] = ts

        if e['event'] in ('reply_received', 'article_published'):
            by_domain[d]['replies'] += 1
        if e['event'] == 'article_published':
            by_domain[d]['published'] += 1
        if e['event'] == 'link_acquired':
            by_domain[d]['links'] += 1

    # Summary stats
    total_pitches   = len(entries)
    total_replies   = sum(1 for e in entries if e['event'] == 'reply_received')
    total_published = sum(1 for e in entries if e['event'] == 'article_published')
    total_links     = sum(1 for e in entries if e['event'] == 'link_acquired')
    reply_rate      = round(total_replies / total_pitches * 100, 1) if total_pitches else 0
    publish_rate    = round(total_published / total_pitches * 100, 1) if total_pitches else 0

    # Per-source breakdown
    by_source = defaultdict(lambda: {'pitches': 0, 'replies': 0, 'published': 0, 'links': 0})
    for e in entries:
        src = e.get('source', 'unknown')
        by_source[src]['pitches'] += 1
        if e['event'] == 'reply_received':
            by_source[src]['replies'] += 1
        if e['event'] == 'article_published':
            by_source[src]['published'] += 1
        if e['event'] == 'link_acquired':
            by_source[src]['links'] += 1

    # Best converting domains
    top_converters = sorted(
        [(d, v['published'], v['links']) for d, v in by_domain.items() if v['published'] > 0],
        key=lambda x: -x[2]
    )[:10]

    summary = {
        "generated_at": datetime.now().isoformat(),
        "period": "all_time",
        "total_pitches": total_pitches,
        "total_replies": total_replies,
        "total_published": total_published,
        "total_links": total_links,
        "reply_rate_pct": reply_rate,
        "publish_rate_pct": publish_rate,
        "unique_domains_contacted": len(by_domain),
        "by_source": dict(by_source),
        "top_converters": top_converters,
    }

    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


# ============================================================================
# REPORTING
# ============================================================================

def print_report(entries: list, days: int = 0):
    if not entries:
        print("No tracker entries found.")
        return

    if days > 0:
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()
        entries = [e for e in entries if e['timestamp'] >= cutoff_iso]
        print(f"=== Outreach Report — Last {days} days ===")
    else:
        print("=== Full Outreach Report (All Time) ===")

    if not entries:
        print("No entries in this period.")
        return

    total_pitches   = len(entries)
    total_replies   = sum(1 for e in entries if e['event'] == 'reply_received')
    total_published = sum(1 for e in entries if e['event'] == 'article_published')
    total_links     = sum(1 for e in entries if e['event'] == 'link_acquired')
    reply_rate      = round(total_replies / total_pitches * 100, 1) if total_pitches else 0
    publish_rate    = round(total_published / total_pitches * 100, 1) if total_pitches else 0

    print(f"\n📊 OVERALL PERFORMANCE")
    print(f"  Pitches sent:        {total_pitches}")
    print(f"  Replies received:    {total_replies}  ({reply_rate}% reply rate)")
    print(f"  Articles published:  {total_published}  ({publish_rate}% publish rate)")
    print(f"  Links acquired:      {total_links}")
    print()

    # Per-source breakdown
    print(f"📡 BY SOURCE")
    by_source = defaultdict(lambda: {'pitches': 0, 'replies': 0, 'published': 0})
    for e in entries:
        src = e.get('source', 'unknown')
        by_source[src]['pitches'] += 1
        if e['event'] == 'reply_received':
            by_source[src]['replies'] += 1
        if e['event'] == 'article_published':
            by_source[src]['published'] += 1

    for src, stats in sorted(by_source.items(), key=lambda x: -x[1]['pitches']):
        rr = round(stats['replies']/stats['pitches']*100, 1) if stats['pitches'] else 0
        pr = round(stats['published']/stats['pitches']*100, 1) if stats['pitches'] else 0
        print(f"  {src:20s} pitches={stats['pitches']:3d}  replies={stats['replies']:2d} ({rr}%)  published={stats['published']} ({pr}%)")
    print()

    # Outstanding replies (waiting)
    waiting = [e for e in entries if e['event'] == 'pitch_sent' and e['reply_status'] in ('', 'waiting')]
    print(f"⏳ AWAITING REPLY ({len(waiting)} prospects)")
    for e in waiting[:15]:
        print(f"  {e['prospect_domain']:40s} sent={e['date']}  topic={e.get('pitch_topic','?')[:40]}")
    print()

    # Converted prospects
    converted = [e for e in entries if e['event'] in ('article_published', 'link_acquired')]
    if converted:
        print(f"✅ CONVERTED ({len(converted)} wins)")
        for e in converted:
            print(f"  {e['prospect_domain']:40s} date={e['date']}  article={e.get('article_url','?')[:60]}")
    print()

    # Bounced / rejected
    bad = [e for e in entries if e['event'] in ('rejected', 'bounced')]
    if bad:
        print(f"❌ BOUNCED/REJECTED ({len(bad)})")
        for e in bad[:10]:
            print(f"  {e['prospect_domain']}  note={e.get('notes','?')[:50]}")


def prospect_history(domain: str, entries: list):
    """Show full history for a single prospect."""
    history = [e for e in entries if domain in e.get('prospect_domain', '')]
    if not history:
        print(f"No history found for: {domain}")
        return
    print(f"\n📋 HISTORY: {domain}")
    print(f"  Total touchpoints: {len(history)}")
    for e in sorted(history, key=lambda x: x['timestamp']):
        print(f"  [{e['date']}] {e['event']:20s} | {e.get('pitch_topic', e.get('subject', '?'))[:50]}")
        if e.get('article_url'):
            print(f"    Article: {e['article_url']}")
        if e.get('link_url'):
            print(f"    Link:    {e['link_url']}")
        if e.get('notes'):
            print(f"    Note:    {e['notes']}")


# ============================================================================
# BACKFILL from outreach_log.jsonl
# ============================================================================

def backfill():
    """Build tracker entries from the existing outreach_log.jsonl."""
    if not OUTREACH_LOG.exists():
        print("No outreach_log.jsonl found — nothing to backfill.")
        return

    entries = []
    skipped = 0
    with open(OUTREACH_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                log_entry = json.loads(line)
            except Exception:
                skipped += 1
                continue

            event_map = {
                'sent': 'pitch_sent',
                'delivered': 'pitch_sent',
                'opened': 'pitch_sent',
                'replied': 'reply_received',
                'accepted': 'article_published',
                'published': 'article_published',
                'link_acquired': 'link_acquired',
                'rejected': 'rejected',
                'bounced': 'bounced',
                'waiting': 'pitch_sent',
                'new': None,
                'contacted': None,
            }

            raw_status = log_entry.get('status', '') or log_entry.get('reply_status', '')
            mapped = event_map.get(raw_status, 'pitch_sent')

            if mapped is None:
                # Skip non-outreach status like 'new', 'contacted'
                continue

            ts = log_entry.get('sent_at') or log_entry.get('timestamp') or ''
            entry = make_entry(
                event=mapped,
                prospect_url=log_entry.get('prospect_url', ''),
                prospect_domain=log_entry.get('prospect_name', '') or log_entry.get('prospect_domain', ''),
                prospect_email=log_entry.get('email', ''),
                subject=log_entry.get('subject', ''),
                pitch_topic=log_entry.get('pitch_topic', ''),
                pitch_angle=log_entry.get('pitch_angle', ''),
                reply_status=raw_status,
                article_url=log_entry.get('article_url', ''),
                link_url=log_entry.get('link_url', ''),
                notes=log_entry.get('notes', ''),
                source=log_entry.get('source', 'guest_outreach'),
            )
            if ts:
                entry['timestamp'] = ts
                entry['date'] = ts[:10]
            entries.append(entry)

    print(f"Backfill: {len(entries)} entries converted from {OUTREACH_LOG.name}")
    if skipped:
        print(f"  Skipped {skipped} unparseable lines")

    # Write to tracker
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_FILE, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    print(f"Written to {TRACKER_FILE}")

    # Update summary
    summary = update_summary(entries)
    print(f"\n=== Summary ===")
    print(f"  Pitches: {summary['total_pitches']}")
    print(f"  Replies:  {summary['total_replies']} ({summary['reply_rate_pct']}%)")
    print(f"  Published: {summary['total_published']}")
    print(f"  Links:    {summary['total_links']}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Outreach tracker — report, log, and backfill')
    parser.add_argument('--report', action='store_true', help='Print performance report')
    parser.add_argument('--days', type=int, default=0, help='Limit report to last N days')
    parser.add_argument('--backfill', action='store_true', help='Backfill tracker from outreach_log.jsonl')
    parser.add_argument('--prospect', type=str, default='', help='Show history for a domain')
    parser.add_argument('--event', type=str, default='pitch_sent', help='Event type to log')
    parser.add_argument('--domain', type=str, default='', help='Prospect domain')
    parser.add_argument('--email', type=str, default='', help='Prospect email')
    parser.add_argument('--url', type=str, default='', help='Prospect URL')
    parser.add_argument('--subject', type=str, default='', help='Email subject')
    parser.add_argument('--topic', type=str, default='', help='Pitch topic')
    parser.add_argument('--angle', type=str, default='', help='Pitch angle used')
    parser.add_argument('--source', type=str, default='guest_outreach', help='Source: guest_outreach|haro|connectively')
    parser.add_argument('--notes', type=str, default='', help='Additional notes')
    args = parser.parse_args()

    if args.backfill:
        backfill()
        return

    if args.prospect:
        entries = load_tracker()
        prospect_history(args.prospect, entries)
        return

    if args.report:
        entries = load_tracker()
        print_report(entries, days=args.days)
        return

    # Default: log a new event
    entry = make_entry(
        event=args.event,
        prospect_url=args.url,
        prospect_domain=args.domain,
        prospect_email=args.email,
        subject=args.subject,
        pitch_topic=args.topic,
        pitch_angle=args.angle,
        source=args.source,
        notes=args.notes,
    )
    log_event(entry)


if __name__ == '__main__':
    main()
