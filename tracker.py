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
    """Bypasses InfinityFree's aes.js / testcookie challenge automatically"""
    try:
        res = session.get(url, timeout=15)
        if 'slowAES.decrypt' in res.text:
            print("Detected InfinityFree firewall challenge. Solving security cookie...")
            matches = re.findall(r'toNumbers\("([0-9a-fA-F]+)"\)', res.text)
            if len(matches) >= 3:
                a_key = bytes.fromhex(matches[0])
                b_iv = bytes.fromhex(matches[1])
                c_cipher = bytes.fromhex(matches[2])

                cipher = Cipher(algorithms.AES(a_key), modes.CBC(b_iv), backend=default_backend())
                decryptor = cipher.decryptor()
                cookie_val = (decryptor.update(c_cipher) + decryptor.finalize()).hex()

                session.cookies.set('__test', cookie_val, domain='stacy.infinityfreeapp.com', path='/')
                print("Firewall bypassed successfully! __test cookie set.")
                return True
        return True
    except Exception as e:
        print(f"Bypass error: {e}")
        return False

def fetch_chaturbate_live():
    url = "https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9w8Zb&format=json"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=30)
        data = r.json()
        # Chaturbate wraps live rooms inside a 'results' dictionary
        if isinstance(data, dict):
            if 'results' in data and isinstance(data['results'], list):
                return data['results']
            elif 'rooms' in data and isinstance(data['rooms'], list):
                return data['rooms']
            elif 'data' in data and isinstance(data['data'], list):
                return data['data']
            return []
        elif isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"Error fetching Chaturbate: {e}")
        return []

def main():
    # 1. Bypass InfinityFree Security
    bypass_infinityfree(ENDPOINT_URL)

    # 2. Fetch saved streamers from database
    try:
        res = session.post(ENDPOINT_URL, data={'action': 'load_all'}, timeout=15)
        site_data = res.json()
        saved_streamers = [s['name'].lower() for s in site_data.get('streamers', [])]
    except Exception as e:
        print(f"Failed to load streamers: {e}")
        return

    if not saved_streamers:
        print("No saved streamers found in library.")
        return

    saved_set = set(saved_streamers)
    print(f"Successfully loaded {len(saved_set)} streamers from library.")

    # 3. Fetch Chaturbate live rooms
    print("Scanning Chaturbate live rooms...")
    live_rooms = fetch_chaturbate_live()
    print(f"Chaturbate total live rooms: {len(live_rooms)}")

    # 4. Map Statuses
    status_payload = []
    found_online = set()

    for room in live_rooms:
        if not isinstance(room, dict):
            continue
        u_name = room.get('username', '').lower()
        if u_name in saved_set:
            current_show = room.get('current_show', 'public').lower()
            viewers = room.get('num_users', 0)
            subject = room.get('room_subject', '')

            # Status Mapping Rule:
            # - public -> public
            # - private / ticket_show -> private
            # - away / hidden / club_show -> others
            mapped_status = 'public'
            if current_show in ['private', 'ticket_show']:
                mapped_status = 'private'
            elif current_show in ['away', 'hidden', 'group_show', 'club_show'] or 'hidden' in current_show:
                mapped_status = 'others'

            status_payload.append({
                'name': u_name,
                'status': mapped_status,
                'viewers': viewers,
                'subject': subject
            })
            found_online.add(u_name)

    # Offline streamers
    for offline_name in saved_set - found_online:
        status_payload.append({
            'name': offline_name,
            'status': 'offline',
            'viewers': 0,
            'subject': ''
        })

    print(f"Found {len(found_online)} streamer(s) ONLINE right now.")

    # 5. Sync to database
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
    
