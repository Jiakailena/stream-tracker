#!/usr/bin/env python3
"""
Live Lounge - Stream Tracker (tracker.py)
------------------------------------------
- 20-Worker concurrent embed scraper (https://chaturbate.com/embed/{username}/?bgcolor=black)
- Extracts `num_viewers`, `room_status`, and `room_subject` directly from embed JS
- Subdomain-aware InfinityFree AES cookie firewall bypass
- Syncs tracked state & continuous session metadata back to stream.php
"""

import os
import re
import sys
import time
import json
import html
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Optional crypto libraries for InfinityFree AES cookie challenge
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_BACKEND = 'cryptography'
except ImportError:
    try:
        from Crypto.Cipher import AES
        CRYPTO_BACKEND = 'pycryptodome'
    except ImportError:
        CRYPTO_BACKEND = None

# ==========================================
# CONFIGURATION
# ==========================================
STREAM_URL = os.getenv("STREAM_URL", "https://stacy.infinityfreeapp.com/stream.php")
TRACKER_SECRET = os.getenv("TRACKER_SECRET", "")
MAX_WORKERS = 20
REQUEST_TIMEOUT = 8

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ==========================================
# INFINITYFREE AES FIREWALL BYPASS SESSION
# ==========================================
class InfinityFreeSession(requests.Session):
    """
    Automated requests.Session that intercepts InfinityFree's slowAES __test cookie
    firewall and computes the AES-CBC response to authenticate headless calls.
    """
    def __init__(self):
        super().__init__()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=MAX_WORKERS + 5, pool_maxsize=MAX_WORKERS + 5)
        self.mount("https://", adapter)
        self.mount("http://", adapter)
        self.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _solve_aes(self, a_hex: str, b_hex: str, c_hex: str) -> str:
        key = bytes.fromhex(a_hex)
        iv = bytes.fromhex(b_hex)
        ciphertext = bytes.fromhex(c_hex)

        if CRYPTO_BACKEND == 'cryptography':
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            return plaintext.hex()
        elif CRYPTO_BACKEND == 'pycryptodome':
            cipher = AES.new(key, AES.MODE_CBC, iv)
            plaintext = cipher.decrypt(ciphertext)
            return plaintext.hex()
        else:
            raise RuntimeError(
                "Neither 'cryptography' nor 'pycryptodome' is installed. "
                "Install via 'pip install cryptography' to bypass InfinityFree AES."
            )

    def request(self, method, url, *args, **kwargs):
        # Allow up to 3 challenge-response iterations
        for attempt in range(3):
            resp = super().request(method, url, *args, **kwargs)

            # Check if InfinityFree served the JavaScript test challenge page
            if resp.status_code == 200 and ("slowAES.decrypt" in resp.text or "toNumbers" in resp.text):
                print(f"[INFO] InfinityFree AES challenge detected (pass {attempt + 1}). Solving __test cookie...")
                a_match = re.search(r'a=toNumbers\("([a-f0-9]+)"\)', resp.text)
                b_match = re.search(r'b=toNumbers\("([a-f0-9]+)"\)', resp.text)
                c_match = re.search(r'c=toNumbers\("([a-f0-9]+)"\)', resp.text)

                if a_match and b_match and c_match:
                    cookie_val = self._solve_aes(a_match.group(1), b_match.group(1), c_match.group(1))
                    parsed = urllib.parse.urlparse(url)
                    host = parsed.hostname or "stacy.infinityfreeapp.com"

                    # 1. Bind to exact subdomain
                    self.cookies.set("__test", cookie_val, domain=host, path="/")
                    # 2. Bind with leading dot for subdomain matching
                    self.cookies.set("__test", cookie_val, domain=f".{host}", path="/")
                    # 3. Bind to root domain
                    parts = host.split(".")
                    if len(parts) >= 2:
                        root_domain = "." + ".".join(parts[-2:])
                        self.cookies.set("__test", cookie_val, domain=root_domain, path="/")
                    # 4. Inject directly into headers to guarantee transmission
                    self.headers["Cookie"] = f"__test={cookie_val}"

                    print(f"[OK] Solved __test cookie: {cookie_val[:12]}... (applied to {host})")
                    continue
                else:
                    print("[WARN] Could not parse slowAES parameters from challenge page.")
                    return resp

            return resp

        return resp


# ==========================================
# STRING & REGEX EXTRACTION HELPERS
# ==========================================
def clean_subject_string(raw: str) -> str:
    """Decodes unicode escapes (\\u0020, \\u2665) and HTML entities cleanly."""
    if not raw:
        return ""
    try:
        decoded = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), raw)
    except Exception:
        decoded = raw

    decoded = html.unescape(decoded)
    decoded = decoded.replace(r'\"', '"').replace(r'\/', '/')
    return re.sub(r'\s+', ' ', decoded).strip()


def parse_embed_html(username: str, html_text: str) -> dict:
    """
    Parses the embed page HTML directly for room_status, num_viewers, and room_subject.
    Handles raw quotes, escaped quotes, and JS unicode escapes.
    """
    result = {
        "username": username,
        "is_live": False,
        "status": "offline",
        "num_viewers": 0,
        "viewers": 0,
        "subject": "",
        "room_subject": ""
    }

    if not html_text:
        return result

    # 1. Room Status
    status_patterns = [
        r'(?:\\u0022|\\"|")room_status(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")([a-zA-Z0-9_\-]+)(?:\\u0022|\\"|")',
        r'(?:\\u0022|\\"|")status(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")([a-zA-Z0-9_\-]+)(?:\\u0022|\\"|")',
        r'initialRoomStatus\s*=\s*(?:\\u0022|\\"|")([a-zA-Z0-9_\-]+)(?:\\u0022|\\"|")',
    ]
    raw_status = None
    for pattern in status_patterns:
        m = re.search(pattern, html_text)
        if m:
            raw_status = m.group(1).lower().strip()
            break

    # 2. Real-Time Viewer Count
    viewer_patterns = [
        r'(?:\\u0022|\\"|")num_viewers(?:\\u0022|\\"|")\s*:\s*(\d+)',
        r'(?:\\u0022|\\"|")viewers(?:\\u0022|\\"|")\s*:\s*(\d+)',
        r'(?:\\u0022|\\"|")num_users(?:\\u0022|\\"|")\s*:\s*(\d+)',
    ]
    viewers = 0
    for pattern in viewer_patterns:
        m = re.search(pattern, html_text)
        if m:
            viewers = int(m.group(1))
            break

    # 3. Room Subject / Goal
    subject_patterns = [
        r'\\u0022(?:room_subject|subject|room_title|topic)\\u0022\s*:\s*\\u0022(.*?)\\u0022(?=\s*[,}\]])',
        r'\\"(?:room_subject|subject|room_title|topic)\\"\s*:\s*\\"(.*?)\\"(?=\s*[,}\]])',
        r'"(?:room_subject|subject|room_title|topic)"\s*:\s*"(.*?)"(?=\s*[,}\]])',
    ]
    extracted_subject = ""
    for pattern in subject_patterns:
        m = re.search(pattern, html_text, re.DOTALL)
        if m:
            extracted_subject = clean_subject_string(m.group(1))
            break

    # Fallback to <title> if JS subject is missing
    if not extracted_subject:
        title_match = re.search(r'<title>(.*?)</title>', html_text, re.IGNORECASE | re.DOTALL)
        if title_match:
            t = title_match.group(1).strip()
            t = re.sub(r'\s*-\s*Chaturbate.*$', '', t, flags=re.IGNORECASE)
            if t and t.lower() != username.lower():
                extracted_subject = clean_subject_string(t)

    # 4. Map Normalized Status Hierarchy
    if raw_status:
        if raw_status == "public":
            result["status"] = "public"
            result["is_live"] = True
        elif raw_status in ("private", "vip", "c2c"):
            result["status"] = "private"
            result["is_live"] = True
        elif raw_status in ("offline", "away_offline"):
            result["status"] = "offline"
            result["is_live"] = False
        else:
            result["status"] = "others"
            result["is_live"] = True
    else:
        if "room is offline" in html_text.lower() or "room_is_offline" in html_text.lower():
            result["status"] = "offline"
            result["is_live"] = False
        elif viewers > 0:
            result["status"] = "public"
            result["is_live"] = True

    if result["is_live"]:
        result["num_viewers"] = viewers
        result["viewers"] = viewers
        result["subject"] = extracted_subject
        result["room_subject"] = extracted_subject
    else:
        result["num_viewers"] = 0
        result["viewers"] = 0
        result["subject"] = ""
        result["room_subject"] = ""

    return result


# ==========================================
# SCRAPING ENGINE (20 WORKERS)
# ==========================================
def check_streamer_embed(session: requests.Session, username: str) -> dict:
    """Queries the embed page and returns parsed status."""
    url = f"https://chaturbate.com/embed/{username}/?bgcolor=black"
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return parse_embed_html(username, resp.text)
        return {
            "username": username,
            "is_live": False,
            "status": "offline",
            "num_viewers": 0,
            "viewers": 0,
            "subject": "",
            "room_subject": ""
        }
    except Exception as e:
        return {
            "username": username,
            "is_live": False,
            "status": "offline",
            "num_viewers": 0,
            "viewers": 0,
            "subject": "",
            "room_subject": "",
            "error": str(e)
        }


def get_streamers_list(session: InfinityFreeSession) -> list:
    """Fetches tracked usernames from stream.php."""
    params = {"action": "get_streamers"}
    if TRACKER_SECRET:
        params["secret"] = TRACKER_SECRET

    print(f"[INFO] Fetching streamer list from {STREAM_URL}...")
    try:
        resp = session.get(STREAM_URL, params=params, timeout=12)
        if resp.status_code == 200:
            try:
                data = resp.json()
            except json.JSONDecodeError:
                print(f"[ERROR] Response is not JSON. Status: {resp.status_code}")
                print(f"[DEBUG] Raw response: {resp.text[:300]}")
                return []

            streamers = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        streamers.append(item.strip().lower())
                    elif isinstance(item, dict):
                        u = item.get("username") or item.get("name")
                        if u:
                            streamers.append(str(u).strip().lower())
            elif isinstance(data, dict):
                for key in ("streamers", "data", "results"):
                    if key in data and isinstance(data[key], list):
                        return [
                            (x.get("username") if isinstance(x, dict) else str(x)).strip().lower()
                            for x in data[key]
                        ]
            return sorted(list(set(streamers)))
    except Exception as e:
        print(f"[ERROR] Failed to fetch streamer list: {e}")

    return []


def sync_results_to_backend(session: InfinityFreeSession, results: list) -> dict:
    """Posts tracked updates back to stream.php to maintain continuous sessions."""
    payload = {
        "action": "sync_tracking",
        "timestamp": int(time.time()),
        "streamers": results,
        "data": results
    }
    if TRACKER_SECRET:
        payload["secret"] = TRACKER_SECRET

    print(f"[INFO] Syncing {len(results)} streamers back to database...")
    try:
        resp = session.post(STREAM_URL, json=payload, timeout=15)
        try:
            return resp.json()
        except Exception:
            return {"status_code": resp.status_code, "text": resp.text[:200]}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==========================================
# MAIN EXECUTION ROUTINE
# ==========================================
def main():
    start_time = time.time()
    print("=" * 65)
    print(" LIVE LOUNGE TRACKER - DIRECT EMBED PARSER")
    print("=" * 65)

    backend_session = InfinityFreeSession()
    streamers = get_streamers_list(backend_session)

    if not streamers:
        print("[WARN] No streamers returned from backend. Exiting.")
        sys.exit(0)

    print(f"[INFO] Loaded {len(streamers)} streamers. Starting 20-worker pool...")

    embed_session = requests.Session()
    embed_adapter = HTTPAdapter(
        pool_connections=MAX_WORKERS + 5,
        pool_maxsize=MAX_WORKERS + 5,
        max_retries=2
    )
    embed_session.mount("https://", embed_adapter)
    embed_session.headers.update({"User-Agent": USER_AGENT})

    results = []
    live_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_username = {
            executor.submit(check_streamer_embed, embed_session, user): user
            for user in streamers
        }

        for future in as_completed(future_to_username):
            data = future.result()
            results.append(data)
            if data.get("is_live"):
                live_count += 1
                subj = data.get("subject", "")
                preview = (subj[:45] + "...") if len(subj) > 45 else subj
                print(
                    f"  [LIVE] {data['username']:<18} | "
                    f"Status: {data['status']:<7} | "
                    f"Viewers: {data['num_viewers']:<5} | "
                    f"Goal: {preview}"
                )

    elapsed = round(time.time() - start_time, 2)
    print("-" * 65)
    print(f"[DONE] Scraped {len(results)} models in {elapsed}s. Detected {live_count} streamers LIVE!")

    sync_resp = sync_results_to_backend(backend_session, results)
    print(f"[SYNC] Server Response: {sync_resp}")
    print("=" * 65)


if __name__ == "__main__":
    main()
