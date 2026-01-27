"""
Redis pub/sub for cross-server game events.

In a multi-server deployment, each server has its own WebSocket connections.
When a game action occurs, the server handling that action needs to notify
all other servers so they can update their connected clients.

This module provides:
- Pub/sub channels per room for targeted broadcasting
- Message types for state updates, player events, and broadcasts
- Async listener loop for handling incoming messages
- Clean subscription management

Usage:
    pubsub = GamePubSub(redis_client)
    await pubsub.start()

    # Subscribe to room events
    async def handle_message(msg: PubSubMessage):
        print(f"Received: {msg.type} for room {msg.room_code}")

    await pubsub.subscribe("ABCD", handle_message)

    # Publish to room
    await pubsub.publish(PubSubMessage(
        type=MessageType.GAME_STATE_UPDATE,
        room_code="ABCD",
        data={"game_state": {...}},
    ))

    await pubsub.stop()
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Awaitable, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Types of messages that can be published via pub/sub."""

    # Game state changed (other servers should update their cache)
    GAME_STATE_UPDATE = "game_state_update"

    # Player connected to room (for presence tracking)
    PLAYER_JOINED = "player_joined"

    # Player disconnected from room
    PLAYER_LEFT = "player_left"

    # Room is being closed (game ended or abandoned)
    ROOM_CLOSED = "room_closed"

    # Generic broadcast to all clients in room
    BROADCAST = "broadcast"


@dataclass
class PubSubMessage:
    """
    Message sent via Redis pub/sub.

    Attributes:
        type: Message type (determines how handlers process it).
        room_code: Room this message is for.
        data: Message payload (type-specific).
        sender_id: Optional server ID of sender (to avoid echo).
    """

    type: MessageType
    room_code: str
    data: dict
    sender_id: Optional[str] = None

    def to_json(self) -> str:
        """Serialize to JSON for Redis."""
        return json.dumps({
            "type": self.type.value,
            "room_code": self.room_code,
            "data": self.data,
            "sender_id": self.sender_id,
        })

    @classmethod
    def from_json(cls, raw: str) -> "PubSubMessage":
        """Deserialize from JSON."""
        d = json.loads(raw)
        return cls(
            type=MessageType(d["type"]),
            room_code=d["room_code"],
            data=d.get("data", {}),
            sender_id=d.get("sender_id"),
        )


# Type alias for message handlers
MessageHandler = Callable[[PubSubMessage], Awaitable[None]]


class GamePubSub:
    """
    Redis pub/sub for cross-server game events.

    Manages subscriptions to room channels and dispatches incoming
    messages to registered handlers.
    """

    CHANNEL_PREFIX = "golf:room:"

    def __init__(
        self,
        redis_client: redis.Redis,
        server_id: str = "default",
    ):
        """
        Initialize pub/sub with Redis client.

        Args:
            redis_client: Async Redis client.
            server_id: Unique ID for this server instance.
        """
        self.redis = redis_client
        self.server_id = server_id
        self.pubsub = redis_client.pubsub()
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _channel(self, room_code: str) -> str:
        """Get Redis channel name for a room."""
        return f"{self.CHANNEL_PREFIX}{room_code}"

    async def subscribe(
        self,
        room_code: str,
        handler: MessageHandler,
    ) -> None:
        """
        Subscribe to room events.

        Args:
            room_code: Room to subscribe to.
            handler: Async function to call on each message.
        """
        channel = self._channel(room_code)
        if channel not in self._handlers:
            self._handlers[channel] = []
            await self.pubsub.subscribe(channel)
            logger.debug(f"Subscribed to channel {channel}")
        self._handlers[channel].append(handler)

    async def unsubscribe(self, room_code: str) -> None:
        """
        Unsubscribe from room events.

        Args:
            room_code: Room to unsubscribe from.
        """
        channel = self._channel(room_code)
        if channel in self._handlers:
            del self._handlers[channel]
            await self.pubsub.unsubscribe(channel)
            logger.debug(f"Unsubscribed from channel {channel}")

    async def remove_handler(self, room_code: str, handler: MessageHandler) -> None:
        """
        Remove a specific handler from a room subscription.

        Args:
            room_code: Room the handler was registered for.
            handler: Handler to remove.
        """
        channel = self._channel(room_code)
        if channel in self._handlers:
            handlers = self._handlers[channel]
            if handler in handlers:
                handlers.remove(handler)
            # If no handlers left, unsubscribe
            if not handlers:
                await self.unsubscribe(room_code)

    async def publish(self, message: PubSubMessage) -> int:
        """
        Publish a message to a room's channel.

        Args:
            message: Message to publish.

        Returns:
            Number of subscribers that received the message.
        """
        # Add sender ID so we can filter out our own messages
        message.sender_id = self.server_id
        channel = self._channel(message.room_code)
        count = await self.redis.publish(channel, message.to_json())
        logger.debug(f"Published {message.type.value} to {channel} ({count} receivers)")
        return count

    async def start(self) -> None:
        """Start listening for messages."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._listen())
        logger.info("GamePubSub listener started")

    async def stop(self) -> None:
        """Stop listening and clean up."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        await self.pubsub.close()
        self._handlers.clear()
        logger.info("GamePubSub listener stopped")

    async def _listen(self) -> None:
        """Main listener loop."""
        while self._running:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message["type"] == "message":
                    await self._handle_message(message)

            except asyncio.CancelledError:
                break
            except redis.ConnectionError as e:
                logger.error(f"PubSub connection error: {e}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"PubSub listener error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _handle_message(self, raw_message: dict) -> None:
        """Handle an incoming Redis message."""
        try:
            channel = raw_message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode()

            data = raw_message["data"]
            if isinstance(data, bytes):
                data = data.decode()

            msg = PubSubMessage.from_json(data)

            # Skip messages from ourselves
            if msg.sender_id == self.server_id:
                return

            handlers = self._handlers.get(channel, [])
            for handler in handlers:
                try:
                    await handler(msg)
                except Exception as e:
                    logger.error(f"Error in pubsub handler: {e}", exc_info=True)

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in pubsub message: {e}")
        except Exception as e:
            logger.error(f"Error processing pubsub message: {e}", exc_info=True)


# Global pub/sub instance
_pubsub: Optional[GamePubSub] = None


async def get_pubsub(redis_client: redis.Redis, server_id: str = "default") -> GamePubSub:
    """
    Get or create the global pub/sub instance.

    Args:
        redis_client: Redis client to use.
        server_id: Unique ID for this server.

    Returns:
        GamePubSub instance.
    """
    global _pubsub
    if _pubsub is None:
        _pubsub = GamePubSub(redis_client, server_id)
    return _pubsub


async def close_pubsub() -> None:
    """Stop and close the global pub/sub instance."""
    global _pubsub
    if _pubsub is not None:
        await _pubsub.stop()
        _pubsub = None
