import json
import re
import sys
import time
import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

ENDPOINT_URL = "https://stacy.infinityfreeapp.com/stream.php"
TRACKER_SECRET = "jitul_tracker_key_2026"

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

def bypass_infinityfree(url):
    """Bypasses InfinityFree's aes.js firewall automatically"""
    try:
        res = session.get(url, timeout=15)
        if 'slowAES.decrypt' in res.text:
            matches = re.findall(r'toNumbers\("([0-9a-fA-F]+)"\)', res.text)
            if len(matches) >= 3:
                a_key = bytes.fromhex(matches[0])
                b_iv = bytes.fromhex(matches[1])
                c_cipher = bytes.fromhex(matches[2])

                cipher = Cipher(algorithms.AES(a_key), modes.CBC(b_iv), backend=default_backend())
                decryptor = cipher.decryptor()
                cookie_val = (decryptor.update(c_cipher) + decryptor.finalize()).hex()

                session.cookies.set('__test', cookie_val, domain='stacy.infinityfreeapp.com', path='/')
                print("Firewall bypassed successfully!")
                return True
        return True
    except Exception as e:
        print(f"Bypass error: {e}")
        return False

def fetch_all_chaturbate_live_rooms():
    """Paced pagination through Chaturbate's API with 0.5s delay to prevent 429 rate limit"""
    all_rooms = []
    limit = 500
    offset = 0
    max_pages = 25  # Covers up to 12,500 models

    print("Fetching global live rooms via paced pagination...")
    for page in range(max_pages):
        url = f"https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9w8Zb&client_ip=request_ip&format=json&limit={limit}&offset={offset}"
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                data = r.json()
                results = data.get('results', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                if not results:
                    break
                all_rooms.extend(results)
                print(f"Page {page+1}: fetched {len(results)} rooms (Total so far: {len(all_rooms)})")
                if len(results) < limit:
                    break
            else:
                print(f"Notice on page {page+1}: status code {r.status_code}")
                break
        except Exception as e:
            print(f"Error on page {page+1}: {e}")
            break

        offset += limit
        time.sleep(0.5)  # 0.5s gentle gap to eliminate rate limit completely

    print(f"Global scanning complete. Total online rooms: {len(all_rooms)}")
    return all_rooms

def main():
    # 1. Bypass InfinityFree Security
    bypass_infinityfree(ENDPOINT_URL)

    # 2. Fetch saved streamers from database
    try:
        res = session.post(ENDPOINT_URL, data={'action': 'load_all'}, timeout=15)
        site_data = res.json()
        raw_streamers = site_data.get('streamers', [])
    except Exception as e:
        print(f"Failed to load streamers: {e}")
        return

    if not raw_streamers:
        print("No saved streamers found in library.")
        return

    # Map current states in DB
    saved_streamers_map = {s['name'].lower(): int(s.get('is_online', 0)) for s in raw_streamers}
    saved_set = set(saved_streamers_map.keys())
    print(f"Total streamers in library: {len(saved_set)}")

    # 3. Fetch all active live rooms globally with paced delay
    live_rooms = fetch_all_chaturbate_live_rooms()

    # 4. Instant O(1) matching & status mapping
    current_live_matches = {}
    for room in live_rooms:
        if not isinstance(room, dict):
            continue
        u_name = room.get('username', '').lower()
        if u_name in saved_set:
            current_show = room.get('current_show', 'public').lower()
            viewers = room.get('num_users', 0)
            subject = room.get('room_subject', '')

            # Exact status mapping:
            # - public -> public
            # - private / ticket_show -> private
            # - away / hidden / group_show / club_show -> others
            mapped_status = 'public'
            if current_show in ['private', 'ticket_show']:
                mapped_status = 'private'
            elif current_show in ['away', 'hidden', 'group_show', 'club_show'] or 'hidden' in current_show:
                mapped_status = 'others'

            current_live_matches[u_name] = {
                'name': u_name,
                'status': mapped_status,
                'viewers': viewers,
                'subject': subject
            }

    # 5. Build payload (Online streamers + recently went offline delta)
    status_payload = []

    # All currently live streamers
    for u_name, data in current_live_matches.items():
        status_payload.append(data)

    # Streamers that were online in DB, but just went offline
    for u_name, prev_online in saved_streamers_map.items():
        if prev_online == 1 and u_name not in current_live_matches:
            status_payload.append({
                'name': u_name,
                'status': 'offline',
                'viewers': 0,
                'subject': ''
            })

    print(f"Found {len(current_live_matches)} ONLINE out of {len(saved_set)} streamers.")
    print(f"Sending {len(status_payload)} updates to database...")

    # 6. Push updates + guaranteed heartbeat
    try:
        sync_res = session.post(ENDPOINT_URL, data={
            'action': 'sync_tracker',
            'secret': TRACKER_SECRET,
            'payload': json.dumps(status_payload)
        }, timeout=20)
        print("Database Sync Result:", sync_res.json())
    except Exception as e:
        print(f"Sync error: {e}")

if __name__ == '__main__':
    main()
    
