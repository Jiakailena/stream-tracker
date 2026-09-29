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

print("=" * 65)
print("🌍 TESTING CHATURBATE OFFICIAL PUBLIC FEED (CLEAN ENDPOINT)")
print("=" * 65)

# Clean Official API without broken client_ip parameter
URL = "https://chaturbate.com/api/public/affiliates/onlinerooms/?format=json&limit=100"

session = requests.Session()

try:
    start_t = time.time()
    res = session.get(URL, impersonate="chrome124", timeout=20)
    print(f"● HTTP Response: {res.status_code}")

    if res.status_code == 200:
        data = res.json()
        rooms = data.get('results', []) if isinstance(data, dict) else data
        total_count = data.get('count', len(rooms)) if isinstance(data, dict) else len(rooms)

        print(f"✅ Success! Total Live Models Reported: {total_count}")
        print(f"● Fetched in this batch: {len(rooms)} rooms in {round(time.time() - start_t, 2)}s")

        if rooms:
            print("\n--- SAMPLE LIVE STREAMER FROM FEED ---")
            sample = rooms[0]
            print(f"⭐ Name     : {sample.get('username')}")
            print(f"● Status   : {sample.get('current_show')}")
            print(f"● Viewers  : {sample.get('num_users')}")
            print(f"● Goal/Subj: {sample.get('room_subject')}")
            print(f"● Tags     : {', '.join(sample.get('tags', [])[:5])}")

        # Search Targets
        online_map = {r.get('username', '').lower(): r for r in rooms if 'username' in r}
        print("\n" + "=" * 65)
        for t in TARGETS:
            if t.lower() in online_map:
                m = online_map[t.lower()]
                print(f"🟢 {t.upper()} is ONLINE! Viewers: {m.get('num_users')} | Subject: {m.get('room_subject')}")
            else:
                print(f"⚫ {t.upper()} is not in this batch (Offline or different page)")

    else:
        print(f"❌ Failed: HTTP {res.status_code}")
        print(res.text[:300])

except Exception as e:
    print(f"❌ Connection error: {e}")

print("=" * 65)
