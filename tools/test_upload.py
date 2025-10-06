import requests
import sys

if len(sys.argv) < 4:
    print("Usage: python test_upload.py <file_path> <room_code> <name>")
    sys.exit(1)

file_path = sys.argv[1]
room = sys.argv[2]
name = sys.argv[3]
url = "http://127.0.0.1:5000/upload"

with open(file_path, 'rb') as f:
    files = {'file': (file_path.split('\\')[-1], f)}
    data = {'room': room, 'name': name, 'message': 'upload test from script'}
    r = requests.post(url, files=files, data=data)
    print('status:', r.status_code)
    try:
        print('json:', r.json())
    except Exception:
        print('text:', r.text)
