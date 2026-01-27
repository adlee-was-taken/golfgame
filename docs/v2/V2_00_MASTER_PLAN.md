# Golf Card Game - V2 Master Plan

## Overview

Transform the current single-server Golf game into a production-ready, hostable platform with:
- **Event-sourced architecture** for full game replay and audit trails
- **User accounts** with authentication, password reset, and profile management
- **Admin tools** for moderation and system management
- **Leaderboards** with player statistics
- **Scalable hosting** options (self-hosted or cloud)
- **Export/playback** for sharing memorable games

---

## Document Structure (VDD)

This plan is split into independent vertical slices. Each document is self-contained and can be worked on by a separate agent.

| Document | Scope | Dependencies |
|----------|-------|--------------|
| `V2_01_EVENT_SOURCING.md` | Event classes, store, state rebuilding | None (foundation) |
| `V2_02_PERSISTENCE.md` | Redis cache, PostgreSQL, game recovery | 01 |
| `V2_03_USER_ACCOUNTS.md` | Registration, login, password reset, email | 02 |
| `V2_04_ADMIN_TOOLS.md` | Admin dashboard, moderation, system stats | 03 |
| `V2_05_STATS_LEADERBOARDS.md` | Stats aggregation, leaderboard API/UI | 03 |
| `V2_06_REPLAY_EXPORT.md` | Game replay, export, share links | 01, 02 |
| `V2_07_PRODUCTION.md` | Docker, deployment, monitoring, security | All |

---

## Current State (V1)

```
Client (Vanilla JS) <──WebSocket──> FastAPI Server <──> SQLite
                                          │
                                    In-memory rooms
                                    (lost on restart)
```

**What works well:**
- Game logic is solid and well-tested
- CPU AI with 8 distinct personalities
- Flexible house rules system (15+ options)
- Real-time multiplayer via WebSockets
- Basic auth system with invite codes

**Limitations:**
- Single server, no horizontal scaling
- Game state lost on server restart
- Move logging exists but duplicates state
- No persistent player stats or leaderboards
- Limited admin capabilities
- No password reset flow
- No email integration

---

## V2 Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                            Clients                                   │
│                   (Browser / Future: Mobile)                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ WebSocket + REST API
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Command  │ │  Event   │ │  State   │ │  Query   │ │   Auth   │  │
│  │ Handler  │─► Store    │─► Builder  │ │ Service  │ │ Service  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                            │
│  │  Admin   │ │  Stats   │ │  Email   │                            │
│  │ Service  │ │ Worker   │ │ Service  │                            │
│  └──────────┘ └──────────┘ └──────────┘                            │
└───────┬───────────────┬───────────────┬───────────────┬────────────┘
        │               │               │               │
        ▼               ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│    Redis     │ │  PostgreSQL  │ │  PostgreSQL  │ │    Email     │
│ (Live State) │ │   (Events)   │ │ (Users/Stats)│ │   Provider   │
│  (Pub/Sub)   │ │              │ │              │ │  (Resend)    │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

---

## Tech Stack

| Layer | Technology | Reasoning |
|-------|------------|-----------|
| **Web framework** | FastAPI (keep) | Already using, async, fast |
| **WebSockets** | Starlette (keep) | Built into FastAPI |
| **Live state cache** | Redis | Fast, pub/sub, TTL, battle-tested |
| **Event store** | PostgreSQL | JSONB, robust, great tooling |
| **User database** | PostgreSQL | Same instance, keep it simple |
| **Background jobs** | `arq` | Async, Redis-backed, lightweight |
| **Email** | Resend | Simple API, good free tier, reliable |
| **Containerization** | Docker | Consistent deployment |
| **Orchestration** | Docker Compose | Start simple, K8s if needed |

### New Dependencies

```txt
# requirements.txt additions
redis>=5.0.0
asyncpg>=0.29.0           # Async PostgreSQL
sqlalchemy>=2.0.0         # ORM for complex queries
alembic>=1.13.0           # Database migrations
arq>=0.26.0               # Background task queue
pydantic-settings>=2.0    # Config management
resend>=0.8.0             # Email service
python-jose[cryptography] # JWT tokens
passlib[bcrypt]           # Password hashing
```

---

## Phases & Milestones

### Phase 1: Event Infrastructure (Foundation)
**Goal:** Emit events alongside current code, validate replay works

| Milestone | Description | Document |
|-----------|-------------|----------|
| Event classes defined | All gameplay events as dataclasses | 01 |
| Event store working | PostgreSQL persistence | 01 |
| Dual-write enabled | Events emitted without breaking current code | 01 |
| Replay validation | Test proves events recreate identical state | 01 |
| Rate limiting on auth | Brute force protection | 07 |

### Phase 2: Persistence & Recovery
**Goal:** Games survive server restarts

| Milestone | Description | Document |
|-----------|-------------|----------|
| Redis state cache | Live game state in Redis | 02 |
| Pub/sub ready | Multi-server WebSocket fan-out | 02 |
| Game recovery | Rebuild games from events on startup | 02 |
| Graceful shutdown | Save state before stopping | 02 |

### Phase 3a: User Accounts
**Goal:** Full user lifecycle management

| Milestone | Description | Document |
|-----------|-------------|----------|
| Email service integrated | Resend configured and tested | 03 |
| Registration with verification | Email confirmation flow | 03 |
| Password reset flow | Forgot password via email token | 03 |
| Session management | View/revoke sessions | 03 |
| Account settings | Profile, preferences, deletion | 03 |

### Phase 3b: Admin Tools
**Goal:** Moderation and system management

| Milestone | Description | Document |
|-----------|-------------|----------|
| Admin dashboard | User list, search, metrics | 04 |
| User management | Ban, unban, force password reset | 04 |
| Game moderation | View any game, end stuck games | 04 |
| System monitoring | Active games, users online, events/hour | 04 |
| Audit logging | Track admin actions | 04 |

### Phase 4: Stats & Leaderboards
**Goal:** Persistent player statistics

| Milestone | Description | Document |
|-----------|-------------|----------|
| Stats schema | PostgreSQL tables for aggregated stats | 05 |
| Stats worker | Background job processing events | 05 |
| Leaderboard API | REST endpoints | 05 |
| Leaderboard UI | Client display | 05 |
| Achievement system | Badges and milestones (stretch) | 05 |

### Phase 5: Replay & Export
**Goal:** Share and replay games

| Milestone | Description | Document |
|-----------|-------------|----------|
| Export API | Download game as JSON | 06 |
| Import/load | Upload and replay | 06 |
| Replay UI | Playback controls, scrubbing | 06 |
| Share links | Public `/replay/{id}` URLs | 06 |

### Phase 6: Production
**Goal:** Deployable, monitored, secure

| Milestone | Description | Document |
|-----------|-------------|----------|
| Dockerized | All services containerized | 07 |
| Health checks | `/health` endpoint with dependency checks | 07 |
| Metrics | Prometheus metrics | 07 |
| Error tracking | Sentry integration | 07 |
| Deployment guide | Step-by-step for VPS/cloud | 07 |

---

## File Structure (Target)

```
golfgame/
├── client/                     # Frontend (enhance incrementally)
│   ├── index.html
│   ├── app.js
│   ├── components/             # New: modular UI components
│   │   ├── leaderboard.js
│   │   ├── replay-controls.js
│   │   └── admin-dashboard.js
│   └── ...
├── server/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Settings from env vars
│   ├── dependencies.py         # FastAPI dependency injection
│   ├── models/
│   │   ├── events.py           # Event dataclasses
│   │   ├── user.py             # User model
│   │   └── game_state.py       # State rebuilt from events
│   ├── stores/
│   │   ├── event_store.py      # PostgreSQL event persistence
│   │   ├── state_cache.py      # Redis live state
│   │   └── user_store.py       # User persistence
│   ├── services/
│   │   ├── game_service.py     # Command handling, event emission
│   │   ├── auth_service.py     # Authentication, sessions
│   │   ├── email_service.py    # Email sending
│   │   ├── admin_service.py    # Admin operations
│   │   ├── stats_service.py    # Leaderboard queries
│   │   └── replay_service.py   # Export, import, playback
│   ├── routers/
│   │   ├── auth.py             # Auth endpoints
│   │   ├── admin.py            # Admin endpoints
│   │   ├── games.py            # Game/replay endpoints
│   │   └── stats.py            # Leaderboard endpoints
│   ├── workers/
│   │   └── stats_worker.py     # Background stats aggregation
│   ├── middleware/
│   │   ├── rate_limit.py       # Rate limiting
│   │   └── auth.py             # Auth middleware
│   ├── ai/                     # Keep existing AI code
│   │   └── ...
│   └── tests/
│       ├── test_events.py
│       ├── test_replay.py
│       ├── test_auth.py
│       └── ...
├── migrations/                  # Alembic migrations
│   ├── versions/
│   └── env.py
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
├── docs/
│   └── v2/                     # These planning documents
│       ├── V2_00_MASTER_PLAN.md
│       ├── V2_01_EVENT_SOURCING.md
│       └── ...
└── scripts/
    ├── migrate.py              # Run migrations
    ├── create_admin.py         # Bootstrap admin user
    └── export_game.py          # CLI game export
```

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Event store DB | PostgreSQL | JSONB support, same DB as users, simpler ops |
| Email provider | Resend | Simple API, good free tier (3k/mo), reliable |
| Background jobs | arq | Async-native, Redis-backed, lightweight |
| Session storage | Redis | Fast, TTL support, already using for state |
| Password hashing | bcrypt | Industry standard, built-in work factor |
| JWT vs sessions | Both | JWT for API, sessions for WebSocket |

---

## Open Questions

1. **Guest play vs required accounts?**
   - Decision: Allow guest play, prompt to register to save stats
   - Guest games count for global stats but not personal leaderboards

2. **Game history retention?**
   - Decision: Keep events forever (they're small, ~500 bytes each)
   - Implement archival to cold storage after 1 year if needed

3. **Replay visibility?**
   - Decision: Private by default, shareable via link
   - Future: Public games opt-in

4. **CPU games count for leaderboards?**
   - Decision: Yes, but separate "vs humans only" leaderboard later

5. **Multi-region?**
   - Decision: Not for V2, single region is fine for card game latency
   - Revisit if user base grows significantly

---

## How to Use These Documents

Each `V2_XX_*.md` document is designed to be:

1. **Self-contained** - Has all context needed to implement that slice
2. **Agent-ready** - Can be given to a Claude agent as the primary context
3. **Testable** - Includes acceptance criteria and test requirements
4. **Incremental** - Can be implemented and shipped independently (respecting dependencies)

**Workflow:**
1. Pick a document based on current phase
2. Start a new Claude session with that document as context
3. Implement the slice
4. Run tests specified in the document
5. PR and merge
6. Move to next slice

---

## Next Steps

1. Review all V2 documents
2. Set up PostgreSQL locally for development
3. Start with `V2_01_EVENT_SOURCING.md`
4. Implement rate limiting from `V2_07_PRODUCTION.md` early (security)
