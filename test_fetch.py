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
print("🌍 FETCHING CHATURBATE PUBLIC FEED (1 SINGLE REQUEST)")
print("=" * 65)

try:
    # 1. Runner-er real public IPv4 ber kora
    my_ip = session.get("https://api.ipify.org", impersonate="chrome124", timeout=10).text.strip()
    print(f"● Detected Runner Public IP: {my_ip}")

    # 2. Strict mandatory parameter shoho 1-ti single request
    # limit=500 dile ek request-e 500 room ashbe
    URL = f"https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9cPAZ&client_ip={my_ip}&format=json&limit=500"
    
    start_t = time.time()
    res = session.get(URL, impersonate="chrome124", timeout=25)
    print(f"● HTTP Response Status: {res.status_code}")

    if res.status_code == 200:
        data = res.json()
        rooms = data.get('results', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        total_count = data.get('count', len(rooms)) if isinstance(data, dict) else len(rooms)

        print(f"✅ Success! Total Live Rooms On Platform: {total_count}")
        print(f"● Rooms Downloaded in this request: {len(rooms)} in {round(time.time() - start_t, 2)}s")

        if rooms:
            sample = rooms[0]
            print("\n--- SAMPLE LIVE ROOM DATA ---")
            print(f"⭐ Name     : {sample.get('username')}")
            print(f"● Show     : {sample.get('current_show')}")
            print(f"● Viewers  : {sample.get('num_users')}")
            print(f"● Subject  : {sample.get('room_subject')}")
            print(f"● Tags     : {', '.join(sample.get('tags', [])[:6])}")

        # In-Memory Fast Lookup
        online_map = {r.get('username', '').lower(): r for r in rooms if 'username' in r}
        print("\n" + "=" * 65)
        print("🎯 TARGETS STATUS:")
        for t in TARGETS:
            if t.lower() in online_map:
                m = online_map[t.lower()]
                print(f"🟢 {t.upper()} is LIVE! Status: {m.get('current_show')} | Viewers: {m.get('num_users')} | Subject: {m.get('room_subject')}")
            else:
                print(f"⚫ {t.upper()} is not in this batch (Offline or next page)")
    else:
        print(f"❌ Failed: HTTP {res.status_code}")
        print(res.text[:300])

except Exception as e:
    print(f"❌ Error: {e}")

print("=" * 65)
