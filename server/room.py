"""Room management for multiplayer games."""

import random
import string
from dataclasses import dataclass, field
from typing import Optional
from fastapi import WebSocket

from game import Game, Player
from ai import assign_profile, release_profile, get_profile, assign_specific_profile


@dataclass
class RoomPlayer:
    id: str
    name: str
    websocket: Optional[WebSocket] = None
    is_host: bool = False
    is_cpu: bool = False


@dataclass
class Room:
    code: str
    players: dict[str, RoomPlayer] = field(default_factory=dict)
    game: Game = field(default_factory=Game)
    settings: dict = field(default_factory=lambda: {"decks": 1, "rounds": 1})
    game_log_id: Optional[str] = None  # For SQLite logging

    def add_player(self, player_id: str, name: str, websocket: WebSocket) -> RoomPlayer:
        is_host = len(self.players) == 0
        room_player = RoomPlayer(
            id=player_id,
            name=name,
            websocket=websocket,
            is_host=is_host,
        )
        self.players[player_id] = room_player

        # Add to game
        game_player = Player(id=player_id, name=name)
        self.game.add_player(game_player)

        return room_player

    def add_cpu_player(self, cpu_id: str, profile_name: Optional[str] = None) -> Optional[RoomPlayer]:
        # Get a CPU profile (specific or random)
        if profile_name:
            profile = assign_specific_profile(cpu_id, profile_name)
        else:
            profile = assign_profile(cpu_id)

        if not profile:
            return None  # Profile not available

        room_player = RoomPlayer(
            id=cpu_id,
            name=profile.name,
            websocket=None,
            is_host=False,
            is_cpu=True,
        )
        self.players[cpu_id] = room_player

        # Add to game
        game_player = Player(id=cpu_id, name=profile.name)
        self.game.add_player(game_player)

        return room_player

    def remove_player(self, player_id: str) -> Optional[RoomPlayer]:
        if player_id in self.players:
            room_player = self.players.pop(player_id)
            self.game.remove_player(player_id)

            # Release CPU profile back to the pool
            if room_player.is_cpu:
                release_profile(room_player.name)

            # Assign new host if needed
            if room_player.is_host and self.players:
                next_host = next(iter(self.players.values()))
                next_host.is_host = True

            return room_player
        return None

    def get_player(self, player_id: str) -> Optional[RoomPlayer]:
        return self.players.get(player_id)

    def is_empty(self) -> bool:
        return len(self.players) == 0

    def player_list(self) -> list[dict]:
        result = []
        for p in self.players.values():
            player_data = {"id": p.id, "name": p.name, "is_host": p.is_host, "is_cpu": p.is_cpu}
            if p.is_cpu:
                profile = get_profile(p.id)
                if profile:
                    player_data["style"] = profile.style
            result.append(player_data)
        return result

    def get_cpu_players(self) -> list[RoomPlayer]:
        return [p for p in self.players.values() if p.is_cpu]

    def human_player_count(self) -> int:
        return sum(1 for p in self.players.values() if not p.is_cpu)

    async def broadcast(self, message: dict, exclude: Optional[str] = None):
        for player_id, player in self.players.items():
            if player_id != exclude and player.websocket and not player.is_cpu:
                try:
                    await player.websocket.send_json(message)
                except Exception:
                    pass

    async def send_to(self, player_id: str, message: dict):
        player = self.players.get(player_id)
        if player and player.websocket and not player.is_cpu:
            try:
                await player.websocket.send_json(message)
            except Exception:
                pass


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}

    def _generate_code(self) -> str:
        while True:
            code = "".join(random.choices(string.ascii_uppercase, k=4))
            if code not in self.rooms:
                return code

    def create_room(self) -> Room:
        code = self._generate_code()
        room = Room(code=code)
        self.rooms[code] = room
        return room

    def get_room(self, code: str) -> Optional[Room]:
        return self.rooms.get(code.upper())

    def remove_room(self, code: str):
        if code in self.rooms:
            del self.rooms[code]

    def find_player_room(self, player_id: str) -> Optional[Room]:
        for room in self.rooms.values():
            if player_id in room.players:
                return room
        return None
