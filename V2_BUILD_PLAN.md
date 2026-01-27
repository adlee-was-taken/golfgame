# Golf Card Game - V2 Build Plan

## Vision

Transform the current single-server Golf game into a production-ready, hostable platform with:
- **Event-sourced architecture** for full game replay and audit trails
- **Leaderboards** with player statistics
- **Scalable hosting** options (self-hosted or cloud)
- **Export/playback** for sharing memorable games

---

## Current State (V1)

```
Client (Vanilla JS) ◄──WebSocket──► FastAPI Server ◄──► SQLite
                                          │
                                    In-memory rooms
                                    (lost on restart)
```

**What works well:**
- Game logic is solid and well-tested
- CPU AI with multiple personalities
- House rules system is flexible
- Real-time multiplayer via WebSockets

**Limitations:**
- Single server, no horizontal scaling
- Game state lost on server restart
- Move logging exists but duplicates state
- No player accounts with persistent stats

---

## V2 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                            Clients                                   │
│                   (Browser / Future: Mobile)                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ WebSocket + REST API
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │   Command   │  │    Event    │  │    State    │  │   Query    │ │
│  │   Handler   │──►   Store     │──►   Builder   │  │   Service  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │
└───────┬───────────────────┬───────────────────┬───────────────┬─────┘
        │                   │                   │               │
        ▼                   ▼                   ▼               ▼
┌──────────────┐    ┌──────────────┐    ┌─────────────┐  ┌───────────┐
│    Redis     │    │  PostgreSQL  │    │  PostgreSQL │  │  Postgres │
│ (Live State) │    │   (Events)   │    │   (Users)   │  │  (Stats)  │
│ (Pub/Sub)    │    │              │    │             │  │           │
└──────────────┘    └──────────────┘    └─────────────┘  └───────────┘
```

---

## Data Model

### Event Store

All game actions stored as immutable events:

```sql
-- Core event log
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    game_id UUID NOT NULL,
    sequence_num INT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL,
    player_id VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(game_id, sequence_num)
);

-- Game metadata (denormalized for queries)
CREATE TABLE games (
    id UUID PRIMARY KEY,
    room_code VARCHAR(10),
    status VARCHAR(20) DEFAULT 'active',  -- active, completed, abandoned
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    num_players INT,
    num_rounds INT,
    options JSONB,
    winner_id VARCHAR(50),

    -- Denormalized for leaderboard queries
    player_ids VARCHAR(50)[]
);

CREATE INDEX idx_events_game ON events(game_id, sequence_num);
CREATE INDEX idx_games_status ON games(status, completed_at);
CREATE INDEX idx_games_players ON games USING GIN(player_ids);
```

### Event Types

```python
@dataclass
class GameEvent:
    game_id: str
    sequence_num: int
    event_type: str
    player_id: Optional[str]
    timestamp: datetime
    data: dict

# Lifecycle events
GameCreated(room_code, options, host_id)
PlayerJoined(player_id, player_name, is_cpu, profile_name?)
PlayerLeft(player_id, reason)
GameStarted(deck_seed, player_order)
RoundStarted(round_num)
RoundEnded(scores: dict, winner_id)
GameEnded(final_scores: dict, winner_id)

# Gameplay events
InitialCardsFlipped(player_id, positions: list[int])
CardDrawn(player_id, source: "deck"|"discard", card: Card)
CardSwapped(player_id, position: int, new_card: Card, old_card: Card)
CardDiscarded(player_id, card: Card)
CardFlipped(player_id, position: int, card: Card)
FlipSkipped(player_id)
FlipAsAction(player_id, position: int, card: Card)
```

### User & Stats Schema

```sql
-- User accounts (expand existing auth)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    role VARCHAR(20) DEFAULT 'player',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,
    preferences JSONB DEFAULT '{}'
);

-- Player statistics (materialized from events)
CREATE TABLE player_stats (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    games_played INT DEFAULT 0,
    games_won INT DEFAULT 0,
    rounds_played INT DEFAULT 0,
    rounds_won INT DEFAULT 0,
    total_points INT DEFAULT 0,          -- Lower is better
    best_round_score INT,
    worst_round_score INT,
    total_knockouts INT DEFAULT 0,       -- Times going out first
    total_blunders INT DEFAULT 0,        -- From AI analyzer
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Leaderboard views
CREATE VIEW leaderboard_by_wins AS
SELECT
    u.username,
    s.games_played,
    s.games_won,
    ROUND(s.games_won::numeric / NULLIF(s.games_played, 0) * 100, 1) as win_rate,
    s.rounds_won,
    ROUND(s.total_points::numeric / NULLIF(s.rounds_played, 0), 1) as avg_score
FROM player_stats s
JOIN users u ON s.user_id = u.id
WHERE s.games_played >= 25  -- Minimum games for ranking
ORDER BY win_rate DESC, games_won DESC;

CREATE VIEW leaderboard_by_games AS
SELECT
    u.username,
    s.games_played,
    s.games_won,
    s.rounds_won
FROM player_stats s
JOIN users u ON s.user_id = u.id
ORDER BY games_played DESC;
```

---

## Components to Build

### Phase 1: Event Infrastructure (Foundation)

| Component | Description | Effort |
|-----------|-------------|--------|
| Event classes | Python dataclasses for all event types | S |
| Event store | PostgreSQL table + write functions | S |
| State rebuilder | Fold events into GameState | M |
| Dual-write migration | Emit events alongside current mutations | M |
| Event validation | Ensure events can recreate identical state | M |

### Phase 2: Persistence & Recovery

| Component | Description | Effort |
|-----------|-------------|--------|
| Redis state cache | Store live game state in Redis | M |
| Pub/sub for multi-server | Redis pub/sub for WebSocket fan-out | M |
| Game recovery | Rebuild in-progress games from events on restart | S |
| Graceful shutdown | Save state before shutdown | S |

### Phase 3: User System & Stats

| Component | Description | Effort |
|-----------|-------------|--------|
| User registration flow | Proper signup/login UI | M |
| Guest-to-user conversion | Play as guest, register to save stats | S |
| Stats aggregation worker | Process events → update player_stats | M |
| Leaderboard API | REST endpoints for leaderboards | S |
| Leaderboard UI | Display in client | M |

### Phase 4: Replay & Export

| Component | Description | Effort |
|-----------|-------------|--------|
| Export API | `GET /api/games/{id}/export` returns event JSON | S |
| Import/load | Load exported game for replay | S |
| Replay UI | Playback controls, scrubbing, speed control | L |
| Share links | `/replay/{game_id}` public URLs | S |

### Phase 5: Production Hardening

| Component | Description | Effort |
|-----------|-------------|--------|
| Rate limiting | Prevent abuse | S |
| Health checks | `/health` with dependency checks | S |
| Metrics | Prometheus metrics for monitoring | M |
| Error tracking | Sentry or similar | S |
| Backup strategy | Automated PostgreSQL backups | S |

---

## Tech Stack

### Recommended Stack

| Layer | Technology | Reasoning |
|-------|------------|-----------|
| **Web framework** | FastAPI (keep) | Already using, async, fast |
| **WebSockets** | Starlette (keep) | Built into FastAPI |
| **Live state cache** | Redis | Fast, pub/sub, TTL, battle-tested |
| **Event store** | PostgreSQL | JSONB, robust, great tooling |
| **User database** | PostgreSQL | Same instance, keep it simple |
| **Background jobs** | `arq` or `rq` | Stats aggregation, cleanup |
| **Containerization** | Docker | Consistent deployment |
| **Orchestration** | Docker Compose (small) / K8s (large) | Start simple |

### Dependencies to Add

```txt
# requirements.txt additions
redis>=5.0.0
asyncpg>=0.29.0          # Async PostgreSQL
sqlalchemy>=2.0.0        # ORM (optional, can use raw SQL)
alembic>=1.13.0          # Migrations
arq>=0.26.0              # Background tasks
pydantic-settings>=2.0   # Config management
```

---

## Hosting Options

### Option A: Single VPS (Simplest, $5-20/mo)

```
┌─────────────────────────────────────┐
│            VPS (2-4GB RAM)          │
│  ┌─────────┐ ┌─────────┐ ┌───────┐ │
│  │ FastAPI │ │  Redis  │ │Postgres│ │
│  │  :8000  │ │  :6379  │ │ :5432 │ │
│  └─────────┘ └─────────┘ └───────┘ │
│           Docker Compose            │
└─────────────────────────────────────┘

Providers: DigitalOcean, Linode, Hetzner, Vultr
Capacity: ~100-500 concurrent users
```

**docker-compose.yml:**
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://golf:secret@db:5432/golf
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: golf
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: golf
    volumes:
      - postgres_data:/var/lib/postgresql/data

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs

volumes:
  redis_data:
  postgres_data:
```

### Option B: Managed Services ($20-50/mo)

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│   Fly.io     │     │  Upstash Redis  │     │   Neon or    │
│   App        │◄───►│  (Serverless)   │     │  Supabase    │
│   $5-10/mo   │     │  Free-$10/mo    │     │  PostgreSQL  │
└──────────────┘     └─────────────────┘     │  Free-$25/mo │
                                             └──────────────┘

Alternative compute: Railway, Render, Google Cloud Run
```

**Pros:** Less ops, automatic SSL, easy scaling
**Cons:** Slightly higher latency, vendor lock-in

### Option C: Self-Hosted (Home Server / NAS)

```
┌─────────────────────────────────────┐
│  Home Server / Raspberry Pi 5       │
│  Docker Compose (same as Option A)  │
└───────────────────┬─────────────────┘
                    │
┌───────────────────▼─────────────────┐
│  Cloudflare Tunnel (free)           │
│  • No port forwarding needed        │
│  • Free SSL                         │
│  • DDoS protection                  │
└─────────────────────────────────────┘

Domain: golf.yourdomain.com
```

### Option D: Kubernetes (Overkill Unless Scaling Big)

Only if you're expecting 5000+ concurrent users or need multi-region.

---

## Migration Strategy

### Step 1: Add Event Emission (Non-Breaking)

Keep current code working, add event logging in parallel:

```python
# In game.py or main.py
def draw_card(self, player_id: str, source: str) -> Optional[Card]:
    # Existing logic
    card = self._do_draw(player_id, source)

    if card:
        # NEW: Emit event (doesn't affect gameplay)
        self.emit_event(CardDrawn(
            player_id=player_id,
            source=source,
            card=card.to_dict()
        ))

    return card
```

### Step 2: Validate Event Replay

Build a test that:
1. Plays a game normally
2. Captures all events
3. Replays events into fresh state
4. Asserts final state matches

```python
def test_event_replay_matches():
    # Play a game, collect events
    game, events = play_test_game()
    final_state = game.get_state()

    # Rebuild from events
    rebuilt = GameState()
    for event in events:
        rebuilt.apply(event)

    assert rebuilt == final_state
```

### Step 3: Switch to Event-Sourced

Once validation passes:
1. Commands produce events
2. Events applied to state
3. State derived, not mutated directly

### Step 4: Deploy New Infrastructure

1. Set up PostgreSQL + Redis
2. Deploy with feature flag (old vs new storage)
3. Run both in parallel, compare
4. Cut over when confident

---

## Milestones & Timeline

| Phase | Milestone | Dependencies |
|-------|-----------|--------------|
| **1** | Events emitting alongside current code | None |
| **1** | Event replay test passing | Events emitting |
| **2** | Redis state cache working | None |
| **2** | Server survives restart (games recover) | Events + Redis |
| **3** | User accounts with persistent stats | PostgreSQL |
| **3** | Leaderboards displaying | Stats aggregation |
| **4** | Export API working | Events stored |
| **4** | Replay UI functional | Export API |
| **5** | Dockerized deployment | All above |
| **5** | Production deployment | Docker + hosting |

---

## Open Questions

1. **Guest play vs required accounts?**
   - Recommendation: Allow guest play, prompt to register to save stats

2. **Game history retention?**
   - Keep all events forever? Or archive after 90 days?
   - Events are small (~500 bytes each), storage is cheap

3. **Replay visibility?**
   - All games public? Only if shared? Privacy setting per game?

4. **CPU games count for leaderboards?**
   - Recommendation: Yes, but flag them. Separate "vs humans" stats later.

5. **i18n approach?**
   - Client-side translation files (JSON)
   - Server messages are mostly game state, not text

---

## Appendix: File Structure (Proposed)

```
golfgame/
├── client/                    # Frontend (keep as-is for now)
│   ├── index.html
│   ├── app.js
│   └── ...
├── server/
│   ├── main.py               # FastAPI app, WebSocket handlers
│   ├── config.py             # Settings (env vars)
│   ├── models/
│   │   ├── events.py         # Event dataclasses
│   │   ├── game_state.py     # State rebuilt from events
│   │   └── user.py           # User model
│   ├── stores/
│   │   ├── event_store.py    # PostgreSQL event persistence
│   │   ├── state_cache.py    # Redis live state
│   │   └── user_store.py     # User/auth persistence
│   ├── services/
│   │   ├── game_service.py   # Command handling, event emission
│   │   ├── replay_service.py # Export, import, playback
│   │   ├── stats_service.py  # Leaderboard queries
│   │   └── auth_service.py   # Authentication
│   ├── workers/
│   │   └── stats_worker.py   # Background stats aggregation
│   ├── ai/
│   │   ├── profiles.py       # CPU personalities
│   │   └── decisions.py      # AI logic
│   └── tests/
│       ├── test_events.py
│       ├── test_replay.py
│       └── ...
├── migrations/                # Alembic migrations
├── docker-compose.yml
├── Dockerfile
└── V2_BUILD_PLAN.md          # This file
```

---

## Next Steps

1. **Review this plan** - Any adjustments to scope or priorities?
2. **Set up PostgreSQL locally** - For development
3. **Define event classes** - Start with Phase 1
4. **Add event emission** - Non-breaking change to current code

Ready to start building when you are.
