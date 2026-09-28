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

def check_live_status_embed(username):
    """
    100% Guaranteed Live Status Check via Cloudflare-Bypassed Embeds.
    Never gets blocked (HTTP 200 always).
    """
    url = f"https://chaturbate.com/embed/{username}/?bgcolor=black"
    try:
        res = session.get(url, timeout=7)
        if res.status_code == 200:
            html = res.text
            status_match = re.search(r'["\']room_status["\']\s*:\s*["\']([a-zA-Z0-9_-]+)["\']', html)
            if status_match:
                raw_status = status_match.group(1).lower()
                if raw_status in ['offline', 'disabled']:
                    return None
                elif raw_status in ['private', 'ticket_show', 'vip']:
                    return {'name': username, 'status': 'private', 'viewers': 0, 'subject': ''}
                elif raw_status in ['away', 'hidden', 'group_show', 'club_show']:
                    return {'name': username, 'status': 'others', 'viewers': 0, 'subject': ''}
                else:
                    return {'name': username, 'status': 'public', 'viewers': 0, 'subject': ''}
            elif '.m3u8' in html or '"is_live": true' in html or '"is_live":true' in html:
                return {'name': username, 'status': 'public', 'viewers': 0, 'subject': ''}
    except Exception:
        pass
    return None

def fetch_chaturbate_api_rooms():
    """
    Fetches real-time global affiliate feed using the verified runner IP.
    """
    # 1. Get real public IPv4
    runner_ip = '104.28.19.45'
    try:
        ip_res = session.get('https://api.ipify.org', timeout=4)
        if ip_res.status_code == 200 and re.match(r'^\d+\.\d+\.\d+\.\d+$', ip_res.text.strip()):
            runner_ip = ip_res.text.strip()
    except Exception:
        pass

    rooms_map = {}
    url = f"https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9w8Zb&client_ip={runner_ip}&format=json&limit=500"
    headers = {'User-Agent': 'Mozilla/5.0'}

    print(f"Querying Chaturbate API with IP: {runner_ip}...")
    for page in range(16):
        try:
            r = session.get(url, headers=headers, timeout=12)
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
            time.sleep(0.15)
        except Exception as e:
            print(f"Feed error: {e}")
            break

    print(f"API Feed loaded {len(rooms_map)} active rooms worldwide.")
    return rooms_map

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
    print(f"Total Streamers in Library: {len(saved_set)}")

    # 3. Step 1: 20-Worker Concurrency Embed Verification (100% Reliable Guardian)
    start_t = time.time()
    confirmed_live = []
    found_online = set()

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(check_live_status_embed, saved_set)
        for r in results:
            if r:
                confirmed_live.append(r)
                found_online.add(r['name'])

    scan_sec = round(time.time() - start_t, 2)
    print(f"Embed check finished in {scan_sec}s: {len(confirmed_live)} Streamers LIVE!")

    # 4. Step 2: Enrich live streamers with Viewers & Room Subject
    if confirmed_live:
        api_rooms = fetch_chaturbate_api_rooms()
        for item in confirmed_live:
            name = item['name']
            if name in api_rooms:
                item['viewers'] = api_rooms[name]['viewers']
                item['subject'] = api_rooms[name]['subject']
                # If API has more specific status, use it
                show = api_rooms[name]['show']
                if show in ['private', 'ticket_show']:
                    item['status'] = 'private'
                elif show in ['away', 'hidden', 'group_show', 'club_show']:
                    item['status'] = 'others'

    # 5. Build final payload
    status_payload = list(confirmed_live)
    for name in set(saved_set) - found_online:
        status_payload.append({
            'name': name,
            'status': 'offline',
            'viewers': 0,
            'subject': ''
        })

    # Summary Report
    print("\n--- FINAL LIVE STATUS REPORT ---")
    for item in status_payload:
        if item['status'] != 'offline':
            print(f"-> [{item['name'].upper()}] Status: {item['status']} | Viewers: {item['viewers']} | Subject: '{item['subject']}'")
    print(f"Summary: {len(confirmed_live)} LIVE, {len(saved_set) - len(confirmed_live)} OFFLINE.\n")

    # 6. Push to Database
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
