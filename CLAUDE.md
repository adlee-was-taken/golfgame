# Golf Card Game - Project Context

A real-time multiplayer 6-card Golf card game with CPU opponents and smooth anime.js animations.

## Quick Start

```bash
# Install dependencies
pip install -r server/requirements.txt

# Run the server
python server/main.py

# Visit http://localhost:8000
```

For full installation (Docker, PostgreSQL, Redis, production), see [INSTALL.md](INSTALL.md).

## Architecture

```
golfgame/
├── server/                        # Python FastAPI backend
│   ├── main.py                    # HTTP routes, WebSocket server, lifespan
│   ├── game.py                    # Core game logic, state machine
│   ├── ai.py                      # CPU opponent AI with timing/personality
│   ├── handlers.py                # WebSocket message handlers
│   ├── room.py                    # Room/lobby management
│   ├── config.py                  # Environment configuration (pydantic)
│   ├── constants.py               # Card values, game constants
│   ├── auth.py                    # Authentication (JWT, passwords)
│   ├── logging_config.py          # Structured logging setup
│   ├── simulate.py                # AI simulation runner with stats
│   ├── game_analyzer.py           # Query tools for game analysis
│   ├── score_analysis.py          # Score distribution analysis
│   ├── routers/                   # FastAPI route modules
│   │   ├── auth.py                # Login, signup, verify endpoints
│   │   ├── admin.py               # Admin management endpoints
│   │   ├── stats.py               # Statistics & leaderboard endpoints
│   │   ├── replay.py              # Game replay endpoints
│   │   └── health.py              # Health check endpoints
│   ├── services/                  # Business logic layer
│   │   ├── auth_service.py        # User authentication
│   │   ├── admin_service.py       # Admin tools
│   │   ├── stats_service.py       # Player statistics & leaderboards
│   │   ├── replay_service.py      # Game replay functionality
│   │   ├── game_logger.py         # PostgreSQL game move logging
│   │   ├── spectator.py           # Spectator mode
│   │   ├── email_service.py       # Email notifications (Resend)
│   │   ├── recovery_service.py    # Account recovery
│   │   └── ratelimit.py           # Rate limiting
│   ├── stores/                    # Data persistence layer
│   │   ├── event_store.py         # PostgreSQL event sourcing
│   │   ├── user_store.py          # User persistence
│   │   ├── state_cache.py         # Redis state caching
│   │   └── pubsub.py              # Pub/sub messaging
│   ├── models/                    # Data models
│   │   ├── events.py              # Event types for event sourcing
│   │   ├── game_state.py          # Game state representation
│   │   └── user.py                # User data model
│   └── middleware/                 # Request middleware
│       ├── security.py            # CORS, CSP, security headers
│       ├── request_id.py          # Request ID tracking
│       └── ratelimit.py           # Rate limiting middleware
│
├── client/                        # Vanilla JS frontend
│   ├── index.html                 # Main game page
│   ├── app.js                     # Main game controller
│   ├── card-animations.js         # Unified anime.js animation system
│   ├── card-manager.js            # DOM management for cards
│   ├── animation-queue.js         # Animation sequencing
│   ├── timing-config.js           # Centralized timing configuration
│   ├── state-differ.js            # Diff game state for animations
│   ├── style.css                  # Styles (NO card transitions)
│   ├── admin.html                 # Admin panel
│   ├── admin.js                   # Admin panel interface
│   ├── admin.css                  # Admin panel styles
│   ├── replay.js                  # Game replay viewer
│   ├── leaderboard.js             # Leaderboard display
│   └── ANIMATIONS.md              # Animation system documentation
│
├── docs/
│   ├── ANIMATION-FLOWS.md         # Animation flow diagrams
│   ├── v2/                        # V2 architecture docs (event sourcing, auth, etc.)
│   └── v3/                        # V3 feature & refactoring docs
│
├── scripts/                       # Helper scripts
│   ├── install.sh                 # Interactive installer
│   ├── dev-server.sh              # Development server launcher
│   └── docker-build.sh            # Docker image builder
│
└── tests/e2e/                     # End-to-end tests (Playwright)
```

## Key Technical Decisions

### Animation System

**When to use anime.js vs CSS:**
- **Anime.js (CardAnimations)**: Card movements, flips, swaps, draws - anything involving card elements
- **CSS keyframes/transitions**: Simple UI feedback (button hover, badge entrance, status message fades) - non-card elements

**General rule:** If it moves a card, use anime.js. If it's UI chrome, CSS is fine.

- See `client/ANIMATIONS.md` for full documentation
- See `docs/ANIMATION-FLOWS.md` for flow diagrams
- `CardAnimations` class in `card-animations.js` handles everything
- Timing configured in `timing-config.js`

### State Management

- Server is source of truth
- Client receives full game state on each update
- `state-differ.js` computes diffs to trigger appropriate animations

### Animation Race Condition Flags

Several flags in `app.js` prevent `renderGame()` from updating the discard pile during animations:

| Flag | Purpose |
|------|---------|
| `isDrawAnimating` | Local or opponent draw animation in progress |
| `localDiscardAnimating` | Local player discarding drawn card |
| `opponentDiscardAnimating` | Opponent discarding without swap |
| `opponentSwapAnimation` | Opponent swap animation in progress |
| `dealAnimationInProgress` | Deal animation running (suppresses flip prompts) |

**Critical:** These flags must be cleared in ALL code paths (success, error, fallback). Failure to clear causes UI to freeze.

**Clear flags when:**
- Animation completes (callback)
- New animation starts (clear stale flags)
- `your_turn` message received (safety clear)
- Error/fallback paths

### CPU Players

- AI logic in `server/ai.py`
- Configurable timing delays for natural feel
- Multiple personality types affect decision-making (pair hunters, aggressive, conservative, etc.)

**AI Decision Safety Checks:**
- Never swap high cards (8+) into unknown positions (expected value ~4.5)
- Unpredictability has value threshold (7) to prevent obviously bad random plays
- Comeback bonus only applies to cards < 8
- Denial logic skips hidden positions for 8+ cards

**Testing AI with simulations:**
```bash
# Run 500 games and check dumb move rate
python server/simulate.py 500

# Detailed single game output
python server/simulate.py 1 --detailed

# Compare rule presets
python server/simulate.py 100 --compare
```

### Server Architecture

- **Routers** (`server/routers/`): FastAPI route modules for auth, admin, stats, replay, health
- **Services** (`server/services/`): Business logic layer (auth, admin, stats, replay, email, rate limiting)
- **Stores** (`server/stores/`): Data persistence (PostgreSQL event store, user store, Redis state cache, pub/sub)
- **Models** (`server/models/`): Data models (events, game state, user)
- **Middleware** (`server/middleware/`): Security headers, request ID tracking, rate limiting
- **Handlers** (`server/handlers.py`): WebSocket message dispatch (extracted from main.py)

## Common Development Tasks

### Adjusting Animation Speed

Edit `timing-config.js` - all timings are centralized there.

### Adding New Animations

1. Add method to `CardAnimations` class in `card-animations.js`
2. Use anime.js, not CSS transitions
3. Track in `activeAnimations` Map for cancellation support
4. Add timing config to `timing-config.js` if needed

### Debugging Animations

```javascript
// Check what's animating
console.log(window.cardAnimations.activeAnimations);

// Force cleanup
window.cardAnimations.cancelAll();

// Check timing config
console.log(window.TIMING);
```

### Testing CPU Behavior

Adjust delays in `server/ai.py` `CPU_TIMING` dict.

### Running Tests

```bash
# All server tests
cd server && pytest -v

# AI simulation
python server/simulate.py 500
```

## Important Patterns

### No CSS Transitions on Cards

Cards animate via anime.js only. The following should NOT have `transition` (especially on `transform`):
- `.card`, `.card-inner`
- `.real-card`, `.swap-card`
- `.held-card-floating`

Card hover effects are handled by `CardAnimations.hoverIn()/hoverOut()` methods.
CSS may still use box-shadow transitions for hover glow effects.

### State Differ Logic (triggerAnimationsForStateChange)

The state differ in `app.js` detects what changed between game states:

**STEP 1: Draw Detection**
- Detects when `drawn_card` goes from null to something
- Triggers draw animation (from deck or discard)
- Sets `isDrawAnimating` flag

**STEP 2: Discard/Swap Detection**
- Detects when `discard_top` changes and it was another player's turn
- Triggers swap or discard animation
- **Important:** Skip STEP 2 if STEP 1 detected a draw from discard (the discard change was from REMOVING a card, not adding one)

### Animation Overlays

Complex animations create temporary overlay elements:
1. Create `.draw-anim-card` positioned over source
2. Hide original card (or set `opacity: 0` on discard pile during draw-from-discard)
3. Animate overlay
4. Remove overlay, reveal updated card, restore visibility

### Fire-and-Forget for Opponents

Opponent animations don't block - no callbacks needed:
```javascript
cardAnimations.animateOpponentFlip(cardElement, cardData);
```

### Common Animation Pitfalls

**Card position before append:** Always set `left`/`top` styles BEFORE appending overlay cards to body, otherwise they flash at (0,0).

**Deal animation source:** Use `getDeckRect()` for deal animations, not `getDealerRect()`. The dealer rect returns the whole player area, causing cards to animate at wrong size.

**Element rects during hidden:** `visibility: hidden` still allows `getBoundingClientRect()` to work. `display: none` does not.

## Dependencies

### Server
- FastAPI + uvicorn (web framework & ASGI server)
- websockets (WebSocket support)
- asyncpg (PostgreSQL async driver)
- redis (state caching, pub/sub)
- bcrypt (password hashing)
- resend (email service)
- python-dotenv (environment management)
- sentry-sdk (error tracking, optional)

### Client
- anime.js (animations)
- No other frameworks

### Infrastructure
- PostgreSQL (event sourcing, auth, stats, game logs)
- Redis (state caching, pub/sub)

## Game Rules Reference

- 6 cards per player in 2x3 grid
- Lower score wins
- Matching columns cancel out (0 points)
- Jokers are -2 points
- Kings are 0 points
- Game ends when a player flips all cards
