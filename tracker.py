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
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Upgrade-Insecure-Requests': '1'
}
session.headers.update(BROWSER_HEADERS)

COOKIES = {
    'ag_consent': '1',
    'warning_accepted': '1',
    'age_verified': '1',
    'has_accepted_terms': '1',
    'terms_accepted': '1'
}

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

def parse_room_html(html):
    """Accurately extracts viewers and subject from Chaturbate room HTML"""
    viewers = 0
    subject = ''
    
    clean_html = html.replace('\\u0022', '"').replace('\\"', '"')

    # 1. Extract Viewers (num_users)
    mv = re.search(r'"num_users"\s*:\s*(\d+)', clean_html)
    if not mv:
        mv = re.search(r'data-viewers="(\d+)"', clean_html)
    if not mv:
        mv = re.search(r'id="room_users"[^>]*>(\d+)<', clean_html)
    if mv:
        viewers = int(mv.group(1))

    # 2. Extract Room Subject / Goal
    ms = re.search(r'"room_subject"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', clean_html)
    if ms:
        sub_raw = ms.group(1).strip()
        try:
            subject = bytes(sub_raw, 'utf-8').decode('unicode_escape')
        except Exception:
            subject = sub_raw
    if not subject:
        m_meta = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', html)
        if m_meta:
            meta_val = m_meta.group(1).strip()
            if not meta_val.lower().startswith('free live') and 'chaturbate' not in meta_val.lower()[:25]:
                subject = meta_val

    # 3. Check for specific status
    status = None
    mst = re.search(r'"room_status"\s*:\s*"([a-zA-Z0-9_-]+)"', clean_html)
    if mst:
        st_val = mst.group(1).lower()
        if st_val in ['private', 'ticket_show', 'vip']:
            status = 'private'
        elif st_val in ['away', 'hidden', 'group_show', 'club_show']:
            status = 'others'
        elif st_val == 'public':
            status = 'public'

    return viewers, subject, status

def inspect_single_live_streamer(username):
    """Inspects live room page using Python requests with curl fallback"""
    url = f"https://chaturbate.com/{username}/"
    headers = dict(BROWSER_HEADERS)
    headers['Referer'] = f"https://chaturbate.com/embed/{username}/?bgcolor=black"

    viewers, subject, status = 0, '', None

    # Attempt 1: Python Requests
    try:
        r = session.get(url, headers=headers, cookies=COOKIES, timeout=8)
        if r.status_code == 200 and 'num_users' in r.text:
            viewers, subject, status = parse_room_html(r.text)
    except Exception:
        pass

    # Attempt 2: Native Curl Fallback (if requests was blocked by Cloudflare)
    if viewers == 0 and not subject:
        try:
            cmd = [
                'curl', '-sL', '--compressed',
                '-H', f"User-Agent: {BROWSER_HEADERS['User-Agent']}",
                '-H', "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                '-H', f"Referer: https://chaturbate.com/embed/{username}/?bgcolor=black",
                '-b', 'ag_consent=1; warning_accepted=1; age_verified=1; has_accepted_terms=1',
                url
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            if res.returncode == 0 and res.stdout:
                viewers, subject, status = parse_room_html(res.stdout)
        except Exception:
            pass

    return username, viewers, subject, status

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

    # 4. Direct Room Inspection for the Confirmed Live Streamers Only
    if confirmed_live:
        print(f"[2/2] Inspecting room details for {len(confirmed_live)} confirmed live streamers...")
        live_names = [item['name'] for item in confirmed_live]
        
        with ThreadPoolExecutor(max_workers=10) as inspector_executor:
            inspected_data = list(inspector_executor.map(inspect_single_live_streamer, live_names))

        for uname, v, s, st in inspected_data:
            for item in confirmed_live:
                if item['name'] == uname:
                    if v > 0:
                        item['viewers'] = v
                    if s:
                        item['subject'] = s
                    if st:
                        item['status'] = st

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
