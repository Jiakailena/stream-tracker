import json
import re
import sys
import time
import subprocess
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

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate'
}
session.headers.update(BROWSER_HEADERS)

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
                print("InfinityFree firewall bypassed successfully!")
                return True
        return True
    except Exception as e:
        print(f"Bypass error: {e}")
        return False

def check_live_status_embed(username):
    """Fast reliable live status detector via embed"""
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

def fetch_feed_with_curl(url):
    """Bypasses Cloudflare TLS fingerprint blocks using Linux native curl"""
    try:
        cmd = [
            'curl', '-sL', '--compressed',
            '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            '-H', 'Accept: application/json',
            url
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception as e:
        print(f"Curl notice: {e}")
    return None

def fetch_global_chaturbate_rooms():
    """Fetches worldwide active rooms with viewers and subjects"""
    rooms_map = {}
    
    # Try 1: Bulk Feed via Curl
    print("[1/3] Fetching global bulk room feed via curl...")
    bulk_url = "https://chaturbate.com/affiliates/api/onlinerooms/?format=json&wm=9w8Zb"
    data = fetch_feed_with_curl(bulk_url)
    
    # Try 2: Python requests if curl returned None
    if not data:
        try:
            r = session.get(bulk_url, timeout=25)
            if r.status_code == 200:
                data = r.json()
        except Exception:
            pass

    items = data if isinstance(data, list) else (data.get('results', []) if isinstance(data, dict) else [])
    
    if len(items) > 100:
        print(f"Loaded {len(items)} worldwide active rooms successfully!")
        for rm in items:
            if isinstance(rm, dict):
                u = rm.get('username', '').lower()
                if u:
                    rooms_map[u] = {
                        'viewers': int(rm.get('num_users', 0) or 0),
                        'subject': str(rm.get('room_subject', '') or '').strip(),
                        'show': str(rm.get('current_show', 'public') or '').lower()
                    }
        return rooms_map

    # Try 3: Paged Affiliate API via Curl
    print("Bulk feed empty, falling back to paged API...")
    paged_url = "https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9w8Zb&client_ip=request_ip&format=json&limit=500"
    for page in range(16):
        data = fetch_feed_with_curl(paged_url)
        if not data:
            break
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
        paged_url = data.get('next') if isinstance(data, dict) else None
        if not paged_url:
            break

    print(f"Paged API loaded {len(rooms_map)} active rooms.")
    return rooms_map

def fetch_single_room_via_curl(username):
    """Direct room scrape fallback via curl"""
    url = f"https://chaturbate.com/{username}/"
    viewers = 0
    subject = ''
    try:
        cmd = [
            'curl', '-sL', '--compressed',
            '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            '-b', 'ag_consent=1; age_verified=1; warning_accepted=1',
            url
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode == 0 and res.stdout:
            html = res.stdout.replace('\\u0022', '"').replace('\\"', '"')
            mv = re.search(r'"num_users"\s*:\s*(\d+)', html)
            if mv:
                viewers = int(mv.group(1))
            ms = re.search(r'"room_subject"\s*:\s*"([^"]*)"', html)
            if ms:
                sub_raw = ms.group(1).strip()
                try:
                    subject = bytes(sub_raw, 'utf-8').decode('unicode_escape')
                except Exception:
                    subject = sub_raw
    except Exception:
        pass
    return viewers, subject

def main():
    # 1. InfinityFree Firewall
    bypass_infinityfree(ENDPOINT_URL)

    # 2. Load streamers from DB
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
    print(f"Total streamers in library: {len(saved_set)}")

    # 3. Fast Parallel Embed Status Check (20 workers)
    print("[2/3] Verifying online streamers with 20 parallel workers...")
    confirmed_live = []
    found_online = set()

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(check_live_status_embed, saved_set)
        for r in results:
            if r:
                confirmed_live.append(r)
                found_online.add(r['name'])

    print(f"Detected {len(confirmed_live)} streamers LIVE!")

    # 4. Global API Rooms Feed via Curl
    global_rooms = fetch_global_chaturbate_rooms()

    # 5. Enrich live streamers with Viewers & Subject
    status_payload = []
    for item in confirmed_live:
        name = item['name']
        if name in global_rooms and global_rooms[name]['viewers'] > 0:
            item['viewers'] = global_rooms[name]['viewers']
            item['subject'] = global_rooms[name]['subject']
            show = global_rooms[name]['show']
            if show in ['private', 'ticket_show']:
                item['status'] = 'private'
            elif show in ['away', 'hidden', 'group_show', 'club_show']:
                item['status'] = 'others'
        else:
            # Fallback direct curl
            v, s = fetch_single_room_via_curl(name)
            if v > 0:
                item['viewers'] = v
            if s:
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

    # Summary Report in Actions Log
    print("\n--- FINAL LIVE STATUS REPORT ---")
    for item in status_payload:
        if item['status'] != 'offline':
            print(f"-> [{item['name'].upper()}] Status: {item['status']} | Viewers: {item['viewers']} | Subject: '{item['subject']}'")
    print(f"Summary: {len(confirmed_live)} LIVE, {len(saved_set) - len(confirmed_live)} OFFLINE.\n")

    # 7. Push to Database
    print("[3/3] Syncing live data to database...")
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
