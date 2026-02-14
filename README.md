# Golf Card Game

A real-time multiplayer 6-card Golf card game with AI opponents, smooth anime.js animations, and extensive house rules support.

## Features

- **Real-time Multiplayer:** 2-6 players via WebSocket
- **AI Opponents:** 8 unique CPU personalities with distinct play styles
- **House Rules:** 15+ optional rule variants
- **Smooth Animations:** Anime.js-powered card dealing, drawing, swapping, and flipping
- **User Accounts:** Registration, login, email verification
- **Stats & Leaderboards:** Player statistics, win rates, and rankings
- **Game Replay:** Review completed games with full playback
- **Admin Tools:** User management, game moderation, system monitoring
- **Event Sourcing:** Full game history stored for replay and analysis
- **Production Ready:** Docker, systemd, nginx, rate limiting, Sentry integration

## Quick Start

```bash
# Install dependencies
pip install -r server/requirements.txt

# Run the server
python server/main.py

# Visit http://localhost:8000
```

For full installation instructions (Docker, production deployment, etc.), see [INSTALL.md](INSTALL.md).

## How to Play

**6-Card Golf** is a card game where you try to get the **lowest score** across multiple rounds (holes).

- Each player has 6 cards in a 2x3 grid (most start face-down)
- On your turn: **draw** a card, then **swap** it with one of yours or **discard** it
- **Column pairs** (same rank top & bottom) score **0 points** — very powerful!
- When any player reveals all 6 cards, everyone else gets one final turn
- Lowest total score after all rounds wins

**For detailed rules, card values, and house rule explanations, see the in-game Rules page or [server/RULES.md](server/RULES.md).**

## AI Personalities

| Name | Style | Description |
|------|-------|-------------|
| Sofia | Calculated & Patient | Conservative, low risk |
| Maya | Aggressive Closer | Goes out early |
| Priya | Pair Hunter | Holds cards hoping for pairs |
| Marcus | Steady Eddie | Balanced, consistent |
| Kenji | Risk Taker | High variance plays |
| Diego | Chaotic Gambler | Unpredictable |
| River | Adaptive Strategist | Adjusts to game state |
| Sage | Sneaky Finisher | Aggressive end-game |

## House Rules

The game supports 15+ optional house rules including:

- **Flip Modes** - Standard, Speed Golf (must flip after discard), Suspense (optional flip near endgame)
- **Point Modifiers** - Super Kings (-2), Ten Penny (10=1), Lucky Swing Joker (-5)
- **Bonuses & Penalties** - Knock bonus/penalty, Underdog bonus, Tied Shame, Blackjack (21->0)
- **Joker Variants** - Standard, Eagle Eye (paired Jokers = -8)

See the in-game Rules page or [server/RULES.md](server/RULES.md) for complete explanations.

## Development

### Project Structure

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
│   ├── simulate.py                # AI-vs-AI simulation runner
│   ├── game_analyzer.py           # Decision analysis CLI
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
│   ├── middleware/                 # Request middleware
│   │   ├── security.py            # CORS, CSP, security headers
│   │   ├── request_id.py          # Request ID tracking
│   │   └── ratelimit.py           # Rate limiting middleware
│   ├── RULES.md                   # Rules documentation
│   └── test_*.py                  # Test files
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
├── scripts/                       # Helper scripts
│   ├── install.sh                 # Interactive installer
│   ├── dev-server.sh              # Development server launcher
│   └── docker-build.sh            # Docker image builder
│
├── docs/                          # Architecture documentation
│   ├── ANIMATION-FLOWS.md         # Animation flow diagrams
│   ├── v2/                        # V2 architecture docs
│   └── v3/                        # V3 feature & refactoring docs
│
├── tests/e2e/                     # End-to-end tests (Playwright)
├── docker-compose.dev.yml         # Dev Docker services (PostgreSQL + Redis)
├── docker-compose.prod.yml        # Production Docker setup
├── Dockerfile                     # Container definition
├── pyproject.toml                 # Python project metadata
├── INSTALL.md                     # Installation & deployment guide
├── CLAUDE.md                      # Project context for AI assistants
└── README.md
```

### Running Tests

```bash
# All server tests
cd server && pytest -v

# Specific test files
pytest test_game.py test_ai_decisions.py test_handlers.py test_room.py -v

# With coverage
pytest --cov=. --cov-report=term-missing
```

### AI Simulation

```bash
# Run 500 games and check dumb move rate
python server/simulate.py 500

# Detailed single game output
python server/simulate.py 1 --detailed

# Compare rule presets
python server/simulate.py 100 --compare

# Analyze AI decisions for blunders
python server/game_analyzer.py blunders

# Score distribution analysis
python server/score_analysis.py 100
```

### AI Performance

From testing (1000+ games):
- **0 blunders** detected in simulation
- **Median score:** 12 points
- **Score range:** -4 to 34 (typical)
- Personalities influence style without compromising competence

## Technology Stack

- **Backend:** Python 3.11+, FastAPI, WebSockets
- **Frontend:** Vanilla HTML/CSS/JavaScript, anime.js (animations)
- **Database:** PostgreSQL (event sourcing, auth, stats, game logs)
- **Cache:** Redis (state caching, pub/sub)
- **Testing:** pytest, Playwright (e2e)
- **Deployment:** Docker, systemd, nginx

## License

MIT
