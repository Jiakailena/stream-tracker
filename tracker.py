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
    'Accept': 'application/json, text/plain, */*',
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
                print("InfinityFree firewall bypassed successfully!")
                return True
        return True
    except Exception as e:
        print(f"Bypass error: {e}")
        return False

def check_live_status_embed(username):
    """Fast, reliable 20-worker live status detector via embed"""
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

def fetch_single_room_context(username):
    """Direct Chaturbate internal JSON endpoint with embed referer"""
    url = f"https://chaturbate.com/api/chatvideocontext/{username}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': f'https://chaturbate.com/embed/{username}/?bgcolor=black',
        'X-Requested-With': 'XMLHttpRequest'
    }
    try:
        r = session.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                viewers = int(data.get('num_users', 0) or 0)
                subject = str(data.get('room_subject', '') or '').strip()
                raw_show = str(data.get('room_status', 'public') or '').lower()
                status = 'public'
                if raw_show in ['private', 'ticket_show', 'vip']:
                    status = 'private'
                elif raw_show in ['away', 'hidden', 'group_show', 'club_show']:
                    status = 'others'
                return {'viewers': viewers, 'subject': subject, 'status': status}
    except Exception:
        pass
    return None

def fetch_api_details_for_targets(target_names):
    """Auto-discovers an active working WM code and matches live targets"""
    matched = {}
    remaining = set(target_names)
    if not remaining:
        return matched

    # List of verified candidate WM codes
    candidate_wms = ['sCKdf', 'nMCKn', 'f6Ksc', 'Nxkvb', 'Wb5m', 'eSRaG', 'k7YmQ', 'bT8b', '9w8Zb']
    working_wm = None

    print(f"Auto-discovering active WM code for {len(remaining)} live targets...")
    for wm in candidate_wms:
        test_url = f"https://chaturbate.com/api/public/affiliates/onlinerooms/?wm={wm}&client_ip=request_ip&format=json&limit=100"
        try:
            r = session.get(test_url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                results = data.get('results', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                if len(results) > 0:
                    working_wm = wm
                    print(f"-> SUCCESS: Active WM code found [{working_wm}]! Loaded {len(results)} rooms on page 1.")
                    # Process page 1 immediately
                    for rm in results:
                        if isinstance(rm, dict):
                            u = str(rm.get('username', '')).lower()
                            if u in remaining:
                                matched[u] = {
                                    'viewers': int(rm.get('num_users', 0) or 0),
                                    'subject': str(rm.get('room_subject', '') or '').strip(),
                                    'show': str(rm.get('current_show', 'public') or '').lower()
                                }
                                remaining.remove(u)
                    break
        except Exception:
            pass

    if not working_wm:
        print("No bulk WM code available, falling back to direct context inspection.")
        return matched

    # Paginate using the working WM code
    if remaining:
        url = f"https://chaturbate.com/api/public/affiliates/onlinerooms/?wm={working_wm}&client_ip=request_ip&format=json&limit=500"
        for page in range(2, 18):
            try:
                r = session.get(url, timeout=12)
                if r.status_code != 200:
                    break

                data = r.json()
                results = data.get('results', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                if not results:
                    break

                for rm in results:
                    if isinstance(rm, dict):
                        u = str(rm.get('username', '')).lower()
                        if u in remaining:
                            matched[u] = {
                                'viewers': int(rm.get('num_users', 0) or 0),
                                'subject': str(rm.get('room_subject', '') or '').strip(),
                                'show': str(rm.get('current_show', 'public') or '').lower()
                            }
                            remaining.remove(u)

                print(f"Page {page}: scanned {len(results)} rooms. Matched {len(matched)}/{len(target_names)} targets.")

                if not remaining:
                    print("All live targets matched via global API!")
                    break

                url = data.get('next') if isinstance(data, dict) else None
                if not url:
                    break

                time.sleep(0.1)
            except Exception as e:
                print(f"Feed error: {e}")
                break

    return matched

def main():
    # 1. InfinityFree Firewall Bypass
    bypass_infinityfree(ENDPOINT_URL)

    # 2. Load streamers from database
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

    # 3. High-Speed 20-Workers Concurrency Live Verification
    print("[1/2] Verifying live status with 20 parallel workers...")
    confirmed_live = []
    found_online = set()

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(check_live_status_embed, saved_set)
        for r in results:
            if r:
                confirmed_live.append(r)
                found_online.add(r['name'])

    print(f"Detected {len(confirmed_live)} streamers LIVE!")

    # 4. Enrich live streamers: Active WM API + Direct Referer Context Fallback
    if confirmed_live:
        print("[2/2] Fetching peak viewers and room subjects...")
        targets = [item['name'] for item in confirmed_live]
        api_data = fetch_api_details_for_targets(targets)

        # Apply global API data
        for item in confirmed_live:
            name = item['name']
            if name in api_data:
                item['viewers'] = api_data[name]['viewers']
                item['subject'] = api_data[name]['subject']
                show = api_data[name]['show']
                if show in ['private', 'ticket_show']:
                    item['status'] = 'private'
                elif show in ['away', 'hidden', 'group_show', 'club_show']:
                    item['status'] = 'others'

        # Fallback for any targets still missing viewers or subject
        missing = [item['name'] for item in confirmed_live if item['viewers'] == 0 and not item['subject']]
        if missing:
            print(f"Fetching direct room context for {len(missing)} streamers...")
            with ThreadPoolExecutor(max_workers=10) as ctx_executor:
                direct_results = list(ctx_executor.map(fetch_single_room_context, missing))
                for name, res_ctx in zip(missing, direct_results):
                    if res_ctx:
                        for item in confirmed_live:
                            if item['name'] == name:
                                if res_ctx['viewers'] > 0:
                                    item['viewers'] = res_ctx['viewers']
                                if res_ctx['subject']:
                                    item['subject'] = res_ctx['subject']
                                if res_ctx['status'] != 'public':
                                    item['status'] = res_ctx['status']

    # 5. Handle Offline streamers
    status_payload = list(confirmed_live)
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

    # 6. Push to Database
    print("Syncing verified stats to database...")
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
