# V2-08: Unified Game Logging

## Overview

This document covers the unified PostgreSQL game logging system that replaces
the legacy SQLite `game_log.py`. All game events and AI decisions are logged
to PostgreSQL for analysis, replay, and cloud deployment.

**Dependencies:** V2-01 (Event Sourcing), V2-02 (Persistence)
**Dependents:** Game Analyzer, Stats Dashboard

---

## Goals

1. Consolidate all game data in PostgreSQL (drop SQLite dependency)
2. Preserve AI decision context for analysis
3. Maintain compatibility with existing services (Stats, Replay, Recovery)
4. Enable efficient queries for game analysis
5. Support cloud deployment without local file dependencies

---

## Architecture

```
                   ┌─────────────────┐
                   │   Game Server   │
                   │    (main.py)    │
                   └────────┬────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  GameLogger   │  │  EventStore   │  │ StatsService  │
│   Service     │  │   (events)    │  │ ReplayService │
└───────┬───────┘  └───────────────┘  └───────────────┘
        │
        ▼
┌───────────────────────────────────────────────────┐
│                  PostgreSQL                        │
│  ┌─────────┐  ┌───────────┐  ┌──────────────┐    │
│  │ games_v2│  │  events   │  │    moves     │    │
│  │ metadata│  │ (actions) │  │ (AI context) │    │
│  └─────────┘  └───────────┘  └──────────────┘    │
└───────────────────────────────────────────────────┘
```

---

## Database Schema

### moves Table (New)

```sql
CREATE TABLE IF NOT EXISTS moves (
    id BIGSERIAL PRIMARY KEY,
    game_id UUID NOT NULL,
    sequence_num INT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    player_id VARCHAR(50) NOT NULL,
    player_name VARCHAR(100),
    is_cpu BOOLEAN DEFAULT FALSE,

    -- Action details
    action VARCHAR(30) NOT NULL,  -- draw_deck, take_discard, swap, discard, flip, etc.
    card_rank VARCHAR(5),
    card_suit VARCHAR(10),
    position INT,

    -- AI context (JSONB for flexibility)
    hand_state JSONB,           -- Player's hand at decision time
    discard_top JSONB,          -- Top of discard pile
    visible_opponents JSONB,    -- Face-up cards of opponents
    decision_reason TEXT,       -- AI reasoning

    UNIQUE(game_id, sequence_num)
);

CREATE INDEX IF NOT EXISTS idx_moves_game ON moves(game_id);
CREATE INDEX IF NOT EXISTS idx_moves_action ON moves(action);
CREATE INDEX IF NOT EXISTS idx_moves_is_cpu ON moves(is_cpu);
CREATE INDEX IF NOT EXISTS idx_moves_player ON moves(player_id);
```

### Action Types

| Action | Description |
|--------|-------------|
| `draw_deck` | Player drew from deck |
| `take_discard` | Player took top of discard pile |
| `swap` | Player swapped drawn card with hand card |
| `discard` | Player discarded drawn card |
| `flip` | Player flipped a card after discarding |
| `skip_flip` | Player skipped optional flip (endgame) |
| `flip_as_action` | Player used flip-as-action house rule |
| `knock_early` | Player knocked to end round early |

---

## GameLogger Service

**Location:** `/server/services/game_logger.py`

### API

```python
class GameLogger:
    """Logs game events and moves to PostgreSQL."""

    def __init__(self, event_store: EventStore):
        """Initialize with event store instance."""

    def log_game_start(
        self,
        room_code: str,
        num_players: int,
        options: GameOptions,
    ) -> str:
        """Log game start, returns game_id."""

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
    ) -> None:
        """Log a move with AI context."""

    def log_game_end(self, game_id: str) -> None:
        """Mark game as ended."""
```

### Usage

```python
# In main.py lifespan
from services.game_logger import GameLogger, set_logger

_event_store = await get_event_store(config.POSTGRES_URL)
_game_logger = GameLogger(_event_store)
set_logger(_game_logger)

# In handlers
from services.game_logger import get_logger

game_logger = get_logger()
if game_logger:
    game_logger.log_move(
        game_id=room.game_log_id,
        player=player,
        is_cpu=False,
        action="swap",
        card=drawn_card,
        position=position,
        game=room.game,
        decision_reason="swapped 5 into position 2",
    )
```

---

## Query Patterns

### Find Suspicious Discards

```python
# Using EventStore
blunders = await event_store.find_suspicious_discards(limit=50)
```

```sql
-- Direct SQL
SELECT m.*, g.room_code
FROM moves m
JOIN games_v2 g ON m.game_id = g.id
WHERE m.action = 'discard'
AND m.card_rank IN ('A', '2', 'K')
AND m.is_cpu = TRUE
ORDER BY m.timestamp DESC
LIMIT 50;
```

### Get Player Decisions

```python
moves = await event_store.get_player_decisions(game_id, player_name)
```

```sql
SELECT * FROM moves
WHERE game_id = $1 AND player_name = $2
ORDER BY sequence_num;
```

### Recent Games with Stats

```python
games = await event_store.get_recent_games_with_stats(limit=10)
```

```sql
SELECT g.*, COUNT(m.id) as total_moves
FROM games_v2 g
LEFT JOIN moves m ON g.id = m.game_id
GROUP BY g.id
ORDER BY g.created_at DESC
LIMIT 10;
```

---

## Migration from SQLite

### Removed Files

- `/server/game_log.py` - Replaced by `/server/services/game_logger.py`
- `/server/games.db` - Data now in PostgreSQL

### Updated Files

| File | Changes |
|------|---------|
| `main.py` | Import from `services.game_logger`, init in lifespan |
| `ai.py` | Import from `services.game_logger` |
| `simulate.py` | Removed logging, uses in-memory SimulationStats only |
| `game_analyzer.py` | CLI updated for PostgreSQL, class deprecated |
| `stores/event_store.py` | Added `moves` table and query methods |

### Simulation Mode

Simulations (`simulate.py`) no longer write to the database. They use in-memory
`SimulationStats` for analysis. This keeps simulations fast and avoids flooding
the database with bulk test runs.

For simulation analysis:
```bash
python simulate.py 100 --preset baseline
# Stats printed to console
```

For production game analysis:
```bash
python game_analyzer.py blunders 20
python game_analyzer.py recent 10
```

---

## Acceptance Criteria

1. **PostgreSQL Integration**
   - [x] moves table created with proper indexes
   - [x] All game actions logged to PostgreSQL via GameLogger
   - [x] EventStore has append_move() and query methods

2. **Service Compatibility**
   - [x] StatsService still works (uses events table)
   - [x] ReplayService still works (uses events table)
   - [x] RecoveryService still works (uses events table)

3. **Simulation Mode**
   - [x] simulate.py works without PostgreSQL
   - [x] In-memory SimulationStats provides analysis

4. **SQLite Removal**
   - [x] game_log.py can be deleted
   - [x] games.db can be deleted
   - [x] No sqlite3 imports in main game code

---

## Implementation Notes

### Async/Sync Bridging

The GameLogger provides sync methods (`log_move`, `log_game_start`) that
internally fire async tasks. This allows existing sync code paths to call
the logger without blocking:

```python
def log_move(self, game_id, ...):
    if not game_id:
        return
    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(self.log_move_async(...))
    except RuntimeError:
        # Not in async context - skip (simulations)
        pass
```

### Fire-and-Forget Logging

Move logging uses fire-and-forget async tasks to avoid blocking game logic.
This means:
- Logging failures don't crash the game
- Slight delay between action and database write is acceptable
- No acknowledgment that log succeeded

For critical data, use the events table which is the source of truth.

---

## Notes for Developers

- The `moves` table is denormalized for efficient queries
- The `events` table remains the source of truth for game replay
- GameLogger is None when PostgreSQL is not configured (no logging)
- Always check `if game_logger:` before calling methods
- For quick development testing, use simulate.py without database
