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
adapter = HTTPAdapter(pool_connections=35, pool_maxsize=35, max_retries=Retry(total=1, backoff_factor=0.2))
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

def check_streamer_status(username):
    """Accurate, decompressed live checker with exact status targeting"""
    url = f"https://chaturbate.com/embed/{username}/?bgcolor=black"
    try:
        res = session.get(url, timeout=7)
        if res.status_code != 200:
            return None

        html = res.text

        # 1. Exact room_status JSON targeting
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
            # Fallback: check live video manifest
            if '.m3u8' in html or '"is_live": true' in html or '"is_live":true' in html:
                mapped_status = 'public'
            else:
                return None

        # Viewer Count
        viewers = 0
        m_view = re.search(r'["\']num_users["\']\s*:\s*(\d+)', html)
        if m_view:
            viewers = int(m_view.group(1))

        # Room Subject
        subject = ''
        m_sub = re.search(r'["\']room_subject["\']\s*:\s*["\']([^"\']*)["\']', html)
        if m_sub:
            subject = m_sub.group(1)

        return {
            'name': username,
            'status': mapped_status,
            'viewers': viewers,
            'subject': subject
        }
    except Exception:
        pass
    return None

def main():
    # 1. Bypass InfinityFree Security
    bypass_infinityfree(ENDPOINT_URL)

    # 2. Fetch saved streamers
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
    print(f"Checking {len(saved_set)} streamers with multi-threading...")

    # 3. Concurrent verified checks (25 workers)
    status_payload = []
    found_online = set()

    start_t = time.time()
    with ThreadPoolExecutor(max_workers=25) as executor:
        results = executor.map(check_streamer_status, saved_set)
        for r in results:
            if r:
                status_payload.append(r)
                found_online.add(r['name'])

    elapsed = round(time.time() - start_t, 2)
    print(f"Scan finished in {elapsed}s: Found {len(found_online)} LIVE out of {len(saved_set)}.")

    # 4. Offline Streamers
    for name in set(saved_set) - found_online:
        status_payload.append({
            'name': name,
            'status': 'offline',
            'viewers': 0,
            'subject': ''
        })

    # 5. Push to Database
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
