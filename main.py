import json
import os
import random
from string import ascii_uppercase
from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, SocketIO, emit

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
    return {"admin": None, "members": 0, "messages": [], "button_activated": False}


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
        title = request.form.get("title")  # Capture the meeting title
        mode = request.form.get("mode")  # Capture the game mode
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        if not name:
            return render_template("home.html", error="Please enter a name.", code=code, name=name)

        if join and not code:
            return render_template("home.html", error="Please enter the room code.", code=code, name=name)

        room = code  # Default room code for join
        if create:
            room = generate_unique_code()
            # Save the meeting title and mode in the room data
            room_data = {
                "admin": name,
                "members": 0,
                "messages": [],
                "meeting_title": title or "Untitled Meeting",  # Default if no title provided
                "mode": mode,
                "button_activated": False  # Initialize button state
            }
            save_room_data(room, room_data)
            print(f"[INFO] Room {room} created with admin {name}, title '{title}', and mode '{mode}'")
        elif not os.path.exists(os.path.join(ROOMS_DIR, f"{room}.json")):
            print(f"[ERROR] Room {room} does not exist.")
            return render_template("home.html", error="Room does not exist.", code=code, name=name)

        session["room"] = room
        session["name"] = name

        # Pass the room code when redirecting
        return redirect(url_for("room"))
    return render_template("home.html")


@app.route("/room")
def room():
    room = session.get("room")
    name = session.get("name")

    if not room or not name:
        return redirect(url_for("home"))

    # Load room data, including the meeting title
    room_data = load_room_data(room)
    meeting_title = room_data.get("meeting_title", "Untitled Meeting")  # Default if missing

    return render_template(
        "room.html",
        room=room,
        messages=room_data["messages"],
        name=name,
        meeting_title=meeting_title,
        is_admin=(name == room_data["admin"]),
        button_activated=room_data.get("button_activated", False)  # Pass button state
    )


@socketio.on("connect")
def connect():
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return
    
    room_data = load_room_data(room)  # Load room data
    join_room(room)
    send({"name": name, "message": "has entered the room"}, to=room)
    
    room_data["members"] += 1  # Increment member count
    save_room_data(room, room_data)  # Save updated data

    admin_name = room_data["admin"]  # Get the admin name
    send({"name": "System", "message": f"The admin of this room is {admin_name}."}, to=room)  # Notify users about admin
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
        save_room_data(room, room_data)  # Save updated data
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


@socketio.on("activate_button")
def activate_button(data):
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return

    # Load room data
    room_data = load_room_data(room)

    # Only the admin can activate the button
    if name == room_data["admin"]:
        room_data["button_activated"] = True
        save_room_data(room, room_data)

        # Notify everyone in the room that the button is activated
        socketio.emit("button_activated", {"room": room}, to=room)
        print(f"[INFO] Admin {name} activated the button in room {room}")


@app.route("/vote", methods=["POST", "GET"])
def vote():
    room = session.get("room")
    name = session.get("name")

    if not room or not name:
        return redirect(url_for("home"))

    room_data = load_room_data(room)
    admin = room_data["admin"]

    if request.method == "POST":
        # Admin sets the task title
        if name == admin:
            task_title = request.form.get("task_title")
            room_data["current_task"] = {"title": task_title, "votes": []}
            save_room_data(room, room_data)

    task = room_data.get("current_task", {"title": "No task set", "votes": []})
    return render_template(
        "vote.html",
        room=room,
        name=name,
        task=task,
        is_admin=(name == admin)
    )

@socketio.on("submit_vote")
def submit_vote(data):
    room = session.get("room")
    name = session.get("name")
    vote = data.get("vote")

    room_data = load_room_data(room)

    # Vérifier si l'utilisateur a déjà voté
    if "current_task" in room_data:
        current_task = room_data["current_task"]

        if any(v["name"] == name for v in current_task["votes"]):
            socketio.emit("vote_error", {"message": "Vous avez déjà voté."}, to=request.sid)
            return

        # Ajouter le vote
        current_task["votes"].append({"name": name, "vote": vote})
        save_room_data(room, room_data)

        # Diffuser le vote pour désactiver les boutons de l'utilisateur actuel
        socketio.emit("vote_submitted", {"name": name, "vote": vote}, to=room)

@socketio.on("stop_vote")
def stop_vote(data=None):
    room = session.get("room")
    name = session.get("name")

    room_data = load_room_data(room)
    votes = room_data.get("current_task", {}).get("votes", [])

    if name == room_data["admin"]:
        if not votes:
            socketio.emit("vote_error", {"message": "Aucun vote n'a été soumis."}, to=request.sid)
            return

        # Vérifier si tous les joueurs ont voté la même chose
        unique_votes = set(v["vote"] for v in votes)
        if len(unique_votes) == 1:  # Tous les votes sont identiques
            unanimous_vote = unique_votes.pop()
            socketio.emit(
                "voting_results",
                {
                    "unanimous": True,
                    "vote": unanimous_vote
                },
                to=room
            )
        else:
            # Calculer les votes les plus bas et les plus élevés
            sorted_votes = sorted(votes, key=lambda x: x["vote"])
            lowest = sorted_votes[0]
            highest = sorted_votes[-1]

            socketio.emit(
                "voting_results",
                {
                    "unanimous": False,
                    "lowest": {"name": lowest["name"], "vote": lowest["vote"]},
                    "highest": {"name": highest["name"], "vote": highest["vote"]}
                },
                to=room
            )


@socketio.on("reset_vote")
def reset_vote(data=None):  # Ajoutez un argument pour éviter l'erreur
    room = session.get("room")
    name = session.get("name")

    room_data = load_room_data(room)

    # Vérifier si l'utilisateur est l'admin
    if name != room_data["admin"]:
        socketio.emit("vote_error", {"message": "Seul l'admin peut recommencer le vote."}, to=request.sid)
        return

    # Réinitialiser les votes et cacher les résultats
    if "current_task" in room_data:
        room_data["current_task"]["votes"] = []  # Effacer tous les votes
        save_room_data(room, room_data)

        # Diffuser la réinitialisation à tous les utilisateurs
        socketio.emit("vote_reset", {}, to=room)
        print(f"[INFO] L'admin {name} a réinitialisé le vote dans la room {room}.")

@socketio.on("new_task")
def new_task(data):
    room = session.get("room")
    name = session.get("name")

    room_data = load_room_data(room)

    if name != room_data["admin"]:
        socketio.emit("vote_error", {"message": "Seul l'admin peut créer une nouvelle tâche."}, to=request.sid)
        return

    # Définir une nouvelle tâche avec le titre fourni
    task_title = data.get("title", "Nouvelle tâche")
    room_data["current_task"] = {"title": task_title, "votes": []}
    save_room_data(room, room_data)

    # Informer tous les joueurs de la nouvelle tâche
    socketio.emit("task_updated", {"title": task_title}, to=room)
    print(f"[INFO] Nouvelle tâche définie par l'admin {name} : {task_title}")


if __name__ == "__main__":
    socketio.run(app, debug=True)