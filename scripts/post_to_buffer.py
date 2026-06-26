#!/usr/bin/env python3
"""
post_to_buffer.py — Post approved content to Buffer via API.
Usage: python3 post_to_buffer.py --post "content" --platforms linkedin,facebook
       python3 post_to_buffer.py --scheduled  # post all approved scheduled posts
"""

import sys
import json
import argparse
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

# Buffer API config
BUFFER_API_KEY = ":TpMYRYR5hgFYl1fWAyuqkojMEuHyDLfwha98UTIText"
BUFFER_API_BASE = "https://api.bufferapp.com/1/"

def buffer_get(endpoint):
    """Make a GET request to Buffer API."""
    url = f"{BUFFER_API_BASE}{endpoint}" if endpoint.startswith('/') else f"{BUFFER_API_BASE}{endpoint}"
    if '?' not in url:
        url += f"?access_token={BUFFER_API_KEY}"
    else:
        url += f"&access_token={BUFFER_API_KEY}"
    
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Buffer API error ({endpoint}): {e}")
        return None

def buffer_post(endpoint, data):
    """Make a POST request to Buffer API."""
    url = f"{BUFFER_API_BASE}{endpoint}" if endpoint.startswith('/') else f"{BUFFER_API_BASE}{endpoint}"
    if '?' not in url:
        url += f"?access_token={BUFFER_API_KEY}"
    else:
        url += f"&access_token={BUFFER_API_KEY}"
    
    try:
        encoded = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(url, data=encoded, method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Buffer API error ({endpoint}): {e}")
        return None

def get_profiles():
    """Get all connected Buffer profiles."""
    return buffer_get("profiles.json")

def get_profile_for_platform(platform):
    """Get the Buffer profile ID for a given platform."""
    profiles = get_profiles()
    if not profiles:
        return None
    
    # Map platform names to Buffer profile types
    platform_map = {
        'facebook': 'facebook',
        'linkedin': 'linkedin',
        'twitter': 'twitter',
        'instagram': 'instagram'
    }
    
    target = platform_map.get(platform.lower())
    if not target:
        return None
    
    for profile in profiles:
        if profile.get('service', '').lower() == target:
            return profile
    
    # Also check formatted service name
    for profile in profiles:
        if platform.lower() in profile.get('formatted_service', '').lower():
            return profile
    
    return None

def post_update(profile_id, text, now=False):
    """Post an update to Buffer."""
    data = {
        'profile_ids[]': profile_id,
        'text': text,
        'media[]': '',
    }
    if now:
        data['now'] = 'true'
    
    return buffer_post("updates/create.json", data)

def post_scheduled(profile_id, text, timestamp):
    """Schedule a post for a specific time."""
    data = {
        'profile_ids[]': profile_id,
        'text': text,
        'media[]': '',
        'scheduled_at': timestamp,  # ISO8601 format
    }
    return buffer_post("updates/create.json", data)

def post_to_linkedin_and_facebook(text, now=False, scheduled_at=None):
    """Post content to both LinkedIn and Facebook."""
    results = {}
    
    for platform in ['linkedin', 'facebook']:
        profile = get_profile_for_platform(platform)
        if not profile:
            print(f"⚠️ No Buffer profile found for {platform}")
            results[platform] = {'error': 'no profile connected'}
            continue
        
        profile_id = profile.get('id')
        print(f"Posting to {platform} (profile {profile_id})...")
        
        if scheduled_at:
            result = post_scheduled(profile_id, text, scheduled_at)
        elif now:
            result = post_update(profile_id, text, now=True)
        else:
            result = post_update(profile_id, text)
        
        if result and result.get('success'):
            print(f"  ✅ {platform}: posted successfully")
            results[platform] = {'success': True, 'profile_id': profile_id, 'update_id': result.get('updates', [{}])[0].get('id') if result.get('updates') else None}
        else:
            print(f"  ❌ {platform}: failed — {result}")
            results[platform] = {'success': False, 'result': result}
    
    return results

def format_sa_timestamp(day_name, hour=9):
    """Format next occurrence of day_name at 9am SAST as ISO8601."""
    import pytz
    # SAST = UTC+2
    # For cron-driven scheduling, we generate the next occurrence
    days = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
    target_day = days.get(day_name.lower()[:3], 2)
    
    now = datetime.now(pytz.timezone('Africa/Johannesburg'))
    # Find next occurrence of target day
    days_ahead = target_day - now.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    elif days_ahead == 0 and now.hour >= hour:
        days_ahead += 7  # If past 9am today, go to next week
    
    next_date = now.replace(hour=hour, minute=0, second=0, microsecond=0) + __import__('datetime').timedelta(days=days_ahead)
    
    # Convert to UTC for Buffer API (Buffer expects UTC)
    utc_date = next_date.astimezone(pytz.UTC)
    return utc_date.strftime('%Y-%m-%dT%H:%M:%SZ')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Post to Buffer')
    parser.add_argument('--post', type=str, help='Post content text')
    parser.add_argument('--platforms', type=str, default='linkedin,facebook', help='Comma-separated platforms')
    parser.add_argument('--now', action='store_true', help='Post immediately')
    parser.add_argument('--scheduled', type=str, help='Schedule for day name (e.g., mon,wed,fri,sat) at 9am SAST')
    parser.add_argument('--list', action='store_true', help='List connected profiles')
    
    args = parser.parse_args()
    
    if args.list:
        profiles = get_profiles()
        if profiles:
            print(f"Connected Buffer profiles ({len(profiles)}):")
            for p in profiles:
                print(f"  - {p.get('service', '?')}: {p.get('id')} ({p.get('formatted_service', '')})")
        else:
            print("No profiles found")
        sys.exit(0)
    
    if args.post:
        platforms = [p.strip() for p in args.platforms.split(',')]
        
        for platform in platforms:
            profile = get_profile_for_platform(platform)
            if not profile:
                print(f"⚠️ No profile for {platform}, skipping")
                continue
            
            if args.scheduled:
                ts = format_sa_timestamp(args.scheduled)
                result = post_scheduled(profile['id'], args.post, ts)
            elif args.now:
                result = post_update(profile['id'], args.post, now=True)
            else:
                result = post_update(profile['id'], args.post)
            
            print(f"{platform}: {result}")
    
    if not args.post and not args.list:
        parser.print_help()