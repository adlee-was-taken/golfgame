# V3-01: Dealer/Starting Player Rotation

## Overview

In physical card games, the deal rotates clockwise after each hand. The player who deals also typically plays last (or the player to their left plays first). Currently, our game always starts with the host/first player each round.

**Dependencies:** None (server-side foundation)
**Dependents:** V3_02 (Dealing Animation needs to know who is dealing)

---

## Goals

1. Track the current dealer position across rounds
2. Rotate dealer clockwise after each round
3. First player to act is to the left of the dealer (next in order)
4. Communicate dealer position to clients
5. Visual indicator of current dealer (client-side, prep for V3_02)

---

## Current State

From `server/game.py`, round start logic:

```python
def start_next_round(self):
    """Start the next round."""
    self.current_round += 1
    # ... deal cards ...
    # Current player is always index 0 (host/first joiner)
    self.current_player_idx = 0
```

The `player_order` list is set once at game start and never changes. The first player is always `player_order[0]`.

---

## Design

### Server Changes

#### New State Fields

```python
# In Game class __init__
self.dealer_idx = 0  # Index into player_order of current dealer
```

#### Round Start Logic

```python
def start_next_round(self):
    """Start the next round."""
    self.current_round += 1

    # Rotate dealer clockwise (next player in order)
    if self.current_round > 1:
        self.dealer_idx = (self.dealer_idx + 1) % len(self.player_order)

    # First player is to the LEFT of dealer (next after dealer)
    self.current_player_idx = (self.dealer_idx + 1) % len(self.player_order)

    # ... rest of dealing logic ...
```

#### Game State Response

Add dealer info to the game state sent to clients:

```python
def get_state(self, for_player_id: str) -> dict:
    return {
        # ... existing fields ...
        "dealer_id": self.player_order[self.dealer_idx] if self.player_order else None,
        "dealer_idx": self.dealer_idx,
        # current_player_id already exists
    }
```

### Client Changes

#### State Handling

In `app.js`, the `gameState` will now include:
- `dealer_id` - The player ID of the current dealer
- `dealer_idx` - Index for ordering

#### Visual Indicator

Add a dealer chip/badge to the current dealer's area:

```javascript
// In renderGame() or opponent rendering
const isDealer = player.id === this.gameState.dealer_id;
if (isDealer) {
    div.classList.add('is-dealer');
    // Add dealer chip element
}
```

#### CSS

```css
/* Dealer indicator */
.is-dealer::before {
    content: "D";
    position: absolute;
    top: -8px;
    left: -8px;
    width: 20px;
    height: 20px;
    background: #f4a460;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: bold;
    color: #1a1a2e;
    border: 2px solid #fff;
    z-index: 10;
}

/* Or use a chip emoji/icon */
.dealer-chip {
    position: absolute;
    top: -10px;
    right: -10px;
    font-size: 1.2em;
}
```

---

## Edge Cases

### Player Leaves Mid-Game

If the current dealer leaves:
- Dealer position should stay at the same index
- If that index is now out of bounds, wrap to 0
- The show must go on

```python
def remove_player(self, player_id: str):
    # ... existing removal logic ...

    # Adjust dealer_idx if needed
    if self.dealer_idx >= len(self.player_order):
        self.dealer_idx = 0
```

### 2-Player Game

With 2 players, dealer alternates each round:
- Round 1: Player A deals, Player B plays first
- Round 2: Player B deals, Player A plays first
- This works naturally with the modulo logic

### Game Start (Round 1)

For round 1:
- Dealer is the host (player_order[0])
- First player is player_order[1] (or player_order[0] in solo/test)

Option: Could randomize initial dealer, but host-as-first-dealer is traditional.

---

## Test Cases

```python
# server/tests/test_dealer_rotation.py

def test_dealer_starts_as_host():
    """First round dealer is the host (first player)."""
    game = create_game_with_players(["Alice", "Bob", "Carol"])
    game.start_game()

    assert game.dealer_idx == 0
    assert game.get_dealer_id() == "Alice"
    # First player is to dealer's left
    assert game.current_player_idx == 1
    assert game.get_current_player_id() == "Bob"

def test_dealer_rotates_each_round():
    """Dealer advances clockwise after each round."""
    game = create_game_with_players(["Alice", "Bob", "Carol"])
    game.start_game()

    # Round 1: Alice deals, Bob plays first
    assert game.dealer_idx == 0

    complete_round(game)
    game.start_next_round()

    # Round 2: Bob deals, Carol plays first
    assert game.dealer_idx == 1
    assert game.current_player_idx == 2

    complete_round(game)
    game.start_next_round()

    # Round 3: Carol deals, Alice plays first
    assert game.dealer_idx == 2
    assert game.current_player_idx == 0

def test_dealer_wraps_around():
    """Dealer wraps to first player after last player deals."""
    game = create_game_with_players(["Alice", "Bob"])
    game.start_game()

    # Round 1: Alice deals
    assert game.dealer_idx == 0

    complete_round(game)
    game.start_next_round()

    # Round 2: Bob deals
    assert game.dealer_idx == 1

    complete_round(game)
    game.start_next_round()

    # Round 3: Back to Alice
    assert game.dealer_idx == 0

def test_dealer_adjustment_on_player_leave():
    """Dealer index adjusts when players leave."""
    game = create_game_with_players(["Alice", "Bob", "Carol"])
    game.start_game()

    complete_round(game)
    game.start_next_round()
    # Bob is now dealer (idx 1)

    game.remove_player("Carol")  # Remove last player
    # Dealer idx should still be valid
    assert game.dealer_idx == 1
    assert game.dealer_idx < len(game.player_order)

def test_state_includes_dealer_info():
    """Game state includes dealer information."""
    game = create_game_with_players(["Alice", "Bob"])
    game.start_game()

    state = game.get_state("Alice")
    assert "dealer_id" in state
    assert state["dealer_id"] == "Alice"
```

---

## Implementation Order

1. Add `dealer_idx` field to Game class
2. Modify `start_game()` to set initial dealer
3. Modify `start_next_round()` to rotate dealer
4. Modify `get_state()` to include dealer info
5. Handle edge case: player leaves
6. Add tests for dealer rotation
7. Client: Add dealer visual indicator
8. Client: Style the dealer chip/badge

---

## Acceptance Criteria

- [ ] Round 1 dealer is the host (first player in order)
- [ ] Dealer rotates clockwise after each round
- [ ] First player to act is always left of dealer
- [ ] Dealer info included in game state sent to clients
- [ ] Dealer position survives player departure
- [ ] Visual indicator shows current dealer
- [ ] All existing tests still pass

---

## Notes for Agent

- The `player_order` list is established at game start and defines clockwise order
- Keep backward compatibility - games in progress shouldn't break
- The dealer indicator is prep work for V3_02 (dealing animation)
- Consider: Should dealer deal to themselves last? (Traditional, but not gameplay-affecting)
- The visual dealer chip will become important when dealing animation shows cards coming FROM the dealer
