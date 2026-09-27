import json
import re
import sys
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
    """Paginates through Chaturbate's API to fetch ALL live rooms globally (~5000-8000 total)"""
    all_rooms = []
    limit = 500
    offset = 0
    max_pages = 25  # Safety cap (up to 12,500 models)

    print("Fetching global live rooms via pagination...")
    for _ in range(max_pages):
        url = f"https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9w8Zb&client_ip=request_ip&format=json&limit={limit}&offset={offset}"
        try:
            r = session.get(url, timeout=20)
            data = r.json()
            results = data.get('results', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            
            if not results:
                break
                
            all_rooms.extend(results)
            if len(results) < limit:
                break
                
            offset += limit
        except Exception as e:
            print(f"Pagination notice at offset {offset}: {e}")
            break

    print(f"Total live rooms fetched across Chaturbate: {len(all_rooms)}")
    return all_rooms

def main():
    # 1. Bypass InfinityFree Firewall
    bypass_infinityfree(ENDPOINT_URL)

    # 2. Fetch saved streamers and their current state in DB
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

    # Map previous state in DB for delta comparison
    saved_streamers_map = {s['name'].lower(): int(s.get('is_online', 0)) for s in raw_streamers}
    saved_set = set(saved_streamers_map.keys())
    print(f"Total streamers in library: {len(saved_set)}")

    # 3. Fetch all active live rooms globally
    live_rooms = fetch_all_chaturbate_live_rooms()

    # 4. Instant O(1) matching against saved streamers
    current_live_matches = {}
    for room in live_rooms:
        if not isinstance(room, dict):
            continue
        u_name = room.get('username', '').lower()
        if u_name in saved_set:
            current_show = room.get('current_show', 'public').lower()
            viewers = room.get('num_users', 0)
            subject = room.get('room_subject', '')

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

    # 5. Delta Sync calculation:
    # Send all CURRENTLY ONLINE + ONLY those who just went OFFLINE
    status_payload = []

    # A. All currently online streamers
    for u_name, data in current_live_matches.items():
        status_payload.append(data)

    # B. Streamers who were previously online in DB, but are now offline
    for u_name, prev_online in saved_streamers_map.items():
        if prev_online == 1 and u_name not in current_live_matches:
            status_payload.append({
                'name': u_name,
                'status': 'offline',
                'viewers': 0,
                'subject': ''
            })

    print(f"Matched {len(current_live_matches)} ONLINE out of {len(saved_set)} saved streamers.")
    print(f"Syncing {len(status_payload)} delta changes to database...")

    # 6. Send lightweight payload to database
    if status_payload:
        try:
            sync_res = session.post(ENDPOINT_URL, data={
                'action': 'sync_tracker',
                'secret': TRACKER_SECRET,
                'payload': json.dumps(status_payload)
            }, timeout=20)
            print("Database Sync Result:", sync_res.json())
        except Exception as e:
            print(f"Sync error: {e}")
    else:
        print("No status change detected. Database is already up to date.")

if __name__ == '__main__':
    main()
    
