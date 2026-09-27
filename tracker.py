import json
import urllib.request
import urllib.parse
import sys

ENDPOINT_URL = "https://stacy.infinityfreeapp.com/stream.php"
TRACKER_SECRET = "jitul_tracker_key_2026"

def fetch_chaturbate_live():
    url = "https://chaturbate.com/api/public/affiliates/onlinerooms/?wm=9w8Zb&format=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching Chaturbate: {e}")
        return []

def main():
    fetch_req = urllib.request.Request(
        ENDPOINT_URL,
        data=urllib.parse.urlencode({'action': 'load_all'}).encode('utf-8'),
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    try:
        with urllib.request.urlopen(fetch_req, timeout=15) as res:
            site_data = json.loads(res.read().decode('utf-8'))
            saved_streamers = [s['name'].lower() for s in site_data.get('streamers', [])]
    except Exception as e:
        print(f"Failed to load streamers: {e}")
        return

    if not saved_streamers:
        print("No saved streamers found.")
        return

    saved_set = set(saved_streamers)
    print(f"Checking {len(saved_set)} saved streamers...")

    live_rooms = fetch_chaturbate_live()
    print(f"Chaturbate total live rooms: {len(live_rooms)}")

    status_payload = []
    found_online = set()

    for room in live_rooms:
        u_name = room.get('username', '').lower()
        if u_name in saved_set:
            current_show = room.get('current_show', 'public').lower()
            viewers = room.get('num_users', 0)
            subject = room.get('room_subject', '')

            mapped_status = 'public'
            if current_show in ['private', 'ticket_show']:
                mapped_status = 'private'
            elif current_show in ['away', 'hidden', 'group_show', 'club_show'] or 'hidden' in current_show:
                mapped_status = 'others'

            status_payload.append({
                'name': u_name,
                'status': mapped_status,
                'viewers': viewers,
                'subject': subject
            })
            found_online.add(u_name)

    for offline_name in saved_set - found_online:
        status_payload.append({
            'name': offline_name,
            'status': 'offline',
            'viewers': 0,
            'subject': ''
        })

    post_data = urllib.parse.urlencode({
        'action': 'sync_tracker',
        'secret': TRACKER_SECRET,
        'payload': json.dumps(status_payload)
    }).encode('utf-8')

    sync_req = urllib.request.Request(ENDPOINT_URL, data=post_data, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(sync_req, timeout=20) as res:
            result = json.loads(res.read().decode('utf-8'))
            print("Sync Result:", result)
    except Exception as e:
        print(f"Sync error: {e}")

if __name__ == '__main__':
    main()
  
