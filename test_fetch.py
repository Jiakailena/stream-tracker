import sys
import subprocess
import time
import json
import re
import html as html_lib

# Auto-install curl_cffi for bypassing Cloudflare TLS fingerprinting
try:
    from curl_cffi import requests
except ImportError:
    print("📦 Installing curl_cffi (Cloudflare TLS bypasser)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
    from curl_cffi import requests

TARGET = "mia_rom"

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

print("=" * 70)
print("🌍 FETCHING CHATURBATE GLOBAL ONLINE FEED (1 SINGLE REQUEST)")
print("=" * 70)

# Real open affiliate dump endpoint
DUMP_URL = "https://chaturbate.com/affiliates/api/onlinerooms/?format=json"

start_time = time.time()
all_rooms = []

try:
    # Impersonate Chrome 124 TLS & HTTP/2 to bypass Cloudflare 403
    session = requests.Session()
    res = session.get(DUMP_URL, impersonate="chrome124", timeout=35)
    
    print(f"● HTTP Response Status: {res.status_code}")
    print(f"● Download Size: {len(res.content) / (1024 * 1024):.2f} MB")
    
    if res.status_code == 200:
        data = res.json()
        if isinstance(data, list):
            all_rooms = data
        elif isinstance(data, dict):
            all_rooms = data.get('results') or data.get('rooms') or []
            
        elapsed = round(time.time() - start_time, 2)
        print(f"✅ SUCCESS! Fetched {len(all_rooms)} total live rooms in {elapsed}s")
    else:
        print(f"❌ Failed with status code: {res.status_code}")
        print(res.text[:300])

except Exception as err:
    print(f"❌ Connection Error: {err}")

# Search target inside the single dump
if all_rooms:
    print("-" * 70)
    print(f"🔍 Searching for target '{TARGET}' in the downloaded dump...")
    
    # Fast In-Memory Dictionary Lookup
    online_map = {r.get('username', '').lower(): r for r in all_rooms if 'username' in r}
    
    if TARGET.lower() in online_map:
        model_data = online_map[TARGET.lower()]
        raw_subj = clean_subject(model_data.get('room_subject', ''))
        tokens = extract_tokens(raw_subj)
        
        print("\n" + "★" * 25 + f" {TARGET.upper()} IS LIVE! " + "★" * 25)
        print(f"🟢 Show Status    : {model_data.get('current_show', 'public').upper()}")
        print(f"👥 Real Viewers   : {model_data.get('num_users', 0)} viewers")
        print(f"⏱️ Online For     : {model_data.get('seconds_online', 0) // 60} minutes")
        print(f"📝 Room Subject   : {raw_subj}")
        print(f"🪙 Goal Tokens    : {tokens if tokens else 'No goal tokens detected'}")
        print(f"🏷️ Room Tags      : {', '.join(model_data.get('tags', []))}")
        print("-" * 70)
        print("Raw JSON Data for verification:")
        print(json.dumps(model_data, indent=2))
    else:
        print(f"\n⚫ RESULT: '{TARGET}' is currently OFFLINE.")
        print("\n--- SAMPLE 2 LIVE MODELS FROM THIS EXACT DUMP ---")
        for sample in all_rooms[:2]:
            s_name = sample.get('username')
            s_subj = clean_subject(sample.get('room_subject', ''))
            s_view = sample.get('num_users')
            s_show = sample.get('current_show')
            print(f"⭐ [{s_name}] Show: {s_show} | Viewers: {s_view} | Subject: '{s_subj[:50]}...'")
print("=" * 70)
