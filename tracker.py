import sys
import subprocess
import time
import json
import re
import random
import os
import html as html_lib
from urllib.parse import urlparse

# Auto check for curl_cffi, cryptography and pywebpush
for pkg in ["curl_cffi", "cryptography", "pywebpush"]:
    try:
        __import__(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

from curl_cffi import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from pywebpush import webpush, WebPushException

# ==========================================
# CONFIGURATION & SETTINGS
# ==========================================
WEBSITE_URL = "https://stacy.infinityfreeapp.com/stream.php"
TRACKER_SECRET_KEY = "jitul_tracker_key_2026"

WORKER_URL = "https://cb-feed-proxy.jiakailena.workers.dev"
CLOUDFLARE_KEY = "jitul_tracker_key_2026"

# VAPID Keys for Background Web Push
VAPID_PRIVATE_KEY = "2-2o1-oC0G9S4lP3_ih7XFXDeOM8DTyvY7Jt8RVt4nE"
VAPID_CLAIMS = {"sub": "mailto:admin@infinityfree.com"}

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

def send_web_push_alerts(newly_live_streamers, subscriptions):
    """Sends background Web Push to all registered device tokens"""
    if not newly_live_streamers or not subscriptions:
        return

    print(f"\n🔔 [PUSH] Triggering background push for {len(newly_live_streamers)} newly live streamer(s)...")

    for streamer in newly_live_streamers:
        payload = json.dumps({
            "title": f"⭐ {streamer.upper()} is LIVE!",
            "body": "Streamer started broadcasting. Tap to watch now!",
            "url": WEBSITE_URL
        })

        for sub in subscriptions:
            endpoint = sub.get("endpoint", "")
            p256dh = sub.get("p256dh", "")
            auth = sub.get("auth", "")

            if not endpoint or not p256dh or not auth:
                continue

            sub_info = {
                "endpoint": endpoint,
                "keys": {
                    "p256dh": p256dh,
                    "auth": auth
                }
            }

            try:
                webpush(
                    subscription_info=sub_info,
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=VAPID_CLAIMS,
                    timeout=10
                )
                print(f"  ✅ Push delivered to device: {endpoint[:45]}...")
            except WebPushException as ex:
                print(f"  ❌ WebPush delivery failed: {ex}")
            except Exception as e:
                print(f"  ❌ Unexpected Push error: {e}")

# ==========================================
# INFINITYFREE BYETHOST AES CHALLENGE SOLVER
# ==========================================
def bypass_infinityfree_firewall(session, target_url: str):
    """
    Solves InfinityFree / ByetHost aes.js challenge and injects __test cookie.
    """
    print("🛡️ Checking InfinityFree bot security challenge...")
    try:
        res = session.get(target_url, impersonate="chrome124", timeout=20)
        html = res.text

        if "aes.js" in html or "toNumbers" in html:
            ma = re.search(r'a\s*=\s*toNumbers\(["\']([0-9a-fA-F]+)["\']\)', html)
            mb = re.search(r'b\s*=\s*toNumbers\(["\']([0-9a-fA-F]+)["\']\)', html)
            mc = re.search(r'c\s*=\s*toNumbers\(["\']([0-9a-fA-F]+)["\']\)', html)

            if ma and mb and mc:
                key = bytes.fromhex(ma.group(1))
                iv = bytes.fromhex(mb.group(1))
                ct = bytes.fromhex(mc.group(1))

                cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
                dec = cipher.decryptor()
                cookie_val = (dec.update(ct) + dec.finalize()).hex()

                session.headers["Cookie"] = f"__test={cookie_val}"
                try:
                    domain = urlparse(target_url).netloc
                    session.cookies.set("__test", cookie_val, domain=domain)
                except Exception:
                    pass

                print(f"🔓 Solved InfinityFree Challenge! (__test={cookie_val[:8]}...)")
                verify_res = session.get(target_url, impersonate="chrome124", timeout=20)
                if "aes.js" not in verify_res.text:
                    print("✅ Security cleared! Server is ready to process requests.")
                return True
        else:
            print("✅ Direct connection open (No security challenge triggered).")
            return True
    except Exception as e:
        print(f"⚠️ Firewall check exception: {e}")
    return False

# ==========================================
# 1. FETCH TARGETS DIRECTLY FROM WEBSITE DB
# ==========================================
def fetch_saved_streamers_from_website(session):
    """Fetches all target streamers saved in your website database."""
    print("🌐 Connecting to website to fetch saved streamer targets...")
    try:
        res = session.post(
            WEBSITE_URL,
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
                print(f"⚠️ Batch {page_num} stopped (HTTP {res.status_code}).")
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
# 3. POST ONLY ONLINE TELEMETRY TO WEBSITE
# ==========================================
def sync_payload_to_website(session, online_payload, total_targets_count):
    """Sends ONLY online streamers with total count for ultra-fast sync."""
    print(f"\n📡 Pushing {len(online_payload)} live streamers (out of {total_targets_count}) to website database...")
    
    post_data = {
        "action": "sync_tracker",
        "secret": TRACKER_SECRET_KEY,
        "total_targets": total_targets_count,
        "payload": json.dumps(online_payload, ensure_ascii=False)
    }

    try:
        res = session.post(
            WEBSITE_URL,
            data=post_data,
            timeout=30,
            impersonate="chrome124"
        )
        if res.status_code == 200:
            try:
                ret = res.json()
                if ret.get("success"):
                    print(f"🎉 WEBSITE SYNC SUCCESS! Active online synced: {ret.get('online_synced', len(online_payload))} streamers.")
                    
                    # Trigger background web push if any streamer just went live
                    newly_live = ret.get("newly_live", [])
                    subscriptions = ret.get("subscriptions", [])
                    if newly_live and subscriptions:
                        send_web_push_alerts(newly_live, subscriptions)
                    
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
    print("🎯 LIVE LOUNGE AUTO-SYNC TRACKER ENGINE (BULK OPTIMIZED)")
    print("=" * 70)

    # Initialize shared website session & unlock InfinityFree
    website_session = requests.Session()
    bypass_infinityfree_firewall(website_session, WEBSITE_URL)

    # Step 1: Target Streamers from Website
    target_list = fetch_saved_streamers_from_website(website_session)
    if not target_list:
        print("❌ No target streamers found. Exiting.")
        return

    # Step 2: Global Live Rooms from Cloudflare
    global_rooms = fetch_all_live_rooms()

    # Step 3: Fast In-Memory Map
    print("\n⚡ Matching targets against live platform data...")
    online_map = {clean_model_name(r.get('username', '')): r for r in global_rooms if r.get('username')}

    online_payload = []
    for target in target_list:
        target_name = clean_model_name(target)
        if target_name in online_map:
            room = online_map[target_name]
            raw_show = str(room.get('current_show', 'public')).lower()

            if raw_show in ['private', 'ticket_show', 'vip']:
                status = 'private'
            elif raw_show in ['away', 'hidden', 'group_show', 'club_show']:
                status = 'others'
            else:
                status = 'public'

            subj = clean_subject(room.get('room_subject', ''))
            viewers = int(room.get('num_users', 0))

            online_payload.append({
                "name": target_name,
                "status": status,
                "viewers": viewers,
                "subject": subj
            })

    # Step 4: Push ONLY Online Streamers & Dispatch Alerts
    sync_payload_to_website(website_session, online_payload, len(target_list))

    # Step 5: Terminal Summary
    print("=" * 70)
    print(f"📊 SUMMARY:")
    print(f"● Total Target Streamers : {len(target_list)}")
    print(f"● Currently Online       : {len(online_payload)}")
    print(f"● Currently Offline      : {len(target_list) - len(online_payload)}")
    print("=" * 70)

if __name__ == "__main__":
    main()
