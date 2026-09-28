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
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8',
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
                    return {'name': username, 'status': 'private', 'viewers': 0, 'subject': '', 'raw_html': html}
                elif raw_status in ['away', 'hidden', 'group_show', 'club_show']:
                    return {'name': username, 'status': 'others', 'viewers': 0, 'subject': '', 'raw_html': html}
                else:
                    return {'name': username, 'status': 'public', 'viewers': 0, 'subject': '', 'raw_html': html}
            elif '.m3u8' in html or '"is_live": true' in html or '"is_live":true' in html:
                return {'name': username, 'status': 'public', 'viewers': 0, 'subject': '', 'raw_html': html}
    except Exception:
        pass
    return None

def get_runner_public_ip():
    """Detects actual GitHub Actions runner IPv4"""
    try:
        r = session.get('https://api.ipify.org', timeout=4)
        if r.status_code == 200 and re.match(r'^\d+\.\d+\.\d+\.\d+$', r.text.strip()):
            return r.text.strip()
    except Exception:
        pass
    return '104.28.19.45'

def parse_api_feed_data(raw_text):
    """Universal parser for both JSON and XML feeds"""
    rooms = {}
    # 1. Try JSON
    try:
        data = json.loads(raw_text)
        results = data.get('results', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for rm in results:
            if isinstance(rm, dict):
                u = str(rm.get('username', '')).lower()
                if u:
                    rooms[u] = {
                        'viewers': int(rm.get('num_users', 0) or 0),
                        'subject': str(rm.get('room_subject', '') or '').strip(),
                        'show': str(rm.get('current_show', 'public') or '').lower()
                    }
        if rooms:
            return rooms
    except Exception:
        pass

    # 2. Try XML
    try:
        blocks = re.findall(r'<room>(.*?)</room>', raw_text, re.DOTALL)
        for b in blocks:
            mu = re.search(r'<username>([^<]+)</username>', b)
            mv = re.search(r'<num_users>(\d+)</num_users>', b)
            ms = re.search(r'<room_subject>([^<]*)</room_subject>', b)
            msh = re.search(r'<current_show>([^<]*)</current_show>', b)
            if mu:
                u = mu.group(1).lower().strip()
                rooms[u] = {
                    'viewers': int(mv.group(1)) if mv else 0,
                    'subject': ms.group(1).strip() if ms else '',
                    'show': msh.group(1).lower().strip() if msh else 'public'
                }
    except Exception:
        pass

    return rooms

def fetch_chaturbate_global_feed():
    """Fetches global affiliate rooms with active WM candidates and format negotiation"""
    runner_ip = get_runner_public_ip()
    candidate_wms = ['9w8Zb', 'sCKdf', 'nMCKn', 'f6Ksc', 'Nxkvb']
    
    for wm in candidate_wms:
        urls_to_try = [
            f"https://chaturbate.com/api/public/affiliates/onlinerooms/?wm={wm}&client_ip={runner_ip}&format=json&limit=500",
            f"https://chaturbate.com/api/public/affiliates/onlinerooms/?wm={wm}&client_ip={runner_ip}&limit=500",
            f"https://chaturbate.com/affiliates/api/onlinerooms/?wm={wm}&format=json"
        ]

        for test_url in urls_to_try:
            try:
                r = session.get(test_url, timeout=12)
                preview = r.text[:120].replace('\n', ' ')
                print(f"[API CHECK] WM:{wm} -> HTTP {r.status_code} | Len: {len(r.text)} | Start: {preview}")
                
                if r.status_code == 200 and len(r.text) > 200:
                    parsed = parse_api_feed_data(r.text)
                    if parsed:
                        print(f"-> SUCCESS: Feed loaded {len(parsed)} active rooms worldwide!")
                        return parsed
            except Exception as e:
                print(f"[API ERROR] {e}")

    return {}

def extract_from_embed_html(html):
    """Extracts room stats from embed HTML"""
    viewers = 0
    subject = ''

    # Clean escaped quotes
    clean = html.replace('\\u0022', '"').replace('\\"', '"')

    # Viewers
    mv = re.search(r'["\']num_users["\']\s*:\s*(\d+)', clean) or re.search(r'["\']viewers["\']\s*:\s*(\d+)', clean)
    if mv:
        viewers = int(mv.group(1))

    # Subject / Topic
    ms = re.search(r'["\']room_subject["\']\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean)
    if ms:
        try:
            subject = bytes(ms.group(1).strip(), 'utf-8').decode('unicode_escape')
        except Exception:
            subject = ms.group(1).strip()

    return viewers, subject

def fetch_direct_room_page(username):
    """Direct fetch with mobile user agent"""
    url = f"https://chaturbate.com/{username}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': f'https://chaturbate.com/embed/{username}/?bgcolor=black'
    }
    cookies = {'ag_consent': '1', 'warning_accepted': '1', 'age_verified': '1'}
    try:
        r = session.get(url, headers=headers, cookies=cookies, timeout=6)
        if r.status_code == 200:
            clean = r.text.replace('\\u0022', '"').replace('\\"', '"')
            mv = re.search(r'"num_users"\s*:\s*(\d+)', clean) or re.search(r'data-viewers="(\d+)"', clean)
            ms = re.search(r'"room_subject"\s*:\s*"([^"\\]*)"', clean)
            v = int(mv.group(1)) if mv else 0
            s = ms.group(1).strip() if ms else ''
            return v, s
    except Exception:
        pass
    return 0, ''

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

    # Diagnostic Snippet for the first live streamer
    if confirmed_live:
        first_live = confirmed_live[0]
        html_str = first_live.get('raw_html', '')
        idx = html_str.find('room_status')
        if idx != -1:
            snippet = html_str[max(0, idx-60):min(len(html_str), idx+180)].replace('\n', ' ')
            print(f"[EMBED SNIPPET for {first_live['name'].upper()}]: ...{snippet}...")

    # 4. Multi-Strategy Detail Fetching
    print("[2/2] Fetching peak viewers and room subjects...")
    api_rooms = fetch_chaturbate_global_feed()

    for item in confirmed_live:
        name = item['name']
        # Try Strategy 1: Global Feed
        if name in api_rooms:
            item['viewers'] = api_rooms[name]['viewers']
            item['subject'] = api_rooms[name]['subject']
            show = api_rooms[name]['show']
            if show in ['private', 'ticket_show']:
                item['status'] = 'private'
            elif show in ['away', 'hidden', 'group_show', 'club_show']:
                item['status'] = 'others'
        else:
            # Try Strategy 2: Embed HTML
            v, s = extract_from_embed_html(item.get('raw_html', ''))
            if v > 0: item['viewers'] = v
            if s: item['subject'] = s

            # Try Strategy 3: Direct Fetch
            if item['viewers'] == 0 and not item['subject']:
                dv, ds = fetch_direct_room_page(name)
                if dv > 0: item['viewers'] = dv
                if ds: item['subject'] = ds

        # Clean temp raw_html before sending to DB
        item.pop('raw_html', None)

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
