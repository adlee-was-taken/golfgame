# Plan 3: Miscellaneous Refactoring & Improvements

## Overview

Everything that doesn't fall under the main.py/game.py or ai.py refactors: shared utilities, dead code, test improvements, and structural cleanup.

---

## M1. Duplicate `get_card_value` Functions

There are currently **three** functions that compute card values:

1. `game.py:get_card_value(card: Card, options)` - Takes Card objects
2. `constants.py:get_card_value_for_rank(rank_str, options_dict)` - Takes rank strings
3. `ai.py:get_ai_card_value(card, options)` - AI-specific wrapper (also handles face-down estimation)

**Problem:** `game.py` and `constants.py` do the same thing with different interfaces, and neither handles all house rules identically. The AI version adds face-down logic but duplicates the base value lookup.

**Fix:**
- Keep `game.py:get_card_value()` as the canonical Card-based function (it already is the most complete)
- Keep `constants.py:get_card_value_for_rank()` for string-based lookups from logs/JSON
- Have `ai.py:get_ai_card_value()` delegate to `game.py:get_card_value()` for the base value, only adding its face-down estimation on top
- Add a brief comment in each noting which is canonical and why each variant exists

This is a minor cleanup - the current code works, it's just slightly confusing to have three entry points.

## M2. `GameOptions` Boilerplate Reduction

`GameOptions` currently has 17+ boolean fields. Every time a new house rule is added, you have to update:

1. `GameOptions` dataclass definition
2. `_options_to_dict()` in game.py
3. `get_active_rules()` logic in `get_state()`
4. `from_client_data()` (proposed in Plan 1)
5. `start_game` handler in main.py (currently, will move to handlers.py)

**Fix:** Use `dataclasses.fields()` introspection to auto-generate the dict and client data parsing:

```python
from dataclasses import fields, asdict

# _options_to_dict becomes:
def _options_to_dict(self) -> dict:
    return asdict(self.options)

# from_client_data becomes:
@classmethod
def from_client_data(cls, data: dict) -> "GameOptions":
    field_defaults = {f.name: f.default for f in fields(cls)}
    kwargs = {}
    for f in fields(cls):
        if f.name in data:
            kwargs[f.name] = data[f.name]
    # Special validation
    kwargs["initial_flips"] = max(0, min(2, kwargs.get("initial_flips", 2)))
    return cls(**kwargs)
```

This means adding a new house rule only requires adding the field to `GameOptions` and its entry in the active_rules display table (from Plan 1's B1).

## M3. Consolidate Game Logger Pattern in AI

`ai.py:process_cpu_turn()` has the same logger boilerplate as main.py's human handlers. After Plan 1's A2 creates `log_human_action()`, create a parallel:

```python
def log_cpu_action(game_id, player, action, card=None, position=None, game=None, reason=""):
    game_logger = get_logger()
    if game_logger and game_id:
        game_logger.log_move(
            game_id=game_id,
            player=player,
            is_cpu=True,
            action=action,
            card=card,
            position=position,
            game=game,
            decision_reason=reason,
        )
```

This appears ~4 times in `process_cpu_turn()`.

## M4. `Player.get_player()` Linear Search

`Game.get_player()` does a linear scan of the players list:

```python
def get_player(self, player_id: str) -> Optional[Player]:
    for player in self.players:
        if player.id == player_id:
            return player
    return None
```

With max 6 players this is fine performance-wise, but it's called frequently. Could add a `_player_lookup: dict[str, Player]` cache maintained by `add_player`/`remove_player`. Very minor optimization - only worth doing if we're already touching these methods.

## M5. Room Code Collision Potential

`RoomManager._generate_code()` generates random 4-letter codes and retries on collision. With 26^4 = 456,976 possibilities this is fine now, but if we ever scale, the while-True loop could theoretically spin. Low priority, but a simple improvement:

```python
def _generate_code(self, max_attempts=100) -> str:
    for _ in range(max_attempts):
        code = "".join(random.choices(string.ascii_uppercase, k=4))
        if code not in self.rooms:
            return code
    raise RuntimeError("Could not generate unique room code")
```

## M6. Test Coverage Gaps

Current test files:
- `test_game.py` - Core game logic (good coverage)
- `test_house_rules.py` - House rule scoring
- `test_v3_features.py` - New v3 features
- `test_maya_bug.py` - Specific regression test
- `tests/test_event_replay.py`, `test_persistence.py`, `test_replay.py` - Event system

**Missing:**
- No tests for `room.py` (Room, RoomManager, RoomPlayer)
- No tests for WebSocket message handlers (will be much easier to test after Plan 1's handler extraction)
- No unit tests for individual AI decision functions (will be much easier after Plan 2's decomposition)

**Recommendation:** After Plans 1 and 2 are complete, add:
- `test_handlers.py` - Test each message handler with mock WebSocket/Room
- `test_ai_decisions.py` - Test individual AI sub-functions (go-out logic, denial, etc.)
- `test_room.py` - Test Room/RoomManager CRUD operations

## M7. Unused/Dead Code Audit

Things to verify and potentially remove:
- `score_analysis.py` - Is this used anywhere or was it a one-off analysis tool?
- `game_analyzer.py` - Same question
- `auth.py` (top-level, not in routers/) - Appears to be an old file superseded by `services/auth_service.py`?
- `models/game_state.py` - Check if used or leftover from earlier design

## M8. Type Hints Consistency

Some functions have full type hints, others don't. The AI functions especially are loosely typed. After the ai.py refactor (Plan 2), ensure all new sub-functions have proper type hints:

```python
def _check_go_out_swap(
    player: Player,
    drawn_card: Card,
    profile: CPUProfile,
    game: Game,
    game_state: dict,
) -> Optional[int]:
```

This helps with IDE navigation and catching bugs during future changes.

---

## Execution Order

1. **M3** (AI logger helper) - Do alongside Plan 1's A2
2. **M2** (GameOptions introspection) - Do alongside Plan 1's B2/B3
3. **M1** (card value consolidation) - Quick cleanup
4. **M7** (dead code audit) - Quick investigation
5. **M5** (room code safety) - 2 lines
6. **M6** (tests) - After Plans 1 and 2 are complete
7. **M4** (player lookup) - Only if touching add/remove_player for other reasons
8. **M8** (type hints) - Ongoing, do as part of Plan 2

## Files Touched

- `server/ai.py` - logger helper, card value delegation
- `server/game.py` - GameOptions introspection
- `server/constants.py` - comments clarifying role
- `server/room.py` - room code safety (minor)
- `server/test_room.py` - **new file** (eventually)
- `server/test_handlers.py` - **new file** (eventually)
- `server/test_ai_decisions.py` - **new file** (eventually)
- Various files checked in dead code audit
