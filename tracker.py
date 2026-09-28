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
adapter = HTTPAdapter(pool_connections=30, pool_maxsize=30, max_retries=Retry(total=1, backoff_factor=0.2))
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

def fetch_chaturbate_global_feed():
    """
    Sequentially traverses Chaturbate's official API feed using 'next' URLs.
    Takes only 2-3 seconds total because of persistent HTTP connection reuse.
    """
    rooms_map = {}
    url = "https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9w8Zb&client_ip=request_ip&format=json&limit=500"
    headers = {'User-Agent': 'Mozilla/5.0'}

    print("Fetching worldwide online rooms from Chaturbate API...")
    for page in range(16):
        try:
            r = session.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                print(f"API notice on page {page+1}: status {r.status_code}")
                break
            
            data = r.json()
            results = data.get('results', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not results:
                break

            for rm in results:
                if isinstance(rm, dict):
                    u = rm.get('username', '').lower()
                    if u:
                        rooms_map[u] = {
                            'viewers': int(rm.get('num_users', 0) or 0),
                            'subject': str(rm.get('room_subject', '') or '').strip(),
                            'show': str(rm.get('current_show', 'public') or '').lower()
                        }

            url = data.get('next') if isinstance(data, dict) else None
            if not url:
                break
        except Exception as e:
            print(f"Feed error on page {page+1}: {e}")
            break

    print(f"API Feed fetched {len(rooms_map)} active rooms worldwide.")
    return rooms_map

def direct_check_unmapped_streamer(username):
    """20-Worker Concurrency fallback for missing streamers"""
    url = f"https://chaturbate.com/{username}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    cookies = {
        'ag_consent': '1', 'age_verified': '1', 'consent_accepted': '1', 'warning_accepted': '1'
    }
    try:
        res = session.get(url, headers=headers, cookies=cookies, timeout=7)
        if res.status_code == 200:
            html = res.text
            clean_html = html.replace('\\u0022', '"').replace('\\"', '"')

            status_match = re.search(r'"room_status"\s*:\s*"([a-zA-Z0-9_-]+)"', clean_html)
            if status_match:
                raw_status = status_match.group(1).lower()
                if raw_status in ['offline', 'disabled']:
                    return None

                mapped_status = 'public'
                if raw_status in ['private', 'ticket_show', 'vip']:
                    mapped_status = 'private'
                elif raw_status in ['away', 'hidden', 'group_show', 'club_show']:
                    mapped_status = 'others'

                viewers = 0
                mv = re.search(r'"num_users"\s*:\s*(\d+)', clean_html)
                if mv:
                    viewers = int(mv.group(1))

                subject = ''
                ms = re.search(r'"room_subject"\s*:\s*"([^"]*)"', clean_html)
                if ms:
                    sub_raw = ms.group(1).strip()
                    try:
                        subject = bytes(sub_raw, 'utf-8').decode('unicode_escape')
                    except Exception:
                        subject = sub_raw

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

    saved_set = [s['name'].lower() for s in raw_streamers]
    print(f"Tracking {len(saved_set)} streamers...")

    # 3. Fetch worldwide API feed (Scalable for 10,000+ models)
    global_rooms = fetch_chaturbate_global_feed()

    # 4. Instant O(1) matching
    status_payload = []
    found_online = set()

    for name in saved_set:
        if name in global_rooms:
            rm = global_rooms[name]
            show = rm['show']
            mapped_status = 'public'
            if show in ['private', 'ticket_show']:
                mapped_status = 'private'
            elif show in ['away', 'hidden', 'group_show', 'club_show']:
                mapped_status = 'others'

            status_payload.append({
                'name': name,
                'status': mapped_status,
                'viewers': rm['viewers'],
                'subject': rm['subject']
            })
            found_online.add(name)

    # 5. Fast Multi-threaded 20-Workers Check for any missing models
    unmapped = [name for name in saved_set if name not in found_online]
    if unmapped:
        print(f"Checking {len(unmapped)} unmapped streamers with 20 parallel workers...")
        with ThreadPoolExecutor(max_workers=20) as executor:
            direct_results = executor.map(direct_check_unmapped_streamer, unmapped)
            for r in direct_results:
                if r:
                    status_payload.append(r)
                    found_online.add(r['name'])

    # 6. Offline streamers
    for name in set(saved_set) - found_online:
        status_payload.append({
            'name': name,
            'status': 'offline',
            'viewers': 0,
            'subject': ''
        })

    # Terminal Log Output
    live_count = sum(1 for x in status_payload if x['status'] != 'offline')
    print(f"\n--- VERIFIED STATUS REPORT ---")
    print(f"Total LIVE: {live_count}, Total OFFLINE: {len(saved_set) - live_count}")
    for item in status_payload:
        if item['status'] != 'offline':
            print(f"-> [{item['name'].upper()}] Status: {item['status']} | Viewers: {item['viewers']} | Subject: '{item['subject']}'")
    print("------------------------------\n")

    # 7. Push 1 single payload to database
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
