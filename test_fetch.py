import urllib.request
import json
import time
import re
import html as html_lib

# আপনার দেওয়া টার্গেট মডেল
TEST_MODELS = ["mia_rom"]

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

def check_direct_embed(username: str):
    """Fallback: Direct Embed Check from your tracker.py"""
    url = f"https://chaturbate.com/embed/{username}/?bgcolor=black"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html_text = resp.read().decode('utf-8', errors='ignore')

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

        viewers = 0
        mv = re.search(r'(?:\\u0022|\\"|")num_viewers(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text) or \
             re.search(r'(?:\\u0022|\\"|")viewers(?:\\u0022|\\"|")\s*:\s*(\d+)', html_text)
        if mv:
            viewers = int(mv.group(1))

        subject = ''
        ms = re.search(r'(?:\\u0022|\\"|")room_subject(?:\\u0022|\\"|")\s*:\s*(?:\\u0022|\\"|")(.*?)(?:\\u0022|\\"|")(?=\s*[,}\]])', html_text, re.DOTALL)
        if ms:
            subject = clean_subject(ms.group(1))

        return status, viewers, subject
    except Exception as e:
        return 'error', 0, str(e)

print("=" * 65)
print("🔍 TESTING TELEMETRY FOR: mia_rom")
print("=" * 65)

# 1. Official Live Dump Feed Test
dump_url = "https://chaturbate.com/affiliates/api/onlinerooms/?format=json"
print("⏳ Attempting to fetch Chaturbate global dump feed...")

dump_rooms = []
start_t = time.time()
try:
    req = urllib.request.Request(dump_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        if isinstance(data, list):
            dump_rooms = data
        elif isinstance(data, dict):
            dump_rooms = data.get('results') or data.get('rooms') or []
    print(f"✅ Global Feed Downloaded: {len(dump_rooms)} rooms in {round(time.time() - start_t, 2)}s")
except Exception as e:
    print(f"⚠️ Dump feed error: {e}")

# Check in Dump
found_in_dump = False
for r in dump_rooms:
    if r.get('username', '').lower() == 'mia_rom':
        found_in_dump = True
        print("\n[METHOD 1: GLOBAL FEED RESULT]")
        print(f"⭐ Model    : mia_rom")
        print(f"   ● Status : {r.get('current_show', 'public').upper()}")
        print(f"   ● Viewers: {r.get('num_users', 0)} viewers")
        print(f"   ● Subject: {r.get('room_subject', '').strip()}")
        break

if not found_in_dump:
    print("ℹ️ mia_rom not found in global dump (or dump empty).")

# 2. Direct Embed Test (Your tracker method)
print("\n[METHOD 2: DIRECT EMBED VERIFICATION]")
status, viewers, subject = check_direct_embed("mia_rom")
print(f"⭐ Model    : mia_rom")
print(f"   ● Status : {status.upper()}")
print(f"   ● Viewers: {viewers} viewers")
print(f"   ● Subject: {subject if subject else '(No subject set)'}")

# Token Extraction Test
if subject:
    clean_sub = clean_subject(subject)
    m = re.search(r'\[[^\d\]]*(\d+)[^\]]*\]', clean_sub) or re.search(r'(\d+)\s*(?:tokens?|tk)\b', clean_sub, re.I)
    extracted_tokens = m.group(1) if m else "None"
    print(f"   ● Parsed Goal Tokens: {extracted_tokens}")

print("=" * 65)
