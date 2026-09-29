import urllib.request
import json
import time

# Apnar library theke kichu model er nam check korar jonno
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
    print(f"✅ Success! Total online rooms fetched: {len(all_rooms)} in {fetch_duration}s\n")

    # Fast In-Memory Map
    online_dict = {room['username'].lower(): room for room in all_rooms}

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
  
