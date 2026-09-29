import sys
import subprocess
import time
import json
import re
import html as html_lib

try:
    from curl_cffi import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
    from curl_cffi import requests

TARGET = "_stayhere"
WORKER_URL = "https://cb-feed-proxy.jiakailena.workers.dev"
TRACKER_KEY = "jitul_tracker_key_2026"

session = requests.Session()

def clean_subject(raw: str) -> str:
    if not raw:
        return ""
    try:
        raw = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), raw)
    except Exception:
        pass
    raw = html_lib.unescape(raw)
    raw = raw.replace('\\"', '"').replace('\\/', '/')
    return re.sub(r'\s+', ' ', raw).strip()

def extract_tokens(text: str):
    if not text:
        return None
    m = re.search(r'\[[^\d\]]*(\d+)[^\]]*\]', text) or re.search(r'(\d+)\s*(?:tokens?|tk|remaining|left)\b', text, re.I)
    return m.group(1) if m else None

print("=" * 65)
print(f"🎯 TESTING PRIVATE / LIVE TELEMETRY FOR: '{TARGET}'")
print("=" * 65)

# 1. DIRECT EMBED PLAYER TELEMETRY (Instant Single Check)
print(f"\n[1] Checking Direct Embed Player for '{TARGET}'...")
embed_url = f"https://chaturbate.com/embed/{TARGET}/?bgcolor=black"

try:
    res = session.get(embed_url, impersonate="chrome124", timeout=15)
    if res.status_code == 200:
        html_text = res.text

        # Room Status Extraction
        status_m = re.search(r'(?:\\u0022|\\"|")room_status(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")([a-zA-Z0-9_\-]+)(?:\\u0022|\\"|")', html_text)
        raw_status = status_m.group(1).lower() if status_m else "not_found"

        status = 'offline'
        if raw_status in ['private', 'ticket_show', 'vip', 'c2c']:
            status = 'private'
        elif raw_status in ['away', 'hidden', 'group_show', 'club_show']:
            status = 'others'
        elif raw_status not in ['offline', 'disabled', 'away_offline', 'not_found']:
            status = 'public'
        elif '.m3u8' in html_text or '"is_live": true' in html_text:
            status = 'public'

        # Viewers
        viewers = 0
        mv = re.search(r'(?:\\u0022|\\"|")num_viewers(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text) or \
             re.search(r'(?:\\u0022|\\"|")viewers(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text) or \
             re.search(r'(?:\\u0022|\\"|")num_users(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text)
        if mv:
            viewers = int(mv.group(1))

        # Subject
        subject = ''
        ms = re.search(r'(?:\\u0022|\\"|")room_subject(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")(.*?)(?:\\u0022|\\"|")(?=\s*[,}\]])', html_text, re.DOTALL) or \
             re.search(r'(?:\\u0022|\\"|")subject(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")(.*?)(?:\\u0022|\\"|")(?=\s*[,}\]])', html_text, re.DOTALL)
        if ms:
            cand = clean_subject(ms.group(1))
            if "free live adult chat" not in cand.lower():
                subject = cand

        tokens = extract_tokens(subject)

        print(f"● Embed HTTP Status   : 200 OK")
        print(f"● Raw Internal Status : '{raw_status}'")
        print(f"● Parsed Status       : {status.upper()}")
        print(f"● Viewers             : {viewers}")
        print(f"● Goal / Subject      : {subject if subject else '(No public goal / currently in private)'}")
        print(f"● Goal Tokens         : {tokens if tokens else 'None'}")

        if status == 'private':
            print(f"\n🔒 CONFIRMED: '{TARGET}' IS CURRENTLY IN PRIVATE SHOW!")
        elif status == 'public':
            print(f"\n🟢 '{TARGET}' IS IN PUBLIC SHOW!")
        else:
            print(f"\n⚫ '{TARGET}' CURRENT STATUS: {status.upper()}")
    else:
        print(f"❌ Embed returned HTTP: {res.status_code}")
except Exception as e:
    print(f"❌ Embed error: {e}")

# 2. CHECK VIA CLOUDFLARE WORKER AFFILIATE FEED
print(f"\n[2] Checking Cloudflare Worker Feed for '{TARGET}'...")
try:
    res = session.get(WORKER_URL, headers={"x-tracker-key": TRACKER_KEY}, timeout=20)
    if res.status_code == 200:
        data = res.json()
        rooms = data.get('results', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        print(f"● Feed returned {len(rooms)} live rooms.")

        found = False
        for r in rooms:
            if r.get('username', '').lower() == TARGET.lower():
                found = True
                print(f"\n🎉 FOUND '{TARGET}' IN API FEED!")
                print(f"● current_show  : {r.get('current_show')}")
                print(f"● num_users     : {r.get('num_users')}")
                print(f"● seconds_online: {r.get('seconds_online')}s ({r.get('seconds_online', 0)//60} mins)")
                print(f"● room_subject  : {r.get('room_subject')}")
                break

        if not found:
            print(f"ℹ️ '{TARGET}' is not in this first 500-room batch (might be in later pagination batch or offline).")
except Exception as e:
    print(f"❌ Worker test error: {e}")

print("=" * 65)
