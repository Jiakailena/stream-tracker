import json
import re
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor
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

def fetch_chaturbate_primary_feed():
    """Single safe request to Chaturbate feed to avoid 429 rate-limiting"""
    url = "https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9w8Zb&client_ip=request_ip&format=json"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=25)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                return data.get('results', [])
            elif isinstance(data, list):
                return data
    except Exception as e:
        print(f"Chaturbate primary feed notice: {e}")
    return []

def direct_check_streamer(username):
    """Controlled direct room check with 0.1s gentle delay"""
    url = f"https://chaturbate.com/embed/{username}/?bgcolor=black"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        time.sleep(0.05)  # Gentle delay to respect server
        res = requests.get(url, headers=headers, timeout=7)
        if res.status_code == 200:
            html = res.text
            is_live = False
            if '"is_live": true' in html or '"is_live":true' in html or '.m3u8' in html:
                is_live = True
            elif 'room_status' in html and '"room_status": "offline"' not in html and '"room_status":"offline"' not in html:
                if '"room_status": "public"' in html or '"room_status":"public"' in html:
                    is_live = True

            if is_live:
                status = 'public'
                if '"room_status": "private"' in html or '"room_status":"private"' in html or 'ticket_show' in html:
                    status = 'private'
                elif '"room_status": "away"' in html or '"room_status": "hidden"' in html or 'hidden' in html:
                    status = 'others'

                viewers = 0
                m_view = re.search(r'"num_users":\s*(\d+)', html)
                if m_view:
                    viewers = int(m_view.group(1))

                return {
                    'name': username,
                    'status': status,
                    'viewers': viewers,
                    'subject': ''
                }
    except Exception:
        pass
    return None

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

    saved_set = set(s['name'].lower() for s in raw_streamers)
    print(f"Checking {len(saved_set)} streamers from library...")

    # 3. Check Chaturbate primary feed (Single Request)
    primary_rooms = fetch_chaturbate_primary_feed()
    status_payload = []
    found_online = set()

    for room in primary_rooms:
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

            status_payload.append({
                'name': u_name,
                'status': mapped_status,
                'viewers': viewers,
                'subject': subject
            })
            found_online.add(u_name)

    # 4. Gentle Batch Checking for remaining streamers (Workers = 5)
    remaining = list(saved_set - found_online)
    if remaining:
        print(f"Running gentle batch check for {len(remaining)} streamers...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            batch_results = executor.map(direct_check_streamer, remaining)
            for r in batch_results:
                if r:
                    status_payload.append(r)
                    found_online.add(r['name'])

    # 5. Mark true offline streamers
    for offline_name in saved_set - found_online:
        status_payload.append({
            'name': offline_name,
            'status': 'offline',
            'viewers': 0,
            'subject': ''
        })

    print(f"Summary: {len(found_online)} ONLINE, {len(saved_set) - len(found_online)} OFFLINE.")

    # 6. Always push full sync + heartbeat to stream.php
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
    
