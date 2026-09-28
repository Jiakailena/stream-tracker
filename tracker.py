#!/usr/bin/env python3
"""
Live Lounge - Stream Tracker (tracker.py)
------------------------------------------
- 20-Worker concurrent embed scraper (chaturbate.com/embed/{username}/?bgcolor=black)
- Extracts live status, `num_viewers`, and `room_subject` in a single pass
- InfinityFree slowAES firewall bypass
- Direct sync back to stream.php (load_all -> sync_tracker)
"""

import os
import re
import sys
import time
import json
import html as html_lib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

ENDPOINT_URL = "https://stacy.infinityfreeapp.com/stream.php"
TRACKER_SECRET = "jitul_tracker_key_2026"

session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=35,
    pool_maxsize=35,
    max_retries=Retry(total=1, backoff_factor=0.2)
)
session.mount('https://', adapter)
session.mount('http://', adapter)

session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9'
})


def bypass_infinityfree(url):
    """Bypasses InfinityFree's slowAES __test cookie challenge automatically"""
    try:
        res = session.get(url, timeout=12)
        if 'slowAES.decrypt' in res.text:
            matches = re.findall(r'toNumbers\("([0-9a-fA-F]+)"\)', res.text)
            if len(matches) >= 3:
                a_key = bytes.fromhex(matches[0])
                b_iv = bytes.fromhex(matches[1])
                c_cipher = bytes.fromhex(matches[2])

                cipher = Cipher(algorithms.AES(a_key), modes.CBC(b_iv), backend=default_backend())
                decryptor = cipher.decryptor()
                cookie_val = (decryptor.update(c_cipher) + decryptor.finalize()).hex()

                # Set on both subdomain, wildcard domain, and header for 100% persistence
                session.cookies.set('__test', cookie_val, domain='stacy.infinityfreeapp.com', path='/')
                session.cookies.set('__test', cookie_val, domain='.infinityfreeapp.com', path='/')
                session.headers['Cookie'] = f'__test={cookie_val}'
                print("[OK] InfinityFree firewall bypassed successfully!")
                return True
        return True
    except Exception as e:
        print(f"[ERROR] Bypass error: {e}")
        return False


def clean_subject(raw: str) -> str:
    """Decodes unicode escapes (\\u2665, \\u0020), HTML entities, and formatting."""
    if not raw:
        return ""
    try:
        raw = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), raw)
    except Exception:
        pass
    raw = html_lib.unescape(raw)
    raw = raw.replace('\\"', '"').replace('\\/', '/')
    return re.sub(r'\s+', ' ', raw).strip()


def extract_from_embed_html(html_text: str):
    """
    Extracts real-time viewer count and room subject from embed HTML.
    Supports raw quotes, escaped quotes (\\"), and unicode escaped quotes (\\u0022).
    """
    viewers = 0
    subject = ''

    if not html_text:
        return viewers, subject

    # 1. Real-time Viewers (Chaturbate uses num_viewers inside embed JS)
    mv = re.search(r'(?:\\u0022|\\"|")num_viewers(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text) or \
         re.search(r'(?:\\u0022|\\"|")viewers(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text) or \
         re.search(r'(?:\\u0022|\\"|")num_users(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text)
    if mv:
        viewers = int(mv.group(1))

    # 2. Room Subject / Goal
    ms = re.search(r'(?:\\u0022|\\"|")room_subject(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")(.*?)(?:\\u0022|\\"|")(?=\s*[,}\]])', html_text, re.DOTALL) or \
         re.search(r'(?:\\u0022|\\"|")subject(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")(.*?)(?:\\u0022|\\"|")(?=\s*[,}\]])', html_text, re.DOTALL) or \
         re.search(r'(?:\\u0022|\\"|")room_title(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")(.*?)(?:\\u0022|\\"|")(?=\s*[,}\]])', html_text, re.DOTALL)
    if ms:
        subject = clean_subject(ms.group(1))

    # Fallback to <title> if JS subject tag is not found
    if not subject:
        title_match = re.search(r'<title>(.*?)</title>', html_text, re.IGNORECASE | re.DOTALL)
        if title_match:
            t = title_match.group(1).strip()
            t = re.sub(r'\s*-\s*Chaturbate.*$', '', t, flags=re.IGNORECASE)
            subject = clean_subject(t)

    return viewers, subject


def check_live_status_embed(username: str):
    """
    Fast, reliable 20-worker live status detector via embed URL.
    Extracts status, viewers, and subject in a single request.
    """
    url = f"https://chaturbate.com/embed/{username}/?bgcolor=black"
    try:
        res = session.get(url, timeout=7)
        if res.status_code == 200:
            html_text = res.text

            # Check Room Status (Matches \u0022room_status\u0022: \u0022public\u0022)
            status_match = re.search(
                r'(?:\\u0022|\\"|")room_status(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")([a-zA-Z0-9_\-]+)(?:\\u0022|\\"|")',
                html_text
            )

            status = None
            if status_match:
                raw_status = status_match.group(1).lower()
                if raw_status in ['offline', 'disabled', 'away_offline']:
                    return None
                elif raw_status in ['private', 'ticket_show', 'vip', 'c2c']:
                    status = 'private'
                elif raw_status in ['away', 'hidden', 'group_show', 'club_show']:
                    status = 'others'
                else:
                    status = 'public'
            elif '.m3u8' in html_text or '"is_live": true' in html_text or '\\u0022is_live\\u0022: true' in html_text:
                status = 'public'
            else:
                return None

            # Extract Viewers & Subject directly from the same HTML
            viewers, subject = extract_from_embed_html(html_text)

            return {
                'name': username,
                'status': status,
                'viewers': viewers,
                'subject': subject
            }
    except Exception:
        pass

    return None


def main():
    print("=" * 65)
    print(" LIVE LOUNGE TRACKER - DIRECT EMBED PARSER")
    print("=" * 65)

    # 1. InfinityFree Firewall Bypass
    bypass_infinityfree(ENDPOINT_URL)

    # 2. Load streamers from database
    try:
        res = session.post(ENDPOINT_URL, data={'action': 'load_all'}, timeout=15)
        site_data = res.json()
        raw_streamers = site_data.get('streamers', [])
    except Exception as e:
        print(f"[ERROR] Failed to load streamers: {e}")
        return

    if not raw_streamers:
        print("[WARN] No saved streamers found in library.")
        return

    saved_set = [s['name'].lower() for s in raw_streamers if 'name' in s]
    print(f"[INFO] Total streamers in library: {len(saved_set)}")

    # 3. High-Speed 20-Workers Concurrency Live Verification & Detail Extraction
    print(f"[INFO] Verifying live status, viewers, and subjects with 20 parallel workers...")
    confirmed_live = []
    found_online = set()

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(check_live_status_embed, saved_set)
        for r in results:
            if r:
                confirmed_live.append(r)
                found_online.add(r['name'])

    print(f"[OK] Detected {len(confirmed_live)} streamers LIVE!")

    # 4. Handle Offline streamers
    status_payload = list(confirmed_live)
    for name in set(saved_set) - found_online:
        status_payload.append({
            'name': name,
            'status': 'offline',
            'viewers': 0,
            'subject': ''
        })

    # Summary Report in Actions Log
    print("\n--- FINAL LIVE STATUS REPORT ---")
    for item in status_payload:
        if item['status'] != 'offline':
            subj = item['subject']
            preview = (subj[:45] + "...") if len(subj) > 45 else subj
            print(f"-> [{item['name'].upper():<16}] Status: {item['status']:<7} | Viewers: {item['viewers']:<5} | Subject: '{preview}'")
    print(f"\nSummary: {len(confirmed_live)} LIVE, {len(saved_set) - len(confirmed_live)} OFFLINE.\n")

    # 5. Push to Database
    print("[INFO] Syncing verified stats to database...")
    try:
        sync_res = session.post(ENDPOINT_URL, data={
            'action': 'sync_tracker',
            'secret': TRACKER_SECRET,
            'payload': json.dumps(status_payload)
        }, timeout=20)
        print("[SYNC] Database Sync Result:", sync_res.json())
    except Exception as e:
        print(f"[ERROR] Sync error: {e}")

    print("=" * 65)


if __name__ == '__main__':
    main()
