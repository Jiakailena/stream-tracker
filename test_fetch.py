import sys
import subprocess
import time
import json
import re

try:
    from curl_cffi import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
    from curl_cffi import requests

WORKER_URL = "https://cb-feed-proxy.jiakailena.workers.dev"
TRACKER_KEY = "jitul_tracker_key_2026"
TARGETS = ["mia_rom", "dellris"]

print("=" * 65)
print("🌍 FETCHING GLOBAL FEED VIA CLOUDFLARE WORKER (1 REQUEST)")
print("=" * 65)

session = requests.Session()
start_t = time.time()

try:
    res = session.get(
        WORKER_URL,
        headers={"x-tracker-key": TRACKER_KEY},
        timeout=30
    )
    print(f"● Cloudflare Worker Status: {res.status_code}")
    print(f"● Download Size: {len(res.content) / (1024 * 1024):.2f} MB")

    if res.status_code == 200:
        data = res.json()
        rooms = data if isinstance(data, list) else (data.get('results') or data.get('rooms') or [])
        elapsed = round(time.time() - start_t, 2)
        print(f"✅ SUCCESS! Fetched {len(rooms)} live rooms in {elapsed}s")

        if rooms:
            online_map = {r.get('username', '').lower(): r for r in rooms if 'username' in r}

            print("\n" + "=" * 65)
            print("🎯 TARGET MODELS TELEMETRY REPORT:")
            for t in TARGETS:
                if t.lower() in online_map:
                    m = online_map[t.lower()]
                    subj = m.get('room_subject', '').strip()
                    tokens_m = re.search(r'\[[^\d\]]*(\d+)[^\]]*\]', subj) or re.search(r'(\d+)\s*(?:tokens?|tk)\b', subj, re.I)
                    tokens = tokens_m.group(1) if tokens_m else "None"

                    print(f"🟢 {t.upper()} is LIVE!")
                    print(f"   ● Status   : {m.get('current_show', 'public').upper()}")
                    print(f"   ● Viewers  : {m.get('num_users', 0)} viewers")
                    print(f"   ● Duration : {m.get('seconds_online', 0) // 60} mins online")
                    print(f"   ● Goal/Subj: {subj}")
                    print(f"   ● Tokens   : {tokens}")
                else:
                    print(f"⚫ {t.upper()} is OFFLINE")
            print("=" * 65)
    else:
        print(f"❌ Failed: HTTP {res.status_code} -> {res.text[:250]}")

except Exception as e:
    print(f"❌ Error: {e}")

print("=" * 65)
