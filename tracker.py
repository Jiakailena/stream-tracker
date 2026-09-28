import json
import re
import sys
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

ENDPOINT_URL = "https://stacy.infinityfreeapp.com/stream.php"
TRACKER_SECRET = "jitul_tracker_key_2026"

session = requests.Session()
adapter = HTTPAdapter(pool_connections=40, pool_maxsize=40, max_retries=Retry(total=1, backoff_factor=0.2))
session.mount('https://', adapter)
session.mount('http://', adapter)

session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
})

def bypass_infinityfree(url):
    """Bypasses InfinityFree's aes.js firewall automatically"""
    try:
        res = session.get(url, timeout=12)
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

def check_live_status_fast(username):
    """Ultra-fast embed status check"""
    url = f"https://chaturbate.com/embed/{username}/?bgcolor=black"
    try:
        res = session.get(url, timeout=7)
        if res.status_code != 200:
            return None

        html = res.text
        status_match = re.search(r'["\']room_status["\']\s*:\s*["\']([a-zA-Z0-9_-]+)["\']', html)
        if status_match:
            raw_status = status_match.group(1).lower()
            if raw_status in ['offline', 'disabled']:
                return None
            elif raw_status in ['private', 'ticket_show', 'vip']:
                mapped_status = 'private'
            elif raw_status in ['away', 'hidden', 'group_show', 'club_show']:
                mapped_status = 'others'
            else:
                mapped_status = 'public'
        else:
            if '.m3u8' in html or '"is_live": true' in html or '"is_live":true' in html:
                mapped_status = 'public'
            else:
                return None

        return {
            'name': username,
            'status': mapped_status,
            'viewers': 0,
            'subject': ''
        }
    except Exception:
        pass
    return None

def fetch_chaturbate_api_feed():
    """Fetches top online rooms from Chaturbate API as quick cache"""
    url = "https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9w8Zb&client_ip=request_ip&format=json"
    headers = {'User-Agent': 'Mozilla/5.0'}
    rooms_map = {}
    try:
        r = session.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            results = data.get('results', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for rm in results:
                u = rm.get('username', '').lower()
                if u:
                    rooms_map[u] = {
                        'viewers': int(rm.get('num_users', 0) or 0),
                        'subject': str(rm.get('room_subject', '') or '').strip()
                    }
    except Exception as e:
        print(f"API feed notice: {e}")
    return rooms_map

def fetch_live_details_from_page(username):
    """Directly extracts viewers and subject from main room page with age-bypass cookies"""
    url = f"https://chaturbate.com/{username}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    }
    cookies = {
        'ag_consent': '1',
        'age_verified': '1',
        'consent_accepted': '1',
        'warning_accepted': '1',
        'has_accepted_terms': '1'
    }
    viewers = 0
    subject = ''
    try:
        r = session.get(url, headers=headers, cookies=cookies, timeout=7)
        if r.status_code == 200:
            html = r.text
            # Extract viewers
            mv = re.search(r'(?:num_users|\\u0022num_users\\u0022|\\\"num_users\\\")\s*:\s*(\d+)', html)
            if mv:
                viewers = int(mv.group(1))

            # Extract subject
            ms = re.search(r'(?:room_subject|\\u0022room_subject\\u0022|\\\"room_subject\\\")\s*:\s*[\"\\]*([^\"\\<\r\n]+)', html)
            if ms:
                sub_raw = ms.group(1).strip()
                try:
                    subject = bytes(sub_raw, "utf-8").decode("unicode_escape")
                except Exception:
                    subject = sub_raw
    except Exception:
        pass
    return viewers, subject

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
        print("No saved streamers found.")
        return

    saved_set = [s['name'].lower() for s in raw_streamers]
    print(f"Verifying {len(saved_set)} streamers with multi-threading...")

    # 3. Parallel live checks
    confirmed_live = []
    found_online = set()

    with ThreadPoolExecutor(max_workers=25) as executor:
        results = executor.map(check_live_status_fast, saved_set)
        for r in results:
            if r:
                confirmed_live.append(r)
                found_online.add(r['name'])

    print(f"Detected {len(confirmed_live)} LIVE streamers! Fetching viewers & room subjects...")

    # 4. Fetch Chaturbate API top rooms for instant data
    api_rooms = fetch_chaturbate_api_feed()

    # 5. Enrich live streamers with peak viewers & subjects
    status_payload = []
    for item in confirmed_live:
        name = item['name']
        if name in api_rooms and api_rooms[name]['viewers'] > 0:
            item['viewers'] = api_rooms[name]['viewers']
            item['subject'] = api_rooms[name]['subject']
        else:
            v, s = fetch_live_details_from_page(name)
            item['viewers'] = v
            item['subject'] = s
        status_payload.append(item)

    # 6. Offline streamers
    for name in set(saved_set) - found_online:
        status_payload.append({
            'name': name,
            'status': 'offline',
            'viewers': 0,
            'subject': ''
        })

    print(f"Payload ready: {len(confirmed_live)} LIVE (with viewers/subjects), {len(saved_set) - len(confirmed_live)} OFFLINE.")

    # 7. Push to Database
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
