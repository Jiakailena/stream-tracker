import sys
import subprocess
import time
import json
import re
import random
import html as html_lib
from pathlib import Path

# Automatic curl_cffi installation check
try:
    from curl_cffi import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
    from curl_cffi import requests

# ==========================================
# CONFIGURATION & SETTINGS
# ==========================================
WORKER_URL = "https://cb-feed-proxy.jiakailena.workers.dev"
TRACKER_KEY = "jitul_tracker_key_2026"
TARGET_FILE = "streamers.txt"   # 2000 targets listed one per line (optional)

# Fallback targets if file is not found
FALLBACK_TARGETS = ["mia_rom", "dellris", "_stayhere"]

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def load_target_streamers() -> list:
    """Loads up to 2000 target usernames into memory."""
    target_path = Path(TARGET_FILE)
    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            targets = [line.strip().lower() for line in f if line.strip() and not line.startswith("#")]
        print(f"📋 Loaded {len(targets)} target streamers from {TARGET_FILE}")
        return targets
    print(f"⚠️ {TARGET_FILE} not found. Using fallback test targets.")
    return [t.lower() for t in FALLBACK_TARGETS]

def clean_subject(raw: str) -> str:
    """Decodes unicode, cleans html entities and removes extra whitespace."""
    if not raw:
        return ""
    try:
        raw = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), raw)
    except Exception:
        pass
    raw = html_lib.unescape(raw)
    raw = raw.replace('\\"', '"').replace('\\/', '/')
    return re.sub(r'\s+', ' ', raw).strip()

def extract_goal_tokens(text: str):
    """Accurately extracts goal tokens left/remaining from room subject."""
    if not text:
        return None
    # Pattern 1: [1070 tokens left] or [827 tokens remaining] or [500]
    m1 = re.search(r'\[[^\d\]]*(\d+)[^\]]*\]', text)
    if m1:
        return int(m1.group(1))
    
    # Pattern 2: 500 tokens / 500 tk / 500 remaining
    m2 = re.search(r'(\d+)\s*(?:tokens?|tk|remaining|left)\b', text, re.I)
    if m2:
        return int(m2.group(1))
        
    return None

# ==========================================
# CORE PAGINATION ENGINE (0.3s - 0.4s JITTER)
# ==========================================
def fetch_all_live_rooms():
    """
    Fetches the full platform feed across batches with 0.3s-0.4s jitter.
    Bypasses datacenter blocks via Cloudflare Worker.
    """
    session = requests.Session()
    headers = {"x-tracker-key": TRACKER_KEY}
    
    all_rooms = []
    offset = 0
    batch_size = 500
    page_num = 1
    start_time = time.time()

    print("🚀 Starting ultra-safe paginated fetch from Cloudflare Worker...")

    while True:
        url = f"{WORKER_URL}?offset={offset}"
        try:
            res = session.get(url, headers=headers, timeout=20)
            
            if res.status_code != 200:
                print(f"❌ Batch {page_num} failed with status {res.status_code}. Details: {res.text[:120]}")
                break

            data = res.json()
            rooms = data.get('results', []) if isinstance(data, dict) else []
            total_count = data.get('count', 0) if isinstance(data, dict) else len(rooms)

            if not rooms:
                print("ℹ️ No more rooms returned. Finished pagination.")
                break

            all_rooms.extend(rooms)
            print(f"  ● Batch {page_num} (Offset {offset}): +{len(rooms)} rooms | Total: {len(all_rooms)} / {total_count}")

            # Stop conditions
            if len(all_rooms) >= total_count or len(rooms) < batch_size:
                break

            offset += batch_size
            page_num += 1

            # DYNAMIC RANDOM JITTER: 0.3s to 0.4s safe micro-pause
            jitter_delay = round(random.uniform(0.30, 0.40), 3)
            time.sleep(jitter_delay)

        except Exception as e:
            print(f"❌ Exception in batch {page_num}: {e}")
            break

    elapsed = round(time.time() - start_time, 2)
    print(f"✅ Download completed! {len(all_rooms)} live rooms collected in {elapsed}s.\n")
    return all_rooms

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    print("=" * 70)
    print("🎯 CHATURBATE HIGH-SPEED AFFILIATE TELEMETRY TRACKER")
    print("=" * 70)

    target_list = load_target_streamers()
    global_rooms = fetch_all_live_rooms()

    if not global_rooms:
        print("❌ Empty room feed received. Exiting.")
        return

    # In-memory dictionary hashmap (Lookup in O(1) ~ 0.002 seconds)
    print("⚡ Building fast in-memory user map...")
    online_map = {r.get('username', '').lower(): r for r in global_rooms if 'username' in r}

    matched_results = []
    live_count = 0

    for target in target_list:
        target_clean = target.lower()
        
        if target_clean in online_map:
            room = online_map[target_clean]
            raw_show = room.get('current_show', 'public').lower()
            
            # Map platform status to standardized states
            if raw_show in ['private', 'ticket_show', 'vip']:
                status = 'private'
            elif raw_show in ['away', 'hidden', 'group_show', 'club_show']:
                status = 'away'
            else:
                status = 'public'

            subj = clean_subject(room.get('room_subject', ''))
            tokens = extract_goal_tokens(subj)
            viewers = int(room.get('num_users', 0))
            duration_mins = int(room.get('seconds_online', 0)) // 60
            followers = int(room.get('num_followers', 0))

            telemetry = {
                "username": target,
                "status": status,
                "raw_status": raw_show,
                "viewers": viewers,
                "tokens": tokens,
                "subject": subj,
                "online_mins": duration_mins,
                "followers": followers,
                "is_hd": room.get('is_hd', False),
                "is_new": room.get('is_new', False),
                "image_preview": room.get('image_url_360x270', '')
            }
            live_count += 1
        else:
            telemetry = {
                "username": target,
                "status": "offline",
                "raw_status": "offline",
                "viewers": 0,
                "tokens": None,
                "subject": "",
                "online_mins": 0,
                "followers": 0,
                "is_hd": False,
                "is_new": False,
                "image_preview": ""
            }

        matched_results.append(telemetry)

    # Save output to telemetry json
    output_file = Path("telemetry_snapshot.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(matched_results, f, indent=2, ensure_ascii=False)

    print("=" * 70)
    print(f"📊 SUMMARY REPORT:")
    print(f"● Total Target Streamers : {len(target_list)}")
    print(f"● Currently Online       : {live_count}")
    print(f"● Currently Offline      : {len(target_list) - live_count}")
    print(f"● Telemetry exported to  : {output_file.resolve()}")
    print("=" * 70)

    # Preview sample matched targets
    print("\n🔍 LIVE TARGET PREVIEWS:")
    for res in matched_results:
        if res['status'] != 'offline':
            st_color = "🟢" if res['status'] == 'public' else ("🔒" if res['status'] == 'private' else "🟡")
            print(f"{st_color} {res['username'].upper()} | Status: {res['status'].upper()} | Viewers: {res['viewers']} | Online: {res['online_mins']}m")
            if res['tokens'] is not None:
                print(f"   🎯 Tokens Left: {res['tokens']}")
            if res['subject']:
                print(f"   📝 Subject: {res['subject'][:70]}...")
            print("-" * 50)

if __name__ == "__main__":
    main()
    
