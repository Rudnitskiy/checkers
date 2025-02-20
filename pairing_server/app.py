from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_cors import CORS
import uuid
from threading import Lock

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Change in production
CORS(app, supports_credentials=True)  # Allow cross-origin calls from game_server

# Global in‑memory storage (for demo only)
registered_users = set()      # list of registered names
waiting_queue = []            # names waiting for an opponent
pairings = {}                 # mapping: username -> game_id
queue_lock = Lock()

@app.route("/", methods=["GET"])
def index():
    if "username" in session:
        return render_template("lobby.html", username=session["username"])
    else:
        return render_template("register.html")

@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username").strip()
    if username in registered_users:
        return render_template("register.html", error="Name taken, choose another")
    session["username"] = username
    registered_users.add(username)
    return redirect(url_for("index"))

@app.route("/queue", methods=["POST"])
def queue():
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not registered"})
    with queue_lock:
        # If already paired, return pairing info
        if username in pairings:
            return jsonify({"status": "paired", "game_id": pairings[username]})
        # If not already waiting, add to waiting_queue
        if username not in waiting_queue:
            waiting_queue.append(username)
        # If at least two are waiting, pair them
        if len(waiting_queue) >= 2:
            if waiting_queue[0] == username:
                opponent = waiting_queue[1]
                waiting_queue.remove(username)
                waiting_queue.remove(opponent)
            else:
                opponent = waiting_queue.pop(0)
                waiting_queue.remove(username)
            # Generate a unique game id
            game_id = str(uuid.uuid4())
            pairings[username] = game_id
            pairings[opponent] = game_id
            return jsonify({"status": "paired", "game_id": game_id})
    return jsonify({"status": "waiting"})

@app.route("/status", methods=["GET"])
def status():
    username = session.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Not registered"})
    with queue_lock:
        if username in pairings:
            return jsonify({"status": "paired", "game_id": pairings[username]})
    return jsonify({"status": "waiting"})

# New endpoint to clear a user's pairing (e.g., after a game is finished)
@app.route("/reset", methods=["POST"])
def reset():
    username = session.get("username")
    if username in pairings:
        del pairings[username]
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
