"""
Room management for multiplayer Golf games.

This module handles room creation, player management, and WebSocket
communication for multiplayer game sessions.

A Room contains:
    - A unique 4-letter code for joining
    - A collection of RoomPlayers (human or CPU)
    - A Game instance with the actual game state
    - Settings for number of decks, rounds, etc.
"""

import asyncio
import random
import string
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket

from ai import assign_profile, assign_specific_profile, get_profile, release_profile, cleanup_room_profiles
from game import Game, Player


@dataclass
class RoomPlayer:
    """
    A player in a game room (lobby-level representation).

    This is separate from game.Player - RoomPlayer tracks room-level info
    like WebSocket connections and host status, while game.Player tracks
    in-game state like cards and scores.

    Attributes:
        id: Unique player identifier (connection_id for multi-tab support).
        name: Display name.
        websocket: WebSocket connection (None for CPU players).
        is_host: Whether this player controls game settings.
        is_cpu: Whether this is an AI-controlled player.
        auth_user_id: Authenticated user ID for stats/limits (None for guests).
    """

    id: str
    name: str
    websocket: Optional[WebSocket] = None
    is_host: bool = False
    is_cpu: bool = False
    auth_user_id: Optional[str] = None


@dataclass
class Room:
    """
    A game room/lobby that can host a multiplayer Golf game.

    Attributes:
        code: 4-letter room code for joining (e.g., "ABCD").
        players: Dict mapping player IDs to RoomPlayer objects.
        game: The Game instance containing actual game state.
        settings: Room settings (decks, rounds, etc.).
        game_log_id: SQLite log ID for analytics (if logging enabled).
        game_lock: asyncio.Lock for serializing game mutations to prevent race conditions.
    """

    code: str
    players: dict[str, RoomPlayer] = field(default_factory=dict)
    game: Game = field(default_factory=Game)
    settings: dict = field(default_factory=lambda: {"decks": 1, "rounds": 1})
    game_log_id: Optional[str] = None
    game_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def add_player(
        self,
        player_id: str,
        name: str,
        websocket: WebSocket,
        auth_user_id: Optional[str] = None,
    ) -> RoomPlayer:
        """
        Add a human player to the room.

        The first player to join becomes the host.

        Args:
            player_id: Unique identifier for the player (connection_id).
            name: Display name.
            websocket: The player's WebSocket connection.
            auth_user_id: Authenticated user ID for stats/limits (None for guests).

        Returns:
            The created RoomPlayer object.
        """
        is_host = len(self.players) == 0
        room_player = RoomPlayer(
            id=player_id,
            name=name,
            websocket=websocket,
            is_host=is_host,
            auth_user_id=auth_user_id,
        )
        self.players[player_id] = room_player

        game_player = Player(id=player_id, name=name)
        self.game.add_player(game_player)

        return room_player

    def add_cpu_player(
        self,
        cpu_id: str,
        profile_name: Optional[str] = None,
    ) -> Optional[RoomPlayer]:
        """
        Add a CPU player to the room.

        Args:
            cpu_id: Unique identifier for the CPU player.
            profile_name: Specific AI profile to use, or None for random.

        Returns:
            The created RoomPlayer, or None if profile unavailable.
        """
        if profile_name:
            profile = assign_specific_profile(cpu_id, profile_name, self.code)
        else:
            profile = assign_profile(cpu_id, self.code)

        if not profile:
            return None

        room_player = RoomPlayer(
            id=cpu_id,
            name=profile.name,
            websocket=None,
            is_host=False,
            is_cpu=True,
        )
        self.players[cpu_id] = room_player

        game_player = Player(id=cpu_id, name=profile.name)
        self.game.add_player(game_player)

        return room_player

    def remove_player(self, player_id: str) -> Optional[RoomPlayer]:
        """
        Remove a player from the room.

        Handles host reassignment if the host leaves, and releases
        CPU profiles back to the pool.

        Args:
            player_id: ID of the player to remove.

        Returns:
            The removed RoomPlayer, or None if not found.
        """
        if player_id not in self.players:
            return None

        room_player = self.players.pop(player_id)
        self.game.remove_player(player_id)

        # Release CPU profile back to the room's pool
        if room_player.is_cpu:
            release_profile(room_player.name, self.code)

        # Assign new host if needed
        if room_player.is_host and self.players:
            next_host = next(iter(self.players.values()))
            next_host.is_host = True

        return room_player

    def get_player(self, player_id: str) -> Optional[RoomPlayer]:
        """Get a player by ID, or None if not found."""
        return self.players.get(player_id)

    def is_empty(self) -> bool:
        """Check if the room has no players."""
        return len(self.players) == 0

    def player_list(self) -> list[dict]:
        """
        Get list of players for client display.

        Returns:
            List of dicts with id, name, is_host, is_cpu, and style (for CPUs).
        """
        result = []
        for p in self.players.values():
            player_data = {
                "id": p.id,
                "name": p.name,
                "is_host": p.is_host,
                "is_cpu": p.is_cpu,
            }
            if p.is_cpu:
                profile = get_profile(p.id)
                if profile:
                    player_data["style"] = profile.style
            result.append(player_data)
        return result

    def get_cpu_players(self) -> list[RoomPlayer]:
        """Get all CPU players in the room."""
        return [p for p in self.players.values() if p.is_cpu]

    def human_player_count(self) -> int:
        """Count the number of human (non-CPU) players."""
        return sum(1 for p in self.players.values() if not p.is_cpu)

    async def broadcast(self, message: dict, exclude: Optional[str] = None) -> None:
        """
        Send a message to all human players in the room.

        Args:
            message: JSON-serializable message dict.
            exclude: Optional player ID to skip.
        """
        for player_id, player in self.players.items():
            if player_id != exclude and player.websocket and not player.is_cpu:
                try:
                    await player.websocket.send_json(message)
                except Exception:
                    pass

    async def send_to(self, player_id: str, message: dict) -> None:
        """
        Send a message to a specific player.

        Args:
            player_id: ID of the recipient player.
            message: JSON-serializable message dict.
        """
        player = self.players.get(player_id)
        if player and player.websocket and not player.is_cpu:
            try:
                await player.websocket.send_json(message)
            except Exception:
                pass


class RoomManager:
    """
    Manages all active game rooms.

    Provides room creation with unique codes, lookup, and cleanup.
    A single RoomManager instance is used by the server.
    """

    def __init__(self) -> None:
        """Initialize an empty room manager."""
        self.rooms: dict[str, Room] = {}

    def _generate_code(self, max_attempts: int = 100) -> str:
        """Generate a unique 4-letter room code."""
        for _ in range(max_attempts):
            code = "".join(random.choices(string.ascii_uppercase, k=4))
            if code not in self.rooms:
                return code
        raise RuntimeError("Could not generate unique room code")

    def create_room(self) -> Room:
        """
        Create a new room with a unique code.

        Returns:
            The newly created Room.
        """
        code = self._generate_code()
        room = Room(code=code)
        self.rooms[code] = room
        return room

    def get_room(self, code: str) -> Optional[Room]:
        """
        Get a room by its code (case-insensitive).

        Args:
            code: The 4-letter room code.

        Returns:
            The Room if found, None otherwise.
        """
        return self.rooms.get(code.upper())

    def remove_room(self, code: str) -> None:
        """
        Delete a room.

        Args:
            code: The room code to remove.
        """
        if code in self.rooms:
            del self.rooms[code]

    def find_player_room(self, player_id: str) -> Optional[Room]:
        """
        Find which room a player is in.

        Args:
            player_id: The player ID to search for.

        Returns:
            The Room containing the player, or None.
        """
        for room in self.rooms.values():
            if player_id in room.players:
                return room
        return None
