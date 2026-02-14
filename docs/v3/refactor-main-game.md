# Plan 1: main.py & game.py Refactor

## Overview

Break apart the 575-line WebSocket handler in `main.py` into discrete message handlers, eliminate repeated patterns (logging, locking, error responses), and clean up `game.py`'s scattered house rule display logic and options boilerplate.

No backwards-compatibility concerns - no existing userbase.

---

## Part A: main.py WebSocket Handler Decomposition

### A1. Create `server/handlers.py` - Message Handler Registry

Extract each `elif msg_type == "..."` block from `websocket_endpoint()` into standalone async handler functions. One function per message type:

```python
# server/handlers.py

async def handle_create_room(ws, data, ctx) -> None: ...
async def handle_join_room(ws, data, ctx) -> None: ...
async def handle_get_cpu_profiles(ws, data, ctx) -> None: ...
async def handle_add_cpu(ws, data, ctx) -> None: ...
async def handle_remove_cpu(ws, data, ctx) -> None: ...
async def handle_start_game(ws, data, ctx) -> None: ...
async def handle_flip_initial(ws, data, ctx) -> None: ...
async def handle_draw(ws, data, ctx) -> None: ...
async def handle_swap(ws, data, ctx) -> None: ...
async def handle_discard(ws, data, ctx) -> None: ...
async def handle_cancel_draw(ws, data, ctx) -> None: ...
async def handle_flip_card(ws, data, ctx) -> None: ...
async def handle_skip_flip(ws, data, ctx) -> None: ...
async def handle_flip_as_action(ws, data, ctx) -> None: ...
async def handle_knock_early(ws, data, ctx) -> None: ...
async def handle_next_round(ws, data, ctx) -> None: ...
async def handle_leave_room(ws, data, ctx) -> None: ...
async def handle_leave_game(ws, data, ctx) -> None: ...
async def handle_end_game(ws, data, ctx) -> None: ...
```

**Context object** passed to every handler:
```python
@dataclass
class ConnectionContext:
    websocket: WebSocket
    connection_id: str
    player_id: str
    auth_user_id: Optional[str]
    authenticated_user: Optional[User]
    current_room: Optional[Room]  # mutable reference
```

**Handler dispatch** in `websocket_endpoint()` becomes:
```python
HANDLERS = {
    "create_room": handle_create_room,
    "join_room": handle_join_room,
    # ... etc
}

while True:
    data = await websocket.receive_json()
    handler = HANDLERS.get(data.get("type"))
    if handler:
        await handler(data, ctx)
```

This takes `websocket_endpoint()` from ~575 lines to ~30 lines.

### A2. Extract Game Action Logger Helper

The pattern repeated 8 times across draw/swap/discard/flip/skip_flip/flip_as_action/knock_early:

```python
game_logger = get_logger()
if game_logger and current_room.game_log_id and player:
    game_logger.log_move(
        game_id=current_room.game_log_id,
        player=player,
        is_cpu=False,
        action="...",
        card=...,
        position=...,
        game=current_room.game,
        decision_reason="...",
    )
```

Extract to:
```python
# In handlers.py or a small helpers module
def log_human_action(room, player, action, card=None, position=None, reason=""):
    game_logger = get_logger()
    if game_logger and room.game_log_id and player:
        game_logger.log_move(
            game_id=room.game_log_id,
            player=player,
            is_cpu=False,
            action=action,
            card=card,
            position=position,
            game=room.game,
            decision_reason=reason,
        )
```

Each handler call site becomes a single line.

### A3. Replace Static File Routes with `StaticFiles` Mount

Currently 15+ hand-written `@app.get()` routes for static files (lines 1188-1255). Replace with:

```python
from fastapi.staticfiles import StaticFiles

# Serve specific HTML routes first
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(client_path, "index.html"))

@app.get("/admin")
async def serve_admin():
    return FileResponse(os.path.join(client_path, "admin.html"))

@app.get("/replay/{share_code}")
async def serve_replay_page(share_code: str):
    return FileResponse(os.path.join(client_path, "index.html"))

# Mount static files for everything else (JS, CSS, SVG, etc.)
app.mount("/", StaticFiles(directory=client_path), name="static")
```

Eliminates ~70 lines and auto-handles any new client files without code changes.

### A4. Clean Up Lifespan Service Init

The lifespan function (lines 83-242) has a deeply nested try/except block initializing ~8 services with lots of `set_*` calls. Simplify by extracting service init:

```python
async def _init_database_services():
    """Initialize all PostgreSQL-dependent services. Returns dict of services."""
    # All the import/init/set logic currently in lifespan
    ...

async def _init_redis(redis_url):
    """Initialize Redis client and rate limiter."""
    ...

@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.REDIS_URL:
        await _init_redis(config.REDIS_URL)
    if config.POSTGRES_URL:
        await _init_database_services()

    # health check setup
    ...
    yield
    # shutdown...
```

---

## Part B: game.py Cleanup

### B1. Data-Driven Active Rules Display

Replace the 38-line if-chain in `get_state()` (lines 1546-1584) with a declarative approach:

```python
# On GameOptions class or as module-level constant
_RULE_DISPLAY = [
    # (attribute, display_name, condition_fn_or_None)
    ("knock_penalty", "Knock Penalty", None),
    ("lucky_swing", "Lucky Swing", None),
    ("eagle_eye", "Eagle-Eye", None),
    ("super_kings", "Super Kings", None),
    ("ten_penny", "Ten Penny", None),
    ("knock_bonus", "Knock Bonus", None),
    ("underdog_bonus", "Underdog", None),
    ("tied_shame", "Tied Shame", None),
    ("blackjack", "Blackjack", None),
    ("wolfpack", "Wolfpack", None),
    ("flip_as_action", "Flip as Action", None),
    ("four_of_a_kind", "Four of a Kind", None),
    ("negative_pairs_keep_value", "Negative Pairs Keep Value", None),
    ("one_eyed_jacks", "One-Eyed Jacks", None),
    ("knock_early", "Early Knock", None),
]

def get_active_rules(self) -> list[str]:
    rules = []
    # Special: flip mode
    if self.options.flip_mode == FlipMode.ALWAYS.value:
        rules.append("Speed Golf")
    elif self.options.flip_mode == FlipMode.ENDGAME.value:
        rules.append("Endgame Flip")
    # Special: jokers (only if not overridden by lucky_swing/eagle_eye)
    if self.options.use_jokers and not self.options.lucky_swing and not self.options.eagle_eye:
        rules.append("Jokers")
    # Boolean rules
    for attr, display_name, _ in _RULE_DISPLAY:
        if getattr(self.options, attr):
            rules.append(display_name)
    return rules
```

### B2. Simplify `_options_to_dict()`

Replace the 22-line manual dict construction (lines 791-813) with `dataclasses.asdict()` or a simple comprehension:

```python
from dataclasses import asdict

def _options_to_dict(self) -> dict:
    return asdict(self.options)
```

Or if we want to exclude `deck_colors` or similar:
```python
def _options_to_dict(self) -> dict:
    return {k: v for k, v in asdict(self.options).items()}
```

### B3. Add `GameOptions.to_start_game_dict()` for main.py

The `start_game` handler in main.py (lines 663-689) manually maps 17 `data.get()` calls to `GameOptions()`. Add a classmethod:

```python
@classmethod
def from_client_data(cls, data: dict) -> "GameOptions":
    """Build GameOptions from client WebSocket message data."""
    return cls(
        flip_mode=data.get("flip_mode", "never"),
        initial_flips=max(0, min(2, data.get("initial_flips", 2))),
        knock_penalty=data.get("knock_penalty", False),
        use_jokers=data.get("use_jokers", False),
        lucky_swing=data.get("lucky_swing", False),
        super_kings=data.get("super_kings", False),
        ten_penny=data.get("ten_penny", False),
        knock_bonus=data.get("knock_bonus", False),
        underdog_bonus=data.get("underdog_bonus", False),
        tied_shame=data.get("tied_shame", False),
        blackjack=data.get("blackjack", False),
        eagle_eye=data.get("eagle_eye", False),
        wolfpack=data.get("wolfpack", False),
        flip_as_action=data.get("flip_as_action", False),
        four_of_a_kind=data.get("four_of_a_kind", False),
        negative_pairs_keep_value=data.get("negative_pairs_keep_value", False),
        one_eyed_jacks=data.get("one_eyed_jacks", False),
        knock_early=data.get("knock_early", False),
        deck_colors=data.get("deck_colors", ["red", "blue", "gold"]),
    )
```

This keeps the construction logic on the class that owns it and out of the WebSocket handler.

---

## Execution Order

1. **B2, B3** (game.py small wins) - low risk, immediate cleanup
2. **A2** (log helper) - extract before moving handlers, so handlers are clean from the start
3. **A1** (handler extraction) - the big refactor, each handler is a cut-paste + cleanup
4. **A3** (static file mount) - easy win, independent
5. **B1** (active rules) - can do anytime
6. **A4** (lifespan cleanup) - lower priority, nice-to-have

## Files Touched

- `server/main.py` - major changes (handler extraction, static files, lifespan)
- `server/handlers.py` - **new file** with all message handlers
- `server/game.py` - minor changes (active rules, options_to_dict, from_client_data)

## Testing

- All existing tests in `test_game.py` should continue passing (game.py changes are additive/cosmetic)
- The WebSocket handler refactor is structural only - same logic, just reorganized
- Manual smoke test: create room, add CPU, play a round, verify everything works
