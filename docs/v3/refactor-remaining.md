# Remaining Refactor Tasks

Leftover items from the v3 refactor plans that are functional but could benefit from further cleanup.

---

## R1. Decompose `calculate_swap_score()` (from Plan 2, Step 4)

**File:** `server/ai.py` (~236 lines)

Scores a single position for swapping. Still long with inline pair calculations, point gain logic, reveal bonuses, and comeback bonuses. Could extract:

- `_pair_improvement(player, position, new_card, options)` — pair-related benefit of swapping into a position
- `_standings_pressure(player, game)` — how much standings position should affect decisions (shared with `should_take_discard`)

**Validation:** `python server/simulate.py 500` before and after — stats should match within normal variance.

---

## R2. Decompose `should_take_discard()` (from Plan 2, Step 5)

**File:** `server/ai.py` (~148 lines)

Decides whether to take from discard pile. Contains a nested `has_good_swap_option()` helper. After R1's extracted utilities exist, this should shrink since `project_score()` and `known_score()` handle the repeated estimation logic.

**Validation:** Same simulation approach as R1.

---

## R3. New Test Files (from Plan 3, M6)

After Plans 1 and 2, the extracted handlers and AI sub-functions are much easier to unit test. Add:

- **`server/test_handlers.py`** — Test each message handler with mock WebSocket/Room
- **`server/test_ai_decisions.py`** — Test individual AI sub-functions (go-out logic, denial, etc.)
- **`server/test_room.py`** — Test Room/RoomManager CRUD operations

---

## Priority

R1 and R2 are pure structural refactors — no behavior changes, low risk, but also low urgency since the code works fine. R3 adds safety nets for future changes.
