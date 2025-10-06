from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import join_room, leave_room, send, SocketIO, emit
import random
from string import ascii_uppercase
import os
import uuid
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = "hjhjsdahhds"
socketio = SocketIO(app, cors_allowed_origins="*")

# File-based persistence instead of memory-only storage
ROOMS_FILE = "rooms_data.json"
rooms = {}

# uploads config
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", 
                     "mp3", "wav", "ogg", "m4a", "mp4", "avi", "mov", "webm",
                     "pdf", "doc", "docx", "txt", "ppt", "pptx", "xls", "xlsx", 
                     "zip", "rar", "7z", "tar", "gz"}

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def save_rooms():
    """Save rooms data to file"""
    try:
        with open(ROOMS_FILE, 'w') as f:
            json.dump(rooms, f, indent=2)
    except Exception as e:
        print(f"Error saving rooms: {e}")

def load_rooms():
    """Load rooms data from file"""
    global rooms
    try:
        if os.path.exists(ROOMS_FILE):
            with open(ROOMS_FILE, 'r') as f:
                rooms = json.load(f)
        else:
            rooms = {}
    except Exception as e:
        print(f"Error loading rooms: {e}")
        rooms = {}

# Load existing rooms on startup
load_rooms()

def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)
        
        if code not in rooms:
            break
    
    return code

@app.route("/", methods=["POST", "GET"])
def home():
    session.clear()
    if request.method == "POST":
        name = request.form.get("name")
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        if not name:
            return render_template("home.html", error="Please enter a name.", code=code, name=name)

        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name)
        
        room = code
        if create != False:
            room = generate_unique_code(4)
            rooms[room] = {"members": 0, "messages": []}
            save_rooms()  # Persist immediately
        elif code not in rooms:
            return render_template("home.html", error="Room does not exist.", code=code, name=name)
        
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room"))

    return render_template("home.html")

@app.route("/room")
def room():
    room = session.get("room")
    if room is None or session.get("name") is None or room not in rooms:
        return redirect(url_for("home"))

    return render_template("room.html", code=room, messages=rooms[room]["messages"])

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    save_path = os.path.join(UPLOAD_FOLDER, unique_name)
    
    try:
        file.save(save_path)
    except Exception as e:
        return jsonify({'error': f'Failed to save file: {str(e)}'}), 500

    file_url = url_for('static', filename=f'uploads/{unique_name}')

    # Get room and name info
    room = request.form.get('room') or session.get('room')
    name = request.form.get('name') or session.get('name')

    if not room or room not in rooms:
        return jsonify({'error': 'Invalid room'}), 400

    if not name:
        return jsonify({'error': 'Name required'}), 400

    # Determine file type
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'}:
        file_type = 'image'
    elif ext in {'mp3', 'wav', 'ogg', 'm4a'}:
        file_type = 'audio'
    elif ext in {'mp4', 'avi', 'mov', 'webm'}:
        file_type = 'video'
    else:
        file_type = 'document'

    # Create message content
    message_text = request.form.get('message', '')
    content = {
        'name': name,
        'file_url': file_url,
        'file_type': file_type,
        'message': message_text,
        'filename': filename,
        'timestamp': str(uuid.uuid4())  # Simple timestamp
    }

    # Save to persistent storage
    rooms[room]['messages'].append(content)
    save_rooms()

    # Broadcast to all connected clients in the room using SocketIO
    socketio.emit('message', content, room=room)

    return jsonify({'success': True, 'file_url': file_url, 'message': 'File uploaded successfully'})

@socketio.on("message")
def message(data):
    room = session.get("room")
    if room not in rooms:
        return

    content = {
        "name": session.get("name"),
        "message": data["data"],
        "timestamp": str(uuid.uuid4())
    }

    # Save to persistent storage
    rooms[room]["messages"].append(content)
    save_rooms()

    # Broadcast to room
    send(content, to=room)
    print(f"{session.get('name')} said: {data['data']}")

@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return

    join_room(room)
    send({"name": name, "message": "has entered the room"}, to=room)
    rooms[room]["members"] += 1
    save_rooms()
    print(f"{name} joined room {room}")

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)
    
    if room in rooms:
        rooms[room]["members"] -= 1
        save_rooms()
        
        # Only delete room if no members, but keep message history
        if rooms[room]["members"] <= 0:
            # Don't delete, just reset members to 0
            rooms[room]["members"] = 0
            save_rooms()
            
        send({"name": name, "message": "has left the room"}, to=room)
        print(f"{name} has left the room {room}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Use Render's assigned port
    socketio.run(app, debug=True, host='0.0.0.0', port=port)

# if __name__ == "__main__":
    # socketio.run(app, debug=True, host='0.0.0.0', port=5000)
