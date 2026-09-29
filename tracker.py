import sys
import subprocess
import time
import json
import re
import random
import html as html_lib

# Auto check for curl_cffi
try:
    from curl_cffi import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
    from curl_cffi import requests

# ==========================================
# CONFIGURATION & SETTINGS
# ==========================================
WEBSITE_URL = "https://stacy.infinityfreeapp.com/stream.php"
TRACKER_SECRET_KEY = "jitul_tracker_key_2026"

WORKER_URL = "https://cb-feed-proxy.jiakailena.workers.dev"
CLOUDFLARE_KEY = "jitul_tracker_key_2026"

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def clean_model_name(raw: str) -> str:
    """Standardizes username matching cleanName() in stream.php"""
    if not raw:
        return ""
    name = str(raw).strip()
    name = re.sub(r'^https?://(?:www\.)?chaturbate\.com/', '', name, flags=re.I)
    name = name.strip("/@ \t\n\r\0\x0B")
    parts = name.split('/')[0].split('?')[0]
    return parts.lower().strip()

def clean_subject(raw: str) -> str:
    """Cleans unicode emojis and escaped characters"""
    if not raw:
        return ""
    try:
        raw = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), raw)
    except Exception:
        pass
    raw = html_lib.unescape(raw)
    raw = raw.replace('\\"', '"').replace('\\/', '/')
    return re.sub(r'\s+', ' ', raw).strip()

# ==========================================
# 1. FETCH TARGETS DIRECTLY FROM WEBSITE DB
# ==========================================
def fetch_saved_streamers_from_website():
    """Fetches all target streamers saved in your website database."""
    print("🌐 Connecting to website to fetch saved streamer targets...")
    session = requests.Session()
    try:
        res = session.post(
            WEBSITE_URL.strip(),
            data={"action": "load_all"},
            timeout=25,
            impersonate="chrome124"
        )
        if res.status_code == 200:
            data = res.json()
            if data.get("success"):
                streamers = data.get("streamers", [])
                targets = [clean_model_name(s.get("name", "")) for s in streamers if s.get("name")]
                print(f"✅ Successfully loaded {len(targets)} saved streamers from website database!")
                return targets
            else:
                print(f"⚠️ Website returned error: {res.text[:150]}")
        else:
            print(f"❌ Failed to reach website. HTTP {res.status_code}: {res.text[:150]}")
    except Exception as e:
        print(f"❌ Error fetching targets from website: {e}")

    print("⚠️ Fallback to internal test targets.")
    return ["mia_rom", "dellris", "_stayhere"]

# ==========================================
# 2. FETCH CHATURBATE ROOMS (CLOUDFLARE PROXY)
# ==========================================
def fetch_all_live_rooms():
    """Fetches live room directory with 0.3s - 0.4s dynamic random jitter."""
    session = requests.Session()
    headers = {"x-tracker-key": CLOUDFLARE_KEY}
    
    all_rooms = []
    offset = 0
    batch_size = 500
    page_num = 1
    start_time = time.time()

    print("\n🚀 Fetching global live rooms via Cloudflare Worker...")

    while True:
        url = f"{WORKER_URL}?offset={offset}"
        try:
            res = session.get(url, headers=headers, timeout=20)
            if res.status_code != 200:
                print(f"⚠️️ Batch {page_num} stopped (HTTP {res.status_code}).")
                break

            data = res.json()
            rooms = data.get('results', []) if isinstance(data, dict) else []
            total_count = data.get('count', 0) if isinstance(data, dict) else len(rooms)

            if not rooms:
                break

            all_rooms.extend(rooms)
            print(f"  ● Batch {page_num} (Offset {offset}): +{len(rooms)} rooms | Total: {len(all_rooms)} / {total_count}")

            if len(all_rooms) >= total_count or len(rooms) < batch_size:
                break

            offset += batch_size
            page_num += 1

            # Dynamic Random Jitter (0.30s to 0.40s)
            time.sleep(round(random.uniform(0.30, 0.40), 3))

        except Exception as e:
            print(f"❌ Error in batch {page_num}: {e}")
            break

    elapsed = round(time.time() - start_time, 2)
    print(f"✅ Collected {len(all_rooms)} live rooms in {elapsed}s.")
    return all_rooms

# ==========================================
# 3. POST TELEMETRY BACK TO WEBSITE
# ==========================================
def sync_payload_to_website(payload):
    """Sends matched status telemetry to website sync_tracker endpoint."""
    print(f"\n📡 Syncing telemetry for {len(payload)} streamers to website database...")
    session = requests.Session()
    
    post_data = {
        "action": "sync_tracker",
        "secret": TRACKER_SECRET_KEY,
        "payload": json.dumps(payload, ensure_ascii=False)
    }

    try:
        res = session.post(
            WEBSITE_URL.strip(),
            data=post_data,
            timeout=30,
            impersonate="chrome124"
        )
        if res.status_code == 200:
            try:
                ret = res.json()
                if ret.get("success"):
                    print(f"🎉 WEBSITE SYNC SUCCESS! Updated: {ret.get('updated', len(payload))} streamers.")
                    return True
                else:
                    print(f"❌ Website rejected sync: {ret.get('message')}")
            except Exception:
                print(f"⚠️ Website returned non-JSON response:\n{res.text[:300]}")
        else:
            print(f"❌ HTTP Error {res.status_code} during sync:\n{res.text[:300]}")
    except Exception as e:
        print(f"❌ Connection error while syncing to website: {e}")

    return False

# ==========================================
# MAIN ROUTINE
# ==========================================
def main():
    print("=" * 70)
    print("🎯 LIVE LOUNGE AUTO-SYNC TRACKER ENGINE")
    print("=" * 70)

    # Step 1: Target Streamers from Website
    target_list = fetch_saved_streamers_from_website()
    if not target_list:
        print("❌ No target streamers found. Exiting.")
        return

    # Step 2: Global Live Rooms from Cloudflare
    global_rooms = fetch_all_live_rooms()

    # Step 3: Fast In-Memory Map
    print("\n⚡ Matching targets against live platform data...")
    online_map = {clean_model_name(r.get('username', '')): r for r in global_rooms if r.get('username')}

    payload_for_website = []
    live_count = 0

    for target in target_list:
        target_name = clean_model_name(target)
        if target_name in online_map:
            room = online_map[target_name]
            raw_show = str(room.get('current_show', 'public')).lower()

            # Align status with stream.php & app.js: 'public', 'private', 'others'
            if raw_show in ['private', 'ticket_show', 'vip']:
                status = 'private'
            elif raw_show in ['away', 'hidden', 'group_show', 'club_show']:
                status = 'others'
            else:
                status = 'public'

            subj = clean_subject(room.get('room_subject', ''))
            viewers = int(room.get('num_users', 0))

            payload_for_website.append({
                "name": target_name,
                "status": status,
                "viewers": viewers,
                "subject": subj
            })
            live_count += 1
        else:
            payload_for_website.append({
                "name": target_name,
                "status": "offline",
                "viewers": 0,
                "subject": ""
            })

    # Step 4: Push to Website Database
    sync_payload_to_website(payload_for_website)

    # Step 5: Terminal Summary
    print("=" * 70)
    print(f"📊 SUMMARY:")
    print(f"● Total Target Streamers : {len(target_list)}")
    print(f"● Currently Online       : {live_count}")
    print(f"● Currently Offline      : {len(target_list) - live_count}")
    print("=" * 70)

if __name__ == "__main__":
    main()
    
