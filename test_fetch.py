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

TARGETS = ["mia_rom", "dellris"]
session = requests.Session()

print("=" * 65)
print("🌍 TESTING CHATURBATE GLOBAL FEED ALTERNATIVE ENDPOINTS")
print("=" * 65)

# Endpoints that provide the global rooms in 1 single request
CANDIDATE_URLS = [
    # 1. Main affiliate feed with json format
    "https://chaturbate.com/affiliates/api/onlinerooms/?format=json",
    # 2. Public API without wm restrictions
    "https://chaturbate.com/api/public/affiliates/onlinerooms/?format=json&limit=100&client_ip=1.1.1.1&wm=9cPAZ",
    # 3. Direct frontpage catalog API
    "https://chaturbate.com/api/ts/roomlist/room-list/?limit=90"
]

all_rooms = []

for idx, url in enumerate(CANDIDATE_URLS, 1):
    print(f"\n[TRY {idx}] Connecting to: {url[:60]}...")
    try:
        start_t = time.time()
        res = session.get(
            url, 
            impersonate="chrome124", 
            timeout=20,
            headers={
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://chaturbate.com/'
            }
        )
        print(f"● Status: {res.status_code} | Size: {len(res.content)} bytes")

        if res.status_code == 200:
            try:
                data = res.json()
                rooms = []
                if isinstance(data, list):
                    rooms = data
                elif isinstance(data, dict):
                    rooms = data.get('results') or data.get('rooms') or data.get('data') or []
                
                if len(rooms) > 0:
                    print(f"✅ SUCCESS! Fetched {len(rooms)} live rooms in {round(time.time() - start_t, 2)}s!")
                    all_rooms = rooms
                    break
                else:
                    print("⚠️ Returned 200 OK but 0 rooms found.")
            except Exception as parse_err:
                print(f"⚠️ JSON parsing error: {parse_err}")
        else:
            print(f"❌ Failed: HTTP {res.status_code}")
    except Exception as e:
        print(f"❌ Connection error: {e}")

# Target check if any endpoint succeeded
if all_rooms:
    print("\n" + "=" * 65)
    print("🎯 CHECKING TARGET STREAMERS IN DOWNLOADED LIST:")
    online_map = {r.get('username', '').lower(): r for r in all_rooms if 'username' in r}
    
    for t in TARGETS:
        if t.lower() in online_map:
            m = online_map[t.lower()]
            print(f"🟢 {t.upper()} is LIVE! Viewers: {m.get('num_users', m.get('viewers', 0))} | Show: {m.get('current_show', 'public')}")
        else:
            print(f"⚫ {t.upper()} is not in this live batch.")
    
    sample = all_rooms[0]
    print(f"\n[Sample Room Data]: Name: {sample.get('username')} | Viewers: {sample.get('num_users', sample.get('viewers'))}")
else:
    print("\n⚠️ None of the global endpoints returned rooms on this datacenter IP.")

print("=" * 65)
