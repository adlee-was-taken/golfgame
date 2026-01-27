# V2-02: Persistence & Recovery

## Overview

This document covers the live state caching and game recovery system. Games will survive server restarts by storing live state in Redis and rebuilding from events.

**Dependencies:** V2-01 (Event Sourcing)
**Dependents:** V2-03 (User Accounts), V2-06 (Replay)

---

## Goals

1. Cache live game state in Redis
2. Implement Redis pub/sub for multi-server support
3. Enable game recovery from events on server restart
4. Implement graceful shutdown with state preservation

---

## Current State

Games are stored in-memory in `main.py`:

```python
# Current approach
rooms: dict[str, Room] = {}  # Lost on restart!
```

On server restart, all active games are lost.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   FastAPI #1    │     │   FastAPI #2    │     │   FastAPI #N    │
│   (WebSocket)   │     │   (WebSocket)   │     │   (WebSocket)   │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │         Redis           │
                    │  ┌─────────────────┐   │
                    │  │  State Cache    │   │  <- Live game state
                    │  │  (Hash/JSON)    │   │
                    │  └─────────────────┘   │
                    │  ┌─────────────────┐   │
                    │  │    Pub/Sub      │   │  <- Cross-server events
                    │  │   (Channels)    │   │
                    │  └─────────────────┘   │
                    │  ┌─────────────────┐   │
                    │  │   Room Index    │   │  <- Active room codes
                    │  │    (Set)        │   │
                    │  └─────────────────┘   │
                    └─────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │      PostgreSQL         │
                    │    (Event Store)        │  <- Source of truth
                    └─────────────────────────┘
```

---

## Redis Data Model

### Key Patterns

```
golf:room:{room_code}          -> Hash (room metadata)
golf:game:{game_id}            -> JSON (full game state)
golf:room:{room_code}:players  -> Set (connected player IDs)
golf:rooms:active              -> Set (active room codes)
golf:player:{player_id}:room   -> String (player's current room)
```

### Room Metadata Hash

```
golf:room:ABCD
├── game_id: "uuid-..."
├── host_id: "player-uuid"
├── created_at: "2024-01-15T10:30:00Z"
├── status: "waiting" | "playing" | "finished"
└── server_id: "server-1"  # Which server owns this room
```

### Game State JSON

```json
{
  "game_id": "uuid-...",
  "room_code": "ABCD",
  "phase": "playing",
  "current_round": 3,
  "total_rounds": 9,
  "current_player_idx": 1,
  "player_order": ["p1", "p2", "p3"],
  "players": {
    "p1": {
      "id": "p1",
      "name": "Alice",
      "cards": [{"rank": "K", "suit": "hearts", "face_up": true}, ...],
      "score": null,
      "total_score": 15,
      "rounds_won": 1,
      "is_cpu": false
    }
  },
  "deck_count": 32,
  "discard_top": {"rank": "7", "suit": "clubs"},
  "drawn_card": null,
  "options": {...},
  "sequence_num": 47
}
```

---

## State Cache Implementation

```python
# server/stores/state_cache.py
import json
from typing import Optional
from datetime import timedelta
import redis.asyncio as redis

from models.game_state import RebuiltGameState


class StateCache:
    """Redis-backed live game state cache."""

    # Key patterns
    ROOM_KEY = "golf:room:{room_code}"
    GAME_KEY = "golf:game:{game_id}"
    ROOM_PLAYERS_KEY = "golf:room:{room_code}:players"
    ACTIVE_ROOMS_KEY = "golf:rooms:active"
    PLAYER_ROOM_KEY = "golf:player:{player_id}:room"

    # TTLs
    ROOM_TTL = timedelta(hours=4)  # Inactive rooms expire
    GAME_TTL = timedelta(hours=4)

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    # --- Room Operations ---

    async def create_room(
        self,
        room_code: str,
        game_id: str,
        host_id: str,
        server_id: str,
    ) -> None:
        """Create a new room."""
        pipe = self.redis.pipeline()

        # Room metadata
        pipe.hset(
            self.ROOM_KEY.format(room_code=room_code),
            mapping={
                "game_id": game_id,
                "host_id": host_id,
                "status": "waiting",
                "server_id": server_id,
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        pipe.expire(self.ROOM_KEY.format(room_code=room_code), self.ROOM_TTL)

        # Add to active rooms
        pipe.sadd(self.ACTIVE_ROOMS_KEY, room_code)

        # Track host's room
        pipe.set(
            self.PLAYER_ROOM_KEY.format(player_id=host_id),
            room_code,
            ex=self.ROOM_TTL,
        )

        await pipe.execute()

    async def get_room(self, room_code: str) -> Optional[dict]:
        """Get room metadata."""
        data = await self.redis.hgetall(self.ROOM_KEY.format(room_code=room_code))
        if not data:
            return None
        return {k.decode(): v.decode() for k, v in data.items()}

    async def room_exists(self, room_code: str) -> bool:
        """Check if room exists."""
        return await self.redis.exists(self.ROOM_KEY.format(room_code=room_code)) > 0

    async def delete_room(self, room_code: str) -> None:
        """Delete a room and all associated data."""
        room = await self.get_room(room_code)
        if not room:
            return

        pipe = self.redis.pipeline()

        # Get players to clean up their mappings
        players = await self.redis.smembers(
            self.ROOM_PLAYERS_KEY.format(room_code=room_code)
        )
        for player_id in players:
            pipe.delete(self.PLAYER_ROOM_KEY.format(player_id=player_id.decode()))

        # Delete room data
        pipe.delete(self.ROOM_KEY.format(room_code=room_code))
        pipe.delete(self.ROOM_PLAYERS_KEY.format(room_code=room_code))
        pipe.srem(self.ACTIVE_ROOMS_KEY, room_code)

        # Delete game state if exists
        if "game_id" in room:
            pipe.delete(self.GAME_KEY.format(game_id=room["game_id"]))

        await pipe.execute()

    async def get_active_rooms(self) -> set[str]:
        """Get all active room codes."""
        rooms = await self.redis.smembers(self.ACTIVE_ROOMS_KEY)
        return {r.decode() for r in rooms}

    # --- Player Operations ---

    async def add_player_to_room(self, room_code: str, player_id: str) -> None:
        """Add a player to a room."""
        pipe = self.redis.pipeline()
        pipe.sadd(self.ROOM_PLAYERS_KEY.format(room_code=room_code), player_id)
        pipe.set(
            self.PLAYER_ROOM_KEY.format(player_id=player_id),
            room_code,
            ex=self.ROOM_TTL,
        )
        # Refresh room TTL on activity
        pipe.expire(self.ROOM_KEY.format(room_code=room_code), self.ROOM_TTL)
        await pipe.execute()

    async def remove_player_from_room(self, room_code: str, player_id: str) -> None:
        """Remove a player from a room."""
        pipe = self.redis.pipeline()
        pipe.srem(self.ROOM_PLAYERS_KEY.format(room_code=room_code), player_id)
        pipe.delete(self.PLAYER_ROOM_KEY.format(player_id=player_id))
        await pipe.execute()

    async def get_room_players(self, room_code: str) -> set[str]:
        """Get player IDs in a room."""
        players = await self.redis.smembers(
            self.ROOM_PLAYERS_KEY.format(room_code=room_code)
        )
        return {p.decode() for p in players}

    async def get_player_room(self, player_id: str) -> Optional[str]:
        """Get the room a player is in."""
        room = await self.redis.get(self.PLAYER_ROOM_KEY.format(player_id=player_id))
        return room.decode() if room else None

    # --- Game State Operations ---

    async def save_game_state(self, game_id: str, state: dict) -> None:
        """Save full game state."""
        await self.redis.set(
            self.GAME_KEY.format(game_id=game_id),
            json.dumps(state),
            ex=self.GAME_TTL,
        )

    async def get_game_state(self, game_id: str) -> Optional[dict]:
        """Get full game state."""
        data = await self.redis.get(self.GAME_KEY.format(game_id=game_id))
        if not data:
            return None
        return json.loads(data)

    async def update_game_state(self, game_id: str, updates: dict) -> None:
        """Partial update to game state (get, merge, set)."""
        state = await self.get_game_state(game_id)
        if state:
            state.update(updates)
            await self.save_game_state(game_id, state)

    async def delete_game_state(self, game_id: str) -> None:
        """Delete game state."""
        await self.redis.delete(self.GAME_KEY.format(game_id=game_id))

    # --- Room Status ---

    async def set_room_status(self, room_code: str, status: str) -> None:
        """Update room status."""
        await self.redis.hset(
            self.ROOM_KEY.format(room_code=room_code),
            "status",
            status,
        )

    async def refresh_room_ttl(self, room_code: str) -> None:
        """Refresh room TTL on activity."""
        pipe = self.redis.pipeline()
        pipe.expire(self.ROOM_KEY.format(room_code=room_code), self.ROOM_TTL)

        room = await self.get_room(room_code)
        if room and "game_id" in room:
            pipe.expire(self.GAME_KEY.format(game_id=room["game_id"]), self.GAME_TTL)

        await pipe.execute()
```

---

## Pub/Sub for Multi-Server

```python
# server/stores/pubsub.py
import asyncio
import json
from typing import Callable, Awaitable
from dataclasses import dataclass
from enum import Enum
import redis.asyncio as redis


class MessageType(str, Enum):
    GAME_STATE_UPDATE = "game_state_update"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    ROOM_CLOSED = "room_closed"
    BROADCAST = "broadcast"


@dataclass
class PubSubMessage:
    type: MessageType
    room_code: str
    data: dict

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "room_code": self.room_code,
            "data": self.data,
        })

    @classmethod
    def from_json(cls, raw: str) -> "PubSubMessage":
        d = json.loads(raw)
        return cls(
            type=MessageType(d["type"]),
            room_code=d["room_code"],
            data=d["data"],
        )


class GamePubSub:
    """Redis pub/sub for cross-server game events."""

    CHANNEL_PREFIX = "golf:room:"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.pubsub = redis_client.pubsub()
        self._handlers: dict[str, list[Callable[[PubSubMessage], Awaitable[None]]]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _channel(self, room_code: str) -> str:
        return f"{self.CHANNEL_PREFIX}{room_code}"

    async def subscribe(
        self,
        room_code: str,
        handler: Callable[[PubSubMessage], Awaitable[None]],
    ) -> None:
        """Subscribe to room events."""
        channel = self._channel(room_code)
        if channel not in self._handlers:
            self._handlers[channel] = []
            await self.pubsub.subscribe(channel)
        self._handlers[channel].append(handler)

    async def unsubscribe(self, room_code: str) -> None:
        """Unsubscribe from room events."""
        channel = self._channel(room_code)
        if channel in self._handlers:
            del self._handlers[channel]
            await self.pubsub.unsubscribe(channel)

    async def publish(self, message: PubSubMessage) -> None:
        """Publish a message to a room's channel."""
        channel = self._channel(message.room_code)
        await self.redis.publish(channel, message.to_json())

    async def start(self) -> None:
        """Start listening for messages."""
        self._running = True
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.pubsub.close()

    async def _listen(self) -> None:
        """Main listener loop."""
        while self._running:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message["type"] == "message":
                    channel = message["channel"].decode()
                    handlers = self._handlers.get(channel, [])

                    try:
                        msg = PubSubMessage.from_json(message["data"].decode())
                        for handler in handlers:
                            await handler(msg)
                    except Exception as e:
                        print(f"Error handling pubsub message: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"PubSub listener error: {e}")
                await asyncio.sleep(1)
```

---

## Game Recovery

```python
# server/services/recovery_service.py
from typing import Optional
import asyncio

from stores.event_store import EventStore
from stores.state_cache import StateCache
from models.events import rebuild_state, EventType


class RecoveryService:
    """Recovers games from event store on startup."""

    def __init__(self, event_store: EventStore, state_cache: StateCache):
        self.event_store = event_store
        self.state_cache = state_cache

    async def recover_all_games(self) -> dict[str, any]:
        """
        Recover all active games from event store.
        Returns dict of recovered games.
        """
        results = {
            "recovered": 0,
            "failed": 0,
            "skipped": 0,
            "games": [],
        }

        # Get active rooms from Redis (may be stale)
        active_rooms = await self.state_cache.get_active_rooms()

        for room_code in active_rooms:
            room = await self.state_cache.get_room(room_code)
            if not room:
                results["skipped"] += 1
                continue

            game_id = room.get("game_id")
            if not game_id:
                results["skipped"] += 1
                continue

            try:
                game = await self.recover_game(game_id)
                if game:
                    results["recovered"] += 1
                    results["games"].append({
                        "game_id": game_id,
                        "room_code": room_code,
                        "phase": game.phase.value,
                        "sequence": game.sequence_num,
                    })
                else:
                    results["skipped"] += 1
            except Exception as e:
                print(f"Failed to recover game {game_id}: {e}")
                results["failed"] += 1

        return results

    async def recover_game(self, game_id: str) -> Optional[any]:
        """
        Recover a single game from event store.
        Returns the rebuilt game state.
        """
        # Get all events for this game
        events = await self.event_store.get_events(game_id)

        if not events:
            return None

        # Check if game is actually active (not ended)
        last_event = events[-1]
        if last_event.event_type == EventType.GAME_ENDED:
            return None  # Game is finished, don't recover

        # Rebuild state
        state = rebuild_state(events)

        # Save to cache
        await self.state_cache.save_game_state(
            game_id,
            self._state_to_dict(state),
        )

        return state

    async def recover_from_sequence(
        self,
        game_id: str,
        cached_state: dict,
        cached_sequence: int,
    ) -> Optional[any]:
        """
        Recover game by applying only new events to cached state.
        More efficient than full rebuild.
        """
        # Get events after cached sequence
        new_events = await self.event_store.get_events(
            game_id,
            from_sequence=cached_sequence + 1,
        )

        if not new_events:
            return None  # No new events

        # Rebuild state from cache + new events
        state = self._dict_to_state(cached_state)
        for event in new_events:
            state.apply(event)

        # Update cache
        await self.state_cache.save_game_state(
            game_id,
            self._state_to_dict(state),
        )

        return state

    def _state_to_dict(self, state) -> dict:
        """Convert RebuiltGameState to dict for caching."""
        return {
            "game_id": state.game_id,
            "room_code": state.room_code,
            "phase": state.phase.value,
            "current_round": state.current_round,
            "total_rounds": state.total_rounds,
            "current_player_idx": state.current_player_idx,
            "player_order": state.player_order,
            "players": {
                pid: {
                    "id": p.id,
                    "name": p.name,
                    "cards": [c.to_dict() for c in p.cards],
                    "score": p.score,
                    "total_score": p.total_score,
                    "rounds_won": p.rounds_won,
                    "is_cpu": p.is_cpu,
                    "cpu_profile": p.cpu_profile,
                }
                for pid, p in state.players.items()
            },
            "deck_count": len(state.deck),
            "discard_top": state.discard[-1].to_dict() if state.discard else None,
            "drawn_card": state.drawn_card.to_dict() if state.drawn_card else None,
            "options": state.options,
            "sequence_num": state.sequence_num,
            "finisher_id": state.finisher_id,
        }

    def _dict_to_state(self, d: dict):
        """Convert dict back to RebuiltGameState."""
        # Implementation depends on RebuiltGameState structure
        pass
```

---

## Graceful Shutdown

```python
# server/main.py additions
import signal
import asyncio
from contextlib import asynccontextmanager

from stores.state_cache import StateCache
from stores.event_store import EventStore
from services.recovery_service import RecoveryService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("Starting up...")

    # Initialize connections
    app.state.redis = await create_redis_pool()
    app.state.pg_pool = await create_pg_pool()

    app.state.state_cache = StateCache(app.state.redis)
    app.state.event_store = EventStore(app.state.pg_pool)
    app.state.recovery_service = RecoveryService(
        app.state.event_store,
        app.state.state_cache,
    )

    # Recover games
    print("Recovering games from event store...")
    results = await app.state.recovery_service.recover_all_games()
    print(f"Recovery complete: {results['recovered']} recovered, "
          f"{results['failed']} failed, {results['skipped']} skipped")

    # Start pub/sub
    app.state.pubsub = GamePubSub(app.state.redis)
    await app.state.pubsub.start()

    yield

    # Shutdown
    print("Shutting down...")

    # Stop accepting new connections
    await app.state.pubsub.stop()

    # Flush any pending state to Redis
    await flush_pending_states(app)

    # Close connections
    await app.state.redis.close()
    await app.state.pg_pool.close()

    print("Shutdown complete")


async def flush_pending_states(app: FastAPI):
    """Flush any in-memory state to Redis before shutdown."""
    # If we have any rooms with unsaved state, save them now
    for room_code, room in rooms.items():
        if room.game and room.game.game_id:
            try:
                state = room.game.get_full_state()
                await app.state.state_cache.save_game_state(
                    room.game.game_id,
                    state,
                )
            except Exception as e:
                print(f"Error flushing state for room {room_code}: {e}")


app = FastAPI(lifespan=lifespan)


# Handle SIGTERM gracefully
def handle_sigterm(signum, frame):
    """Handle SIGTERM by initiating graceful shutdown."""
    raise KeyboardInterrupt()

signal.signal(signal.SIGTERM, handle_sigterm)
```

---

## Integration with Game Service

```python
# server/services/game_service.py
from stores.state_cache import StateCache
from stores.event_store import EventStore
from stores.pubsub import GamePubSub, PubSubMessage, MessageType


class GameService:
    """
    Handles game commands with event sourcing.
    Coordinates between event store, state cache, and pub/sub.
    """

    def __init__(
        self,
        event_store: EventStore,
        state_cache: StateCache,
        pubsub: GamePubSub,
    ):
        self.event_store = event_store
        self.state_cache = state_cache
        self.pubsub = pubsub

    async def handle_draw(
        self,
        game_id: str,
        player_id: str,
        source: str,
    ) -> dict:
        """Handle draw card command."""
        # 1. Get current state from cache
        state = await self.state_cache.get_game_state(game_id)
        if not state:
            raise GameNotFoundError(game_id)

        # 2. Validate command
        if state["current_player_id"] != player_id:
            raise NotYourTurnError()

        # 3. Execute command (get card from deck/discard)
        # This uses the existing game logic
        game = self._load_game_from_state(state)
        card = game.draw_card(player_id, source)

        if not card:
            raise InvalidMoveError("Cannot draw from that source")

        # 4. Create event
        event = GameEvent(
            event_type=EventType.CARD_DRAWN,
            game_id=game_id,
            sequence_num=state["sequence_num"] + 1,
            player_id=player_id,
            data={"source": source, "card": card.to_dict()},
        )

        # 5. Persist event
        await self.event_store.append(event)

        # 6. Update cache
        new_state = game.get_full_state()
        new_state["sequence_num"] = event.sequence_num
        await self.state_cache.save_game_state(game_id, new_state)

        # 7. Publish to other servers
        await self.pubsub.publish(PubSubMessage(
            type=MessageType.GAME_STATE_UPDATE,
            room_code=state["room_code"],
            data={"game_state": new_state},
        ))

        return new_state
```

---

## Acceptance Criteria

1. **Redis State Cache Working**
   - [ ] Can create/get/delete rooms
   - [ ] Can add/remove players from rooms
   - [ ] Can save/get/delete game state
   - [ ] TTL expiration works correctly
   - [ ] Room code uniqueness enforced

2. **Pub/Sub Working**
   - [ ] Can subscribe to room channels
   - [ ] Can publish messages
   - [ ] Messages received by all subscribers
   - [ ] Handles disconnections gracefully
   - [ ] Multiple servers can communicate

3. **Game Recovery Working**
   - [ ] Games recovered on startup
   - [ ] State matches what was saved
   - [ ] Partial recovery (from sequence) works
   - [ ] Ended games not recovered
   - [ ] Failed recoveries logged and skipped

4. **Graceful Shutdown Working**
   - [ ] SIGTERM triggers clean shutdown
   - [ ] In-flight requests complete
   - [ ] State flushed to Redis
   - [ ] Connections closed cleanly
   - [ ] No data loss on restart

5. **Integration Tests**
   - [ ] Server restart doesn't lose games
   - [ ] Multi-server state sync works
   - [ ] State cache matches event store
   - [ ] Performance acceptable (<100ms for state ops)

---

## Implementation Order

1. Set up Redis locally (docker)
2. Implement StateCache class
3. Write StateCache tests
4. Implement GamePubSub class
5. Implement RecoveryService
6. Add lifespan handler to main.py
7. Integrate with game commands
8. Test full recovery cycle
9. Test multi-server pub/sub

---

## Docker Setup for Development

```yaml
# docker-compose.dev.yml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: golf
      POSTGRES_PASSWORD: devpassword
      POSTGRES_DB: golf
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  redis_data:
  postgres_data:
```

```bash
# Start services
docker-compose -f docker-compose.dev.yml up -d

# Connect to Redis CLI
docker exec -it golfgame_redis_1 redis-cli

# Connect to PostgreSQL
docker exec -it golfgame_postgres_1 psql -U golf
```

---

## Notes for Agent

- Redis operations should use pipelines for atomicity
- Consider Redis Cluster for production (but not needed initially)
- The state cache is a cache, not source of truth (events are)
- Pub/sub is best-effort; state sync should handle missed messages
- Test with multiple server instances locally
- Use connection pooling for both Redis and PostgreSQL
