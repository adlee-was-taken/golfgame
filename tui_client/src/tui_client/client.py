"""WebSocket + HTTP networking for the TUI client."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)

_SESSION_DIR = Path.home() / ".config" / "golfcards"
_SESSION_FILE = _SESSION_DIR / "session.json"


class GameClient:
    """Handles HTTP auth and WebSocket game communication."""

    def __init__(self, host: str, use_tls: bool = True):
        self.host = host
        self.use_tls = use_tls
        self._token: Optional[str] = None
        self._ws: Optional[ClientConnection] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._app = None  # Set by GolfApp
        self._username: Optional[str] = None

    @property
    def http_base(self) -> str:
        scheme = "https" if self.use_tls else "http"
        return f"{scheme}://{self.host}"

    @property
    def ws_url(self) -> str:
        scheme = "wss" if self.use_tls else "ws"
        url = f"{scheme}://{self.host}/ws"
        if self._token:
            url += f"?token={self._token}"
        return url

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    @property
    def username(self) -> Optional[str]:
        return self._username

    def save_session(self) -> None:
        """Persist token and server info to disk."""
        if not self._token:
            return
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "host": self.host,
            "use_tls": self.use_tls,
            "token": self._token,
            "username": self._username,
        }
        _SESSION_FILE.write_text(json.dumps(data))

    @staticmethod
    def load_session() -> dict | None:
        """Load saved session from disk, or None if not found."""
        if not _SESSION_FILE.exists():
            return None
        try:
            return json.loads(_SESSION_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def clear_session() -> None:
        """Delete saved session file."""
        try:
            _SESSION_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    async def verify_token(self) -> bool:
        """Check if the current token is still valid via /api/auth/me."""
        if not self._token:
            return False
        try:
            async with httpx.AsyncClient(verify=self.use_tls) as http:
                resp = await http.get(
                    f"{self.http_base}/api/auth/me",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._username = data.get("username", self._username)
                    return True
                return False
        except Exception:
            return False

    def restore_session(self, session: dict) -> None:
        """Restore client state from a saved session dict."""
        self.host = session["host"]
        self.use_tls = session["use_tls"]
        self._token = session["token"]
        self._username = session.get("username")

    async def login(self, username: str, password: str) -> dict:
        """Login via HTTP and store JWT token.

        Returns the response dict on success, raises on failure.
        """
        async with httpx.AsyncClient(verify=self.use_tls) as http:
            resp = await http.post(
                f"{self.http_base}/api/auth/login",
                json={"username": username, "password": password},
            )
            if resp.status_code != 200:
                detail = resp.json().get("detail", "Login failed")
                raise ConnectionError(detail)
            data = resp.json()
            self._token = data["token"]
            self._username = data["user"]["username"]
            return data

    async def register(
        self, username: str, password: str, invite_code: str = "", email: str = ""
    ) -> dict:
        """Register a new account via HTTP and store JWT token."""
        payload: dict = {"username": username, "password": password}
        if invite_code:
            payload["invite_code"] = invite_code
        if email:
            payload["email"] = email
        async with httpx.AsyncClient(verify=self.use_tls) as http:
            resp = await http.post(
                f"{self.http_base}/api/auth/register",
                json=payload,
            )
            if resp.status_code != 200:
                detail = resp.json().get("detail", "Registration failed")
                raise ConnectionError(detail)
            data = resp.json()
            self._token = data["token"]
            self._username = data["user"]["username"]
            return data

    async def connect(self) -> None:
        """Open WebSocket connection to the server."""
        self._ws = await websockets.connect(self.ws_url)
        self._listener_task = asyncio.create_task(self._listen())

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(self, msg_type: str, **kwargs) -> None:
        """Send a JSON message over WebSocket."""
        if not self._ws:
            raise ConnectionError("Not connected")
        msg = {"type": msg_type, **kwargs}
        logger.debug(f"TX: {msg}")
        await self._ws.send(json.dumps(msg))

    async def _listen(self) -> None:
        """Background task: read messages from WebSocket and post to app."""
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                    logger.debug(f"RX: {data.get('type', '?')}")
                    if self._app:
                        self._app.post_server_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON message: {raw[:100]}")
        except websockets.ConnectionClosed as e:
            logger.info(f"WebSocket closed: {e}")
            if self._app:
                self._app.post_server_message({"type": "connection_closed", "reason": str(e)})
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"WebSocket listener error: {e}")
            if self._app:
                self._app.post_server_message({"type": "connection_error", "reason": str(e)})
