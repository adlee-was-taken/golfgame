# V2_06: Game Replay & Export System

> **Scope**: Replay viewer, game export/import, share links, spectator mode
> **Dependencies**: V2_01 (Event Sourcing), V2_02 (Persistence), V2_03 (User Accounts)
> **Complexity**: Medium

---

## Overview

The replay system leverages our event-sourced architecture to provide:
- **Replay Viewer**: Step through any completed game move-by-move
- **Export/Import**: Download games as JSON, share with others
- **Share Links**: Generate public links to specific games
- **Spectator Mode**: Watch live games in progress

---

## 1. Database Schema

### Shared Games Table

```sql
-- Public share links for completed games
CREATE TABLE shared_games (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id),
    share_code VARCHAR(12) UNIQUE NOT NULL,  -- Short shareable code
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,  -- NULL = never expires
    view_count INTEGER DEFAULT 0,
    is_public BOOLEAN DEFAULT true,
    title VARCHAR(100),  -- Optional custom title
    description TEXT     -- Optional description
);

CREATE INDEX idx_shared_games_code ON shared_games(share_code);
CREATE INDEX idx_shared_games_game ON shared_games(game_id);

-- Track replay views for analytics
CREATE TABLE replay_views (
    id SERIAL PRIMARY KEY,
    shared_game_id UUID REFERENCES shared_games(id),
    viewer_id UUID REFERENCES users(id),  -- NULL for anonymous
    viewed_at TIMESTAMPTZ DEFAULT NOW(),
    ip_hash VARCHAR(64),  -- Hashed IP for rate limiting
    watch_duration_seconds INTEGER
);
```

---

## 2. Replay Service

### Core Implementation

```python
# server/replay.py
from dataclasses import dataclass
from typing import Optional
import secrets
import json

from server.events import EventStore, GameEvent
from server.game import Game, GameOptions

@dataclass
class ReplayFrame:
    """Single frame in a replay."""
    event_index: int
    event: GameEvent
    game_state: dict  # Serialized game state after event
    timestamp: float

@dataclass
class GameReplay:
    """Complete replay of a game."""
    game_id: str
    frames: list[ReplayFrame]
    total_duration_seconds: float
    player_names: list[str]
    final_scores: dict[str, int]
    winner: Optional[str]
    options: GameOptions

class ReplayService:
    def __init__(self, event_store: EventStore, db_pool):
        self.event_store = event_store
        self.db = db_pool

    async def build_replay(self, game_id: str) -> GameReplay:
        """Build complete replay from event store."""
        events = await self.event_store.get_events(game_id)
        if not events:
            raise ValueError(f"No events found for game {game_id}")

        frames = []
        game = None
        start_time = None

        for i, event in enumerate(events):
            if start_time is None:
                start_time = event.timestamp

            # Apply event to get state
            if event.event_type == "game_started":
                game = Game.from_event(event)
            else:
                game.apply_event(event)

            frames.append(ReplayFrame(
                event_index=i,
                event=event,
                game_state=game.to_dict(reveal_all=True),
                timestamp=(event.timestamp - start_time).total_seconds()
            ))

        return GameReplay(
            game_id=game_id,
            frames=frames,
            total_duration_seconds=frames[-1].timestamp if frames else 0,
            player_names=[p.name for p in game.players],
            final_scores={p.name: p.score for p in game.players},
            winner=game.winner.name if game.winner else None,
            options=game.options
        )

    async def create_share_link(
        self,
        game_id: str,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        expires_days: Optional[int] = None
    ) -> str:
        """Generate shareable link for a game."""
        share_code = secrets.token_urlsafe(8)[:12]  # 12-char code

        expires_at = None
        if expires_days:
            expires_at = f"NOW() + INTERVAL '{expires_days} days'"

        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO shared_games
                    (game_id, share_code, created_by, title, expires_at)
                VALUES ($1, $2, $3, $4, $5)
            """, game_id, share_code, user_id, title, expires_at)

        return share_code

    async def get_shared_game(self, share_code: str) -> Optional[dict]:
        """Retrieve shared game by code."""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT sg.*, g.room_code, g.completed_at
                FROM shared_games sg
                JOIN games g ON sg.game_id = g.id
                WHERE sg.share_code = $1
                  AND sg.is_public = true
                  AND (sg.expires_at IS NULL OR sg.expires_at > NOW())
            """, share_code)

            if row:
                # Increment view count
                await conn.execute("""
                    UPDATE shared_games SET view_count = view_count + 1
                    WHERE share_code = $1
                """, share_code)

                return dict(row)
        return None

    async def export_game(self, game_id: str) -> dict:
        """Export game as portable JSON format."""
        replay = await self.build_replay(game_id)

        return {
            "version": "1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "game": {
                "id": replay.game_id,
                "players": replay.player_names,
                "winner": replay.winner,
                "final_scores": replay.final_scores,
                "duration_seconds": replay.total_duration_seconds,
                "options": asdict(replay.options)
            },
            "events": [
                {
                    "type": f.event.event_type,
                    "data": f.event.data,
                    "timestamp": f.timestamp
                }
                for f in replay.frames
            ]
        }

    async def import_game(self, export_data: dict, user_id: str) -> str:
        """Import a game from exported JSON."""
        if export_data.get("version") != "1.0":
            raise ValueError("Unsupported export version")

        # Generate new game ID for import
        new_game_id = str(uuid.uuid4())

        # Store events with new game ID
        for event_data in export_data["events"]:
            event = GameEvent(
                game_id=new_game_id,
                event_type=event_data["type"],
                data=event_data["data"],
                timestamp=datetime.fromisoformat(event_data["timestamp"])
            )
            await self.event_store.append(event)

        # Mark as imported game
        async with self.db.acquire() as conn:
            await conn.execute("""
                INSERT INTO games (id, imported_by, imported_at, is_imported)
                VALUES ($1, $2, NOW(), true)
            """, new_game_id, user_id)

        return new_game_id
```

---

## 3. Spectator Mode

### Live Game Watching

```python
# server/spectator.py
from typing import Set
from fastapi import WebSocket

class SpectatorManager:
    """Manage spectators watching live games."""

    def __init__(self):
        # game_id -> set of spectator websockets
        self.spectators: dict[str, Set[WebSocket]] = {}

    async def add_spectator(self, game_id: str, ws: WebSocket):
        """Add spectator to game."""
        if game_id not in self.spectators:
            self.spectators[game_id] = set()
        self.spectators[game_id].add(ws)

        # Send current game state
        game = await self.get_game_state(game_id)
        await ws.send_json({
            "type": "spectator_joined",
            "game": game.to_dict(reveal_all=False),
            "spectator_count": len(self.spectators[game_id])
        })

    async def remove_spectator(self, game_id: str, ws: WebSocket):
        """Remove spectator from game."""
        if game_id in self.spectators:
            self.spectators[game_id].discard(ws)
            if not self.spectators[game_id]:
                del self.spectators[game_id]

    async def broadcast_to_spectators(self, game_id: str, message: dict):
        """Send update to all spectators of a game."""
        if game_id not in self.spectators:
            return

        dead_connections = set()
        for ws in self.spectators[game_id]:
            try:
                await ws.send_json(message)
            except:
                dead_connections.add(ws)

        # Clean up dead connections
        self.spectators[game_id] -= dead_connections

    def get_spectator_count(self, game_id: str) -> int:
        return len(self.spectators.get(game_id, set()))

# Integration with main game loop
async def handle_game_event(game_id: str, event: GameEvent):
    """Called after each game event to notify spectators."""
    await spectator_manager.broadcast_to_spectators(game_id, {
        "type": "game_update",
        "event": event.to_dict(),
        "timestamp": event.timestamp.isoformat()
    })
```

---

## 4. API Endpoints

```python
# server/routes/replay.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/replay", tags=["replay"])

@router.get("/game/{game_id}")
async def get_replay(game_id: str, user: Optional[User] = Depends(get_current_user)):
    """Get full replay for a game."""
    # Check if user has permission (played in game or game is public)
    if not await can_view_game(user, game_id):
        raise HTTPException(403, "Cannot view this game")

    replay = await replay_service.build_replay(game_id)
    return {
        "game_id": replay.game_id,
        "frames": [
            {
                "index": f.event_index,
                "event_type": f.event.event_type,
                "timestamp": f.timestamp,
                "state": f.game_state
            }
            for f in replay.frames
        ],
        "metadata": {
            "players": replay.player_names,
            "winner": replay.winner,
            "final_scores": replay.final_scores,
            "duration": replay.total_duration_seconds
        }
    }

@router.post("/game/{game_id}/share")
async def create_share_link(
    game_id: str,
    title: Optional[str] = None,
    expires_days: Optional[int] = Query(None, ge=1, le=365),
    user: User = Depends(require_auth)
):
    """Create shareable link for a game."""
    if not await user_played_in_game(user.id, game_id):
        raise HTTPException(403, "Can only share games you played in")

    share_code = await replay_service.create_share_link(
        game_id, user.id, title, expires_days
    )

    return {
        "share_code": share_code,
        "share_url": f"/replay/{share_code}",
        "expires_days": expires_days
    }

@router.get("/shared/{share_code}")
async def get_shared_replay(share_code: str):
    """Get replay via share code (public endpoint)."""
    shared = await replay_service.get_shared_game(share_code)
    if not shared:
        raise HTTPException(404, "Shared game not found or expired")

    replay = await replay_service.build_replay(shared["game_id"])
    return {
        "title": shared.get("title"),
        "view_count": shared["view_count"],
        "replay": replay
    }

@router.get("/game/{game_id}/export")
async def export_game(game_id: str, user: User = Depends(require_auth)):
    """Export game as downloadable JSON."""
    if not await can_view_game(user, game_id):
        raise HTTPException(403, "Cannot export this game")

    export_data = await replay_service.export_game(game_id)

    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="golf-game-{game_id[:8]}.json"'
        }
    )

@router.post("/import")
async def import_game(
    export_data: dict,
    user: User = Depends(require_auth)
):
    """Import a game from JSON export."""
    try:
        new_game_id = await replay_service.import_game(export_data, user.id)
        return {"game_id": new_game_id, "message": "Game imported successfully"}
    except ValueError as e:
        raise HTTPException(400, str(e))

# Spectator endpoints
@router.websocket("/spectate/{room_code}")
async def spectate_game(websocket: WebSocket, room_code: str):
    """WebSocket endpoint for spectating live games."""
    await websocket.accept()

    game_id = await get_game_id_by_room(room_code)
    if not game_id:
        await websocket.close(code=4004, reason="Game not found")
        return

    try:
        await spectator_manager.add_spectator(game_id, websocket)

        while True:
            # Keep connection alive, handle pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await spectator_manager.remove_spectator(game_id, websocket)
```

---

## 5. Frontend: Replay Viewer

### Replay Component

```javascript
// client/replay.js
class ReplayViewer {
    constructor(container) {
        this.container = container;
        this.frames = [];
        this.currentFrame = 0;
        this.isPlaying = false;
        this.playbackSpeed = 1.0;
        this.playInterval = null;
    }

    async loadReplay(gameId) {
        const response = await fetch(`/api/replay/game/${gameId}`);
        const data = await response.json();

        this.frames = data.frames;
        this.metadata = data.metadata;
        this.currentFrame = 0;

        this.render();
        this.renderControls();
    }

    async loadSharedReplay(shareCode) {
        const response = await fetch(`/api/replay/shared/${shareCode}`);
        if (!response.ok) {
            this.showError("Replay not found or expired");
            return;
        }

        const data = await response.json();
        this.frames = data.replay.frames;
        this.metadata = data.replay;
        this.title = data.title;
        this.currentFrame = 0;

        this.render();
    }

    render() {
        if (!this.frames.length) return;

        const frame = this.frames[this.currentFrame];
        const state = frame.state;

        // Render game board at this state
        this.renderBoard(state);

        // Show event description
        this.renderEventInfo(frame);

        // Update timeline
        this.updateTimeline();
    }

    renderBoard(state) {
        // Similar to main game rendering but read-only
        const boardHtml = `
            <div class="replay-board">
                ${state.players.map(p => this.renderPlayerHand(p)).join('')}
                <div class="replay-center">
                    <div class="deck-area">
                        <div class="card deck-card">
                            <span class="card-back"></span>
                        </div>
                        ${state.discard_top ? this.renderCard(state.discard_top) : ''}
                    </div>
                </div>
            </div>
        `;
        this.container.querySelector('.replay-board-container').innerHTML = boardHtml;
    }

    renderEventInfo(frame) {
        const descriptions = {
            'game_started': 'Game started',
            'card_drawn': `${frame.event.data.player} drew a card`,
            'card_discarded': `${frame.event.data.player} discarded`,
            'card_swapped': `${frame.event.data.player} swapped a card`,
            'turn_ended': `${frame.event.data.player}'s turn ended`,
            'round_ended': 'Round ended',
            'game_ended': `Game over! ${this.metadata.winner} wins!`
        };

        const desc = descriptions[frame.event_type] || frame.event_type;
        this.container.querySelector('.event-description').textContent = desc;
    }

    renderControls() {
        const controls = `
            <div class="replay-controls">
                <button class="btn-start" title="Go to start">⏮</button>
                <button class="btn-prev" title="Previous">⏪</button>
                <button class="btn-play" title="Play/Pause">▶</button>
                <button class="btn-next" title="Next">⏩</button>
                <button class="btn-end" title="Go to end">⏭</button>

                <div class="timeline">
                    <input type="range" min="0" max="${this.frames.length - 1}"
                           value="0" class="timeline-slider">
                    <span class="frame-counter">1 / ${this.frames.length}</span>
                </div>

                <div class="speed-control">
                    <label>Speed:</label>
                    <select class="speed-select">
                        <option value="0.5">0.5x</option>
                        <option value="1" selected>1x</option>
                        <option value="2">2x</option>
                        <option value="4">4x</option>
                    </select>
                </div>
            </div>
        `;
        this.container.querySelector('.controls-container').innerHTML = controls;
        this.bindControlEvents();
    }

    bindControlEvents() {
        this.container.querySelector('.btn-start').onclick = () => this.goToFrame(0);
        this.container.querySelector('.btn-end').onclick = () => this.goToFrame(this.frames.length - 1);
        this.container.querySelector('.btn-prev').onclick = () => this.prevFrame();
        this.container.querySelector('.btn-next').onclick = () => this.nextFrame();
        this.container.querySelector('.btn-play').onclick = () => this.togglePlay();

        this.container.querySelector('.timeline-slider').oninput = (e) => {
            this.goToFrame(parseInt(e.target.value));
        };

        this.container.querySelector('.speed-select').onchange = (e) => {
            this.playbackSpeed = parseFloat(e.target.value);
            if (this.isPlaying) {
                this.stopPlayback();
                this.startPlayback();
            }
        };
    }

    goToFrame(index) {
        this.currentFrame = Math.max(0, Math.min(index, this.frames.length - 1));
        this.render();
    }

    nextFrame() {
        if (this.currentFrame < this.frames.length - 1) {
            this.currentFrame++;
            this.render();
        } else if (this.isPlaying) {
            this.togglePlay();  // Stop at end
        }
    }

    prevFrame() {
        if (this.currentFrame > 0) {
            this.currentFrame--;
            this.render();
        }
    }

    togglePlay() {
        this.isPlaying = !this.isPlaying;
        const btn = this.container.querySelector('.btn-play');

        if (this.isPlaying) {
            btn.textContent = '⏸';
            this.startPlayback();
        } else {
            btn.textContent = '▶';
            this.stopPlayback();
        }
    }

    startPlayback() {
        const baseInterval = 1000;  // 1 second between frames
        this.playInterval = setInterval(() => {
            this.nextFrame();
        }, baseInterval / this.playbackSpeed);
    }

    stopPlayback() {
        if (this.playInterval) {
            clearInterval(this.playInterval);
            this.playInterval = null;
        }
    }

    updateTimeline() {
        const slider = this.container.querySelector('.timeline-slider');
        const counter = this.container.querySelector('.frame-counter');

        if (slider) slider.value = this.currentFrame;
        if (counter) counter.textContent = `${this.currentFrame + 1} / ${this.frames.length}`;
    }
}
```

### Replay Page HTML

```html
<!-- client/replay.html or section in index.html -->
<div id="replay-view" class="view hidden">
    <header class="replay-header">
        <h2 class="replay-title">Game Replay</h2>
        <div class="replay-meta">
            <span class="player-names"></span>
            <span class="game-duration"></span>
        </div>
    </header>

    <div class="replay-board-container">
        <!-- Board renders here -->
    </div>

    <div class="event-description"></div>

    <div class="controls-container">
        <!-- Controls render here -->
    </div>

    <div class="replay-actions">
        <button class="btn-share">Share Replay</button>
        <button class="btn-export">Export JSON</button>
        <button class="btn-back">Back to Menu</button>
    </div>
</div>
```

### Replay Styles

```css
/* client/style.css additions */
.replay-controls {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: var(--surface-color);
    border-radius: 8px;
    flex-wrap: wrap;
    justify-content: center;
}

.replay-controls button {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: none;
    background: var(--primary-color);
    color: white;
    cursor: pointer;
    font-size: 1.2rem;
}

.replay-controls button:hover {
    background: var(--primary-dark);
}

.timeline {
    flex: 1;
    min-width: 200px;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.timeline-slider {
    flex: 1;
    height: 8px;
    -webkit-appearance: none;
    background: var(--border-color);
    border-radius: 4px;
}

.timeline-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    background: var(--primary-color);
    border-radius: 50%;
    cursor: pointer;
}

.frame-counter {
    font-family: monospace;
    min-width: 80px;
    text-align: right;
}

.event-description {
    text-align: center;
    padding: 1rem;
    font-size: 1.1rem;
    color: var(--text-secondary);
    min-height: 3rem;
}

.speed-control {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.speed-select {
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
}

/* Spectator badge */
.spectator-count {
    position: absolute;
    top: 10px;
    right: 10px;
    background: rgba(0,0,0,0.7);
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 20px;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.spectator-count::before {
    content: '👁';
}
```

---

## 6. Share Dialog

```javascript
// Share modal component
class ShareDialog {
    constructor(gameId) {
        this.gameId = gameId;
    }

    async show() {
        const modal = document.createElement('div');
        modal.className = 'modal share-modal';
        modal.innerHTML = `
            <div class="modal-content">
                <h3>Share This Game</h3>

                <div class="share-options">
                    <label>
                        <span>Title (optional):</span>
                        <input type="text" id="share-title" placeholder="Epic comeback win!">
                    </label>

                    <label>
                        <span>Expires in:</span>
                        <select id="share-expiry">
                            <option value="">Never</option>
                            <option value="7">7 days</option>
                            <option value="30">30 days</option>
                            <option value="90">90 days</option>
                        </select>
                    </label>
                </div>

                <div class="share-result hidden">
                    <p>Share this link:</p>
                    <div class="share-link-container">
                        <input type="text" id="share-link" readonly>
                        <button class="btn-copy">Copy</button>
                    </div>
                </div>

                <div class="modal-actions">
                    <button class="btn-generate">Generate Link</button>
                    <button class="btn-cancel">Cancel</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        this.bindEvents(modal);
    }

    async generateLink(modal) {
        const title = modal.querySelector('#share-title').value || null;
        const expiry = modal.querySelector('#share-expiry').value || null;

        const response = await fetch(`/api/replay/game/${this.gameId}/share`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title,
                expires_days: expiry ? parseInt(expiry) : null
            })
        });

        const data = await response.json();
        const fullUrl = `${window.location.origin}${data.share_url}`;

        modal.querySelector('#share-link').value = fullUrl;
        modal.querySelector('.share-result').classList.remove('hidden');
        modal.querySelector('.btn-generate').classList.add('hidden');
    }
}
```

---

## 7. Integration Points

### Game End Integration

```python
# In main.py after game ends
async def on_game_end(game: Game):
    # Store final game state
    await event_store.append(GameEvent(
        game_id=game.id,
        event_type="game_ended",
        data={
            "winner": game.winner.id,
            "final_scores": {p.id: p.score for p in game.players},
            "duration": game.duration_seconds
        }
    ))

    # Notify spectators
    await spectator_manager.broadcast_to_spectators(game.id, {
        "type": "game_ended",
        "winner": game.winner.name,
        "final_scores": {p.name: p.score for p in game.players}
    })
```

### Navigation Links

```javascript
// Add to game history/profile
function renderGameHistory(games) {
    return games.map(game => `
        <div class="history-item">
            <span class="game-date">${formatDate(game.played_at)}</span>
            <span class="game-result">${game.won ? 'Won' : 'Lost'}</span>
            <span class="game-score">${game.score} pts</span>
            <a href="/replay/${game.id}" class="btn-replay">Watch Replay</a>
        </div>
    `).join('');
}
```

---

## 8. Validation Tests

```python
# tests/test_replay.py

async def test_build_replay():
    """Verify replay correctly reconstructs game states."""
    # Create game with known moves
    game_id = await create_test_game()

    replay = await replay_service.build_replay(game_id)

    assert len(replay.frames) > 0
    assert replay.game_id == game_id
    assert replay.winner is not None

    # Verify each frame has valid state
    for frame in replay.frames:
        assert frame.game_state is not None
        assert 'players' in frame.game_state

async def test_share_link_creation():
    """Test creating and accessing share links."""
    game_id = await create_completed_game()
    user_id = "test-user"

    share_code = await replay_service.create_share_link(game_id, user_id)

    assert len(share_code) == 12

    # Retrieve via share code
    shared = await replay_service.get_shared_game(share_code)
    assert shared is not None
    assert shared["game_id"] == game_id

async def test_share_link_expiry():
    """Verify expired links return None."""
    game_id = await create_completed_game()

    # Create link that expires in -1 days (already expired)
    share_code = await create_expired_share(game_id)

    shared = await replay_service.get_shared_game(share_code)
    assert shared is None

async def test_export_import_roundtrip():
    """Test game can be exported and reimported."""
    original_game_id = await create_completed_game()

    export_data = await replay_service.export_game(original_game_id)

    assert export_data["version"] == "1.0"
    assert len(export_data["events"]) > 0

    # Import as new game
    new_game_id = await replay_service.import_game(export_data, "importer-user")

    # Verify imported game matches
    original_replay = await replay_service.build_replay(original_game_id)
    imported_replay = await replay_service.build_replay(new_game_id)

    assert len(original_replay.frames) == len(imported_replay.frames)
    assert original_replay.final_scores == imported_replay.final_scores

async def test_spectator_connection():
    """Test spectator can join and receive updates."""
    game_id = await create_active_game()

    async with websocket_client(f"/api/replay/spectate/{game_id}") as ws:
        # Should receive initial state
        msg = await ws.receive_json()
        assert msg["type"] == "spectator_joined"
        assert "game" in msg

        # Simulate game event
        await trigger_game_event(game_id)

        # Should receive update
        update = await ws.receive_json()
        assert update["type"] == "game_update"
```

---

## 9. Security Considerations

1. **Access Control**: Users can only view replays of games they played in, unless shared
2. **Rate Limiting**: Limit share link creation to prevent abuse
3. **Expired Links**: Clean up expired share links via background job
4. **Import Validation**: Validate imported JSON structure to prevent injection
5. **Spectator Limits**: Cap spectators per game to prevent resource exhaustion

---

## Summary

This document provides a complete replay and export system that:
- Leverages event sourcing for perfect game reconstruction
- Supports shareable links with optional expiry
- Enables live spectating of games in progress
- Allows game export/import for portability
- Includes frontend replay viewer with playback controls
