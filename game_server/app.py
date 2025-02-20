from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Global storage of games and player info
games = {}             # mapping: game_id -> CheckersGame instance
players_in_game = {}   # mapping: socket session id -> {game_id, color, player}

# ---------------------------
# Checkers Game Logic Class
# ---------------------------
class CheckersGame:
    def __init__(self, player_white, player_black):
        self.player_white = player_white
        self.player_black = player_black
        self.current_turn = "white"
        self.board = self.initialize_board()
        self.winner = None

    def initialize_board(self):
        board = [[None for _ in range(8)] for _ in range(8)]
        for row in range(3):
            for col in range(8):
                if (row + col) % 2 == 1:
                    board[row][col] = {"color": "black", "king": False}
        for row in range(5, 8):
            for col in range(8):
                if (row + col) % 2 == 1:
                    board[row][col] = {"color": "white", "king": False}
        return board

    def get_board_state(self):
        return self.board

    def is_valid_move(self, from_row, from_col, to_row, to_col, player_color):
        board = self.board
        if not (0 <= from_row < 8 and 0 <= from_col < 8 and 0 <= to_row < 8 and 0 <= to_col < 8):
            return False, "Out of bounds"
        piece = board[from_row][from_col]
        if not piece:
            return False, "No piece at the source"
        if piece["color"] != player_color:
            return False, "Not your piece"
        if board[to_row][to_col] is not None:
            return False, "Destination not empty"
        dr = to_row - from_row
        dc = to_col - from_col
        if abs(dr) == 1 and abs(dc) == 1:
            if not piece["king"]:
                if player_color == "white" and dr != -1:
                    return False, "White pieces move upward"
                if player_color == "black" and dr != 1:
                    return False, "Black pieces move downward"
            if self.has_capture(player_color):
                return False, "Capture available – you must capture"
            return True, None
        elif abs(dr) == 2 and abs(dc) == 2:
            mid_row = (from_row + to_row) // 2
            mid_col = (from_col + to_col) // 2
            mid_piece = board[mid_row][mid_col]
            if not mid_piece or mid_piece["color"] == player_color:
                return False, "No opponent to capture"
            if not piece["king"]:
                if player_color == "white" and dr != -2:
                    return False, "White pieces capture upward"
                if player_color == "black" and dr != 2:
                    return False, "Black pieces capture downward"
            return True, None
        else:
            return False, "Invalid move distance"

    def has_capture(self, player_color):
        for row in range(8):
            for col in range(8):
                piece = self.board[row][col]
                if piece and piece["color"] == player_color:
                    if self.can_capture_from(row, col):
                        return True
        return False

    def can_capture_from(self, row, col):
        piece = self.board[row][col]
        directions = [(-1,-1), (-1,1), (1,-1), (1,1)]
        for dr, dc in directions:
            if not piece["king"]:
                if piece["color"] == "white" and dr > 0:
                    continue
                if piece["color"] == "black" and dr < 0:
                    continue
            mid_row = row + dr
            mid_col = col + dc
            end_row = row + 2*dr
            end_col = col + 2*dc
            if 0 <= mid_row < 8 and 0 <= mid_col < 8 and 0 <= end_row < 8 and 0 <= end_col < 8:
                mid_piece = self.board[mid_row][mid_col]
                if mid_piece and mid_piece["color"] != piece["color"] and self.board[end_row][end_col] is None:
                    return True
        return False

    def move(self, from_row, from_col, to_row, to_col, player_color):
        valid, msg = self.is_valid_move(from_row, from_col, to_row, to_col, player_color)
        if not valid:
            return False, msg
        piece = self.board[from_row][from_col]
        dr = to_row - from_row
        if abs(dr) == 2:
            mid_row = (from_row + to_row) // 2
            mid_col = (from_col + to_col) // 2
            self.board[mid_row][mid_col] = None
        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None
        if player_color == "white" and to_row == 0:
            piece["king"] = True
        if player_color == "black" and to_row == 7:
            piece["king"] = True
        if abs(dr) == 2 and self.can_capture_from(to_row, to_col):
            return True, "capture_again"
        self.current_turn = "white" if self.current_turn == "black" else "black"
        return True, None

    def resign(self, player_color):
        self.winner = "white" if player_color == "black" else "black"

    def check_winner(self):
        white_exists = any(piece for row in self.board for piece in row if piece and piece["color"]=="white")
        black_exists = any(piece for row in self.board for piece in row if piece and piece["color"]=="black")
        if not white_exists:
            self.winner = "black"
        elif not black_exists:
            self.winner = "white"
        return self.winner

# ---------------------------
# HTTP Routes
# ---------------------------
@app.route("/")
def index():
    # The game URL includes query parameters: game_id and player name
    game_id = request.args.get("game_id")
    player = request.args.get("player")
    if not game_id or not player:
        return "Missing game_id or player", 400
    # (Note: you might want to create the game session automatically here if needed)
    # For demo, if the game_id is new, we create a game using the two players.
    if game_id not in games:
        # Assume first join is white, second is black.
        games[game_id] = CheckersGame(player_white=player, player_black="")  # placeholder for black
    return render_template("game.html", game_id=game_id, player=player)

@app.route("/create_game", methods=["POST"])
def create_game():
    # (Optional API endpoint to pre-create a game session)
    data = request.get_json()
    player_white = data.get("player_white")
    player_black = data.get("player_black")
    game_id = data.get("game_id", str(uuid.uuid4()))
    game = CheckersGame(player_white, player_black)
    games[game_id] = game
    return {"game_id": game_id}, 200

# ---------------------------
# Socket.IO Events
# ---------------------------
@socketio.on("join")
def on_join(data):
    game_id = data.get("game_id")
    player = data.get("player")
    room = game_id
    join_room(room)
    # Create game if it doesn't exist.
    if game_id not in games:
        games[game_id] = CheckersGame(player_white=player, player_black="")
    game = games[game_id]
    # Register the player if not already registered.
    if request.sid not in players_in_game:
        # Assign as white if not set; otherwise, assign as black.
        if game.player_white == "":
            game.player_white = player
        elif game.player_black == "" and player != game.player_white:
            game.player_black = player
        # Determine color.
        color = "white" if player == game.player_white else "black"
        players_in_game[request.sid] = {"game_id": game_id, "color": color, "player": player}

    # For every player in the room, compute the opponent name.
    for sid, info in players_in_game.items():
        if info["game_id"] == game_id:
            if info["color"] == "white":
                opp = game.player_black if game.player_black != "" else "Waiting for opponent"
            else:
                opp = game.player_white if game.player_white != "" else "Waiting for opponent"
            socketio.emit("board_state", {
                "board": game.get_board_state(),
                "turn": game.current_turn,
                "your_color": info["color"],
                "opponent": opp
            }, room=sid)

@socketio.on("make_move")
def on_make_move(data):
    game_id = data.get("game_id")
    from_row = data.get("from_row")
    from_col = data.get("from_col")
    to_row = data.get("to_row")
    to_col = data.get("to_col")
    if request.sid not in players_in_game:
        emit("error", {"message": "Not joined in a game"})
        return
    player_info = players_in_game[request.sid]
    if player_info["game_id"] != game_id:
        emit("error", {"message": "Game mismatch"})
        return
    player_color = player_info["color"]
    game = games.get(game_id)
    if not game:
        emit("error", {"message": "Game not found"})
        return
    if game.winner is not None:
        emit("move_error", {"message": "Game is finished, no moves allowed."})
        return
    if game.current_turn != player_color:
        emit("error", {"message": "Not your turn"})
        return
    success, msg = game.move(from_row, from_col, to_row, to_col, player_color)
    if not success:
        emit("move_error", {"message": msg})
        return
    winner = game.check_winner()
    room = game_id
    board = game.get_board_state()
    for sid, info in players_in_game.items():
        if info["game_id"] == game_id:
            opp = game.player_black if info["color"]=="white" else game.player_white
            if not opp:
                opp = "Waiting for opponent"
            if winner:
                socketio.emit("game_over", {
                    "winner": winner,
                    "board": board,
                    "opponent": opp
                }, room=sid)
            else:
                socketio.emit("board_state", {
                    "board": board,
                    "turn": game.current_turn,
                    "your_color": info["color"],
                    "opponent": opp
                }, room=sid)

@socketio.on("resign")
def on_resign(data):
    game_id = data.get("game_id")
    if request.sid not in players_in_game:
        emit("error", {"message": "Not in game"})
        return
    player_info = players_in_game[request.sid]
    player_color = player_info["color"]
    game = games.get(game_id)
    if not game:
        emit("error", {"message": "Game not found"})
        return
    if game.winner is not None:
        emit("move_error", {"message": "Game already finished."})
        return
    game.resign(player_color)
    winner = game.winner
    room = game_id
    board = game.get_board_state()
    for sid, info in players_in_game.items():
        if info["game_id"] == game_id:
            opp = game.player_black if info["color"]=="white" else game.player_white
            if not opp:
                opp = "Waiting for opponent"
            socketio.emit("game_over", {
                "winner": winner,
                "board": board,
                "opponent": opp
            }, room=sid)

if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=5001)