"""SQLite game logging for AI decision analysis."""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import asdict

from game import Card, Player, Game, GameOptions


class GameLogger:
    """Logs game state and AI decisions to SQLite for post-game analysis."""

    def __init__(self, db_path: str = "games.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Games table
                CREATE TABLE IF NOT EXISTS games (
                    id TEXT PRIMARY KEY,
                    room_code TEXT,
                    started_at TIMESTAMP,
                    ended_at TIMESTAMP,
                    num_players INTEGER,
                    options_json TEXT
                );

                -- Moves table (one per AI decision)
                CREATE TABLE IF NOT EXISTS moves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT REFERENCES games(id),
                    move_number INTEGER,
                    timestamp TIMESTAMP,
                    player_id TEXT,
                    player_name TEXT,
                    is_cpu BOOLEAN,

                    -- Decision context
                    action TEXT,

                    -- Cards involved
                    card_rank TEXT,
                    card_suit TEXT,
                    position INTEGER,

                    -- Full state snapshot
                    hand_json TEXT,
                    discard_top_json TEXT,
                    visible_opponents_json TEXT,

                    -- AI reasoning
                    decision_reason TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_moves_game_id ON moves(game_id);
                CREATE INDEX IF NOT EXISTS idx_moves_action ON moves(action);
                CREATE INDEX IF NOT EXISTS idx_moves_is_cpu ON moves(is_cpu);
            """)

    def log_game_start(
        self, room_code: str, num_players: int, options: GameOptions
    ) -> str:
        """Log start of a new game. Returns game_id."""
        game_id = str(uuid.uuid4())
        options_dict = {
            "flip_on_discard": options.flip_on_discard,
            "initial_flips": options.initial_flips,
            "knock_penalty": options.knock_penalty,
            "use_jokers": options.use_jokers,
            "lucky_swing": options.lucky_swing,
            "super_kings": options.super_kings,
            "ten_penny": options.ten_penny,
            "knock_bonus": options.knock_bonus,
            "underdog_bonus": options.underdog_bonus,
            "tied_shame": options.tied_shame,
            "blackjack": options.blackjack,
            "eagle_eye": options.eagle_eye,
        }

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO games (id, room_code, started_at, num_players, options_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (game_id, room_code, datetime.now(), num_players, json.dumps(options_dict)),
            )
        return game_id

    def log_move(
        self,
        game_id: str,
        player: Player,
        is_cpu: bool,
        action: str,
        card: Optional[Card] = None,
        position: Optional[int] = None,
        game: Optional[Game] = None,
        decision_reason: Optional[str] = None,
    ):
        """Log a single move/decision."""
        # Get current move number
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COALESCE(MAX(move_number), 0) + 1 FROM moves WHERE game_id = ?",
                (game_id,),
            )
            move_number = cursor.fetchone()[0]

            # Serialize hand
            hand_data = []
            for c in player.cards:
                hand_data.append({
                    "rank": c.rank.value,
                    "suit": c.suit.value,
                    "face_up": c.face_up,
                })

            # Serialize discard top
            discard_top_data = None
            if game:
                discard_top = game.discard_top()
                if discard_top:
                    discard_top_data = {
                        "rank": discard_top.rank.value,
                        "suit": discard_top.suit.value,
                    }

            # Serialize visible opponent cards
            visible_opponents = {}
            if game:
                for p in game.players:
                    if p.id != player.id:
                        visible = []
                        for c in p.cards:
                            if c.face_up:
                                visible.append({
                                    "rank": c.rank.value,
                                    "suit": c.suit.value,
                                })
                        visible_opponents[p.name] = visible

            conn.execute(
                """
                INSERT INTO moves (
                    game_id, move_number, timestamp, player_id, player_name, is_cpu,
                    action, card_rank, card_suit, position,
                    hand_json, discard_top_json, visible_opponents_json, decision_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    move_number,
                    datetime.now(),
                    player.id,
                    player.name,
                    is_cpu,
                    action,
                    card.rank.value if card else None,
                    card.suit.value if card else None,
                    position,
                    json.dumps(hand_data),
                    json.dumps(discard_top_data) if discard_top_data else None,
                    json.dumps(visible_opponents),
                    decision_reason,
                ),
            )

    def log_game_end(self, game_id: str):
        """Mark game as ended."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE games SET ended_at = ? WHERE id = ?",
                (datetime.now(), game_id),
            )


# Query helpers for analysis

def find_suspicious_discards(db_path: str = "games.db") -> list[dict]:
    """Find cases where AI discarded good cards (Ace, 2, King)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT m.*, g.room_code
            FROM moves m
            JOIN games g ON m.game_id = g.id
            WHERE m.action = 'discard'
            AND m.card_rank IN ('A', '2', 'K')
            AND m.is_cpu = 1
            ORDER BY m.timestamp DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_player_decisions(db_path: str, game_id: str, player_name: str) -> list[dict]:
    """Get all decisions made by a specific player in a game."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT * FROM moves
            WHERE game_id = ? AND player_name = ?
            ORDER BY move_number
        """, (game_id, player_name))
        return [dict(row) for row in cursor.fetchall()]


def get_recent_games(db_path: str = "games.db", limit: int = 10) -> list[dict]:
    """Get list of recent games."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT g.*, COUNT(m.id) as total_moves
            FROM games g
            LEFT JOIN moves m ON g.id = m.game_id
            GROUP BY g.id
            ORDER BY g.started_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# Global logger instance (lazy initialization)
_logger: Optional[GameLogger] = None


def get_logger() -> GameLogger:
    """Get or create the global game logger instance."""
    global _logger
    if _logger is None:
        _logger = GameLogger()
    return _logger
