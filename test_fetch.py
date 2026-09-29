import urllib.request
import json
import time

TEST_MODELS = [
    "_stayhere",
    "taisia_hot",
    "bridgetjean",
    "soficb",
    "evvr",
    "onlyxlicious_cb"
]

print("=" * 65)
print("⏳ CHATURBATE OFFICIAL DUMP FETCH TEST")
print("=" * 65)

start_time = time.time()
url = "https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9cPAZ&client_ip=request_ip"

req = urllib.request.Request(
    url,
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
)

try:
    with urllib.request.urlopen(req, timeout=25) as response:
        raw_data = response.read()
        all_rooms = json.loads(raw_data.decode('utf-8'))

    fetch_duration = round(time.time() - start_time, 2)

    # Dictionary vs List Auto-handling
    if isinstance(all_rooms, dict):
        print(f"[DEBUG] API returned dictionary with keys: {list(all_rooms.keys())}")
        rooms = (
            all_rooms.get('results') or 
            all_rooms.get('rooms') or 
            all_rooms.get('data') or 
            []
        )
    elif isinstance(all_rooms, list):
        rooms = all_rooms
    else:
        rooms = []

    print(f"✅ Success! Total live rooms extracted: {len(rooms)} in {fetch_duration}s\n")

    if rooms and isinstance(rooms[0], dict):
        sample = rooms[0]
        print(f"[SAMPLE ROOM KEYS]: {list(sample.keys())[:8]}...")

    # Fast In-Memory Map
    online_dict = {}
    for r in rooms:
        if isinstance(r, dict) and 'username' in r:
            online_dict[r['username'].lower()] = r

    print("-" * 65)
    print("📊 TARGET STREAMERS TELEMETRY REPORT")
    print("-" * 65)

    for name in TEST_MODELS:
        name_clean = name.lower().strip()

        if name_clean in online_dict:
            data = online_dict[name_clean]

            raw_show = data.get('current_show', 'public').lower()
            if raw_show in ['private', 'group']:
                status = 'private'
            elif raw_show in ['away', 'hidden']:
                status = 'others'
            else:
                status = 'public'

            viewers = data.get('num_users', 0)
            subject = data.get('room_subject', '').strip()

            print(f"⭐ LIVE MODEL : {name_clean}")
            print(f"   ● Status   : {status.upper()} (API flag: {raw_show})")
            print(f"   ● Viewers  : {viewers} viewers")
            print(f"   ● Subject  : {subject}")
            print("-" * 65)
        else:
            print(f"⚫ OFFLINE     : {name_clean}")
            print("-" * 65)

except Exception as e:
    print(f"❌ Error fetching Chaturbate feed: {e}")
    
