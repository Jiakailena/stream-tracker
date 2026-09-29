import os
import sys
import re
import html as html_lib

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests")
    import requests

TARGET = "mia_rom"

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://chaturbate.com/'
})

def clean_subject(raw: str) -> str:
    if not raw:
        return ""
    try:
        raw = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), raw)
    except Exception:
        pass
    raw = html_lib.unescape(raw)
    raw = raw.replace('\\"', '"').replace('\\/', '/')
    return re.sub(r'\s+', ' ', raw).strip()

print("=" * 65)
print(f"🔍 TESTING ACCURATE TELEMETRY FOR: {TARGET}")
print("=" * 65)

url = f"https://chaturbate.com/embed/{TARGET}/?bgcolor=black"

try:
    res = session.get(url, timeout=12)
    print(f"[HTTP STATUS]: {res.status_code}")

    if res.status_code == 200:
        html_text = res.text

        # 1. Status Check
        status_match = re.search(r'(?:\\u0022|\\"|")room_status(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")([a-zA-Z0-9_\-]+)(?:\\u0022|\\"|")', html_text)
        status = 'offline'

        if status_match:
            raw_s = status_match.group(1).lower()
            if raw_s in ['offline', 'disabled', 'away_offline']:
                status = 'offline'
            elif raw_s in ['private', 'ticket_show', 'vip', 'c2c']:
                status = 'private'
            elif raw_s in ['away', 'hidden', 'group_show', 'club_show']:
                status = 'others'
            else:
                status = 'public'
        elif '.m3u8' in html_text or '"is_live": true' in html_text:
            status = 'public'

        # 2. Viewers Check
        viewers = 0
        mv = re.search(r'(?:\\u0022|\\"|")num_viewers(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text) or \
             re.search(r'(?:\\u0022|\\"|")viewers(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text) or \
             re.search(r'(?:\\u0022|\\"|")num_users(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text)
        if mv:
            viewers = int(mv.group(1))

        # 3. Subject Check (JS variables + HTML <title> Fallback)
        subject = ''
        ms = re.search(r'(?:\\u0022|\\"|")room_subject(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")(.*?)(?:\\u0022|\\"|")(?=\s*[,}\]])', html_text, re.DOTALL) or \
             re.search(r'(?:\\u0022|\\"|")subject(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")(.*?)(?:\\u0022|\\"|")(?=\s*[,}\]])', html_text, re.DOTALL)
        if ms:
            subject = clean_subject(ms.group(1))

        # HTML Title Fallback (How tracker.py got the subject)
        if not subject:
            title_match = re.search(r'<title>(.*?)</title>', html_text, re.IGNORECASE | re.DOTALL)
            if title_match:
                t = title_match.group(1).strip()
                t = re.sub(r'\s*-\s*Chaturbate.*$', '', t, flags=re.IGNORECASE)
                subject = clean_subject(t)

        # 4. Token Parsing
        extracted_tokens = None
        if subject:
            m = re.search(r'\[[^\d\]]*(\d+)[^\]]*\]', subject) or re.search(r'(\d+)\s*(?:tokens?|tk|remaining|left)\b', subject, re.I)
            if m:
                extracted_tokens = m.group(1)

        print("\n📊 TELEMETRY RESULT:")
        print(f"⭐ Model    : {TARGET}")
        print(f"   ● Status : {status.upper()}")
        print(f"   ● Viewers: {viewers} viewers")
        print(f"   ● Subject: {subject if subject else '(No goal/subject set)'}")
        print(f"   ● Goal Tokens Remaining: {extracted_tokens if extracted_tokens else 'No active goal tokens'}")
    else:
        print(f"❌ Failed with status code: {res.status_code}")

except Exception as e:
    print(f"❌ Error: {e}")

print("=" * 65)
