import json
import os
import random
from string import ascii_uppercase
from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, SocketIO

app = Flask(__name__)
app.config["SECRET_KEY"] = "milina"
socketio = SocketIO(app)

# Directory for saving room data
ROOMS_DIR = os.path.join(os.path.dirname(__file__), "rooms")

# Ensure the directory exists
os.makedirs(ROOMS_DIR, exist_ok=True)

# Load a specific room's data
def load_room_data(room_code):
    file_path = os.path.join(ROOMS_DIR, f"{room_code}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON in {file_path}: {e}")
    else:
        print(f"[ERROR] Room file {file_path} does not exist.")
    return {"admin": None, "members": 0, "messages": []}

# Save a specific room's data
def save_room_data(room_code, data):
    file_path = os.path.join(ROOMS_DIR, f"{room_code}.json")
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"[INFO] Room data saved for {room_code}")
    except Exception as e:
        print(f"[ERROR] Failed to save room data for {room_code}: {e}")

# Generate a unique room code
def generate_unique_code(length=4):
    while True:
        code = "".join(random.choice(ascii_uppercase) for _ in range(length))
        if not os.path.exists(os.path.join(ROOMS_DIR, f"{code}.json")):
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

        if join and not code:
            return render_template("home.html", error="Please enter the room code.", code=code, name=name)

        room = code  # Default room code for join
        if create:
            room = generate_unique_code()
            room_data = {"admin": name, "members": 0, "messages": []}
            save_room_data(room, room_data)
            print(f"[INFO] Room {room} created with admin {name}")
        elif not os.path.exists(os.path.join(ROOMS_DIR, f"{room}.json")):
            print(f"[ERROR] Room {room} does not exist.")
            return render_template("home.html", error="Room does not exist.", code=code, name=name)

        session["room"] = room
        session["name"] = name
        return redirect(url_for("room"))

    return render_template("home.html")

@app.route("/room")
def room():
    room = session.get("room")
    name = session.get("name")

    if not room or not name or not os.path.exists(os.path.join(ROOMS_DIR, f"{room}.json")):
        print(f"[ERROR] Room {room} does not exist or is not valid.")
        return redirect(url_for("home"))

    room_data = load_room_data(room)
    return render_template("room.html", room=room, messages=room_data["messages"])

@socketio.on("connect")
def connect():
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return

    room_data = load_room_data(room)  # Charger les données de la room
    join_room(room)
    send({"name": name, "message": "has entered the room"}, to=room)
    
    room_data["members"] += 1  # Incrémenter le nombre de membres
    save_room_data(room, room_data)  # Sauvegarder les données mises à jour

    admin_name = room_data["admin"]  # Récupérer le nom de l'admin
    send({"name": "System", "message": f"The admin of this room is {admin_name}."}, to=room)  # Envoyer un message avec l'admin
    print(f"[INFO]{admin_name} is the admin of the room {room}")
    print(f"[INFO] {name} joined room {room}")
    

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    if room:
        room_data = load_room_data(room)
        room_data["members"] -= 1
        save_room_data(room, room_data)  # Don't delete the room data unless explicitly required.
        send({"name": name, "message": "has left the room"}, to=room)
        print(f"[INFO] {name} has left room {room}")

@socketio.on("message")
def handle_message(data):
    room = session.get("room")
    name = session.get("name")
    if room and name:
        message = data["data"]
        room_data = load_room_data(room)
        room_data["messages"].append({"name": name, "message": message})
        save_room_data(room, room_data)
        send({"name": name, "message": message}, to=room)
        print(f"[INFO] Message from {name} in {room}: {message}")

if __name__ == "__main__":
    socketio.run(app, debug=True)
