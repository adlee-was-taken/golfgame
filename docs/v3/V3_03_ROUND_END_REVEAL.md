# V3-03: Round End Dramatic Reveal

## Overview

When a round ends, all face-down cards must be revealed for scoring. In physical games, this is a dramatic moment - each player flips their hidden cards one at a time while others watch. Currently, all cards flip simultaneously which lacks drama.

**Dependencies:** None
**Dependents:** V3_07 (Score Tallying can follow the reveal)

---

## Goals

1. Reveal cards sequentially, one player at a time
2. Within each player, reveal cards with slight stagger
3. Pause briefly between players for dramatic effect
4. Start with the player who triggered final turn (the "knocker")
5. End with visible score tally moment
6. Play flip sounds for each reveal

---

## Current State

When round ends, the server sends a `round_over` message and clients receive a `game_state` update where all cards are now `face_up: true`. The state differ detects the changes but doesn't sequence the animations - they happen together.

From `showScoreboard()` in app.js:
```javascript
showScoreboard(scores, isFinal, rankings) {
    // Cards are already revealed by state update
    // Scoreboard appears immediately
}
```

---

## Design

### Reveal Sequence

```
1. Round ends - "Hole Complete!" message
2. VOLUNTARY FLIP WINDOW (4 seconds):
   - Players can tap their own face-down cards to peek/flip
   - Countdown timer shows remaining time
   - "Tap to reveal your cards" prompt
3. AUTO-REVEAL (after timeout or all flipped):
   - Knocker's cards reveal first (they went out)
   - For each other player (clockwise from knocker):
     a. Player area highlights
     b. Face-down cards flip with stagger (100ms between)
     c. Brief pause to see the reveal (400ms)
4. Score tallying animation (see V3_07)
5. Scoreboard appears
```

### Voluntary Flip Window

Before the dramatic reveal sequence, players get a chance to flip their own hidden cards:
- **Duration:** 4 seconds (configurable)
- **Purpose:** Let players see their own cards before everyone else does
- **UI:** Countdown timer, "Tap your cards to reveal" message
- **Skip:** If all players flip their cards, proceed immediately

### Visual Flow

```
Timeline:
0ms     - Round ends, pause
500ms   - Knocker highlight, first card flips
600ms   - Knocker second card flips (if any)
700ms   - Knocker third card flips (if any)
1100ms  - Pause to see knocker's hand
1500ms  - Player 2 highlight
1600ms  - Player 2 cards flip...
...continue for all players...
Final   - Scoreboard appears
```

### Timing Configuration

```javascript
// In timing-config.js
reveal: {
    voluntaryWindow: 4000,  // Time for players to flip their own cards
    initialPause: 500,      // Pause before auto-reveals start
    cardStagger: 100,       // Between cards in same hand
    playerPause: 400,       // Pause after each player's reveal
    highlightDuration: 200, // Player area highlight fade-in
}
```

---

## Implementation

### Approach: Intercept State Update

Instead of letting `renderGame()` show all cards instantly, intercept the round_over state and run a reveal sequence.

```javascript
// In handleMessage, game_state case:

case 'game_state':
    const oldState = this.gameState;
    const newState = data.game_state;

    // Check for round end transition
    const roundJustEnded = oldState?.phase !== 'round_over' &&
                           newState.phase === 'round_over';

    if (roundJustEnded) {
        // Don't update state yet - run reveal animation first
        this.runRoundEndReveal(oldState, newState, () => {
            this.gameState = newState;
            this.renderGame();
        });
        return;
    }

    // Normal state update
    this.gameState = newState;
    this.renderGame();
    break;
```

### Voluntary Flip Window Implementation

```javascript
async runVoluntaryFlipWindow(oldState, newState) {
    const T = window.TIMING?.reveal || {};
    const windowDuration = T.voluntaryWindow || 4000;

    // Find which of MY cards need flipping
    const myOldCards = oldState?.players?.find(p => p.id === this.playerId)?.cards || [];
    const myNewCards = newState?.players?.find(p => p.id === this.playerId)?.cards || [];
    const myHiddenPositions = [];

    for (let i = 0; i < 6; i++) {
        if (!myOldCards[i]?.face_up && myNewCards[i]?.face_up) {
            myHiddenPositions.push(i);
        }
    }

    // If I have no hidden cards, skip window
    if (myHiddenPositions.length === 0) {
        return;
    }

    // Show prompt and countdown
    this.showRevealPrompt(windowDuration);

    // Enable clicking on my hidden cards
    this.voluntaryFlipMode = true;
    this.voluntaryFlipPositions = new Set(myHiddenPositions);
    this.renderGame(); // Re-render to make cards clickable

    // Wait for timeout or all cards flipped
    return new Promise(resolve => {
        const checkComplete = () => {
            if (this.voluntaryFlipPositions.size === 0) {
                this.hideRevealPrompt();
                this.voluntaryFlipMode = false;
                resolve();
            }
        };

        // Set up interval to check completion
        const checkInterval = setInterval(checkComplete, 100);

        // Timeout after window duration
        setTimeout(() => {
            clearInterval(checkInterval);
            this.hideRevealPrompt();
            this.voluntaryFlipMode = false;
            resolve();
        }, windowDuration);
    });
}

showRevealPrompt(duration) {
    // Create countdown overlay
    const overlay = document.createElement('div');
    overlay.id = 'reveal-prompt';
    overlay.className = 'reveal-prompt';
    overlay.innerHTML = `
        <div class="reveal-prompt-text">Tap your cards to reveal</div>
        <div class="reveal-prompt-countdown">${Math.ceil(duration / 1000)}</div>
    `;
    document.body.appendChild(overlay);

    // Countdown timer
    const countdownEl = overlay.querySelector('.reveal-prompt-countdown');
    let remaining = duration;
    this.countdownInterval = setInterval(() => {
        remaining -= 100;
        countdownEl.textContent = Math.ceil(remaining / 1000);
        if (remaining <= 0) {
            clearInterval(this.countdownInterval);
        }
    }, 100);
}

hideRevealPrompt() {
    clearInterval(this.countdownInterval);
    const overlay = document.getElementById('reveal-prompt');
    if (overlay) {
        overlay.classList.add('fading');
        setTimeout(() => overlay.remove(), 300);
    }
}

// Modify handleCardClick to handle voluntary flips
handleCardClick(position) {
    // ... existing code ...

    // Voluntary flip during reveal window
    if (this.voluntaryFlipMode && this.voluntaryFlipPositions?.has(position)) {
        const myData = this.getMyPlayerData();
        const card = myData?.cards[position];
        if (card) {
            this.playSound('flip');
            this.fireLocalFlipAnimation(position, card);
            this.voluntaryFlipPositions.delete(position);
            // Update local state to show card flipped
            this.locallyFlippedCards.add(position);
            this.renderGame();
        }
        return;
    }

    // ... rest of existing code ...
}
```

### Reveal Animation Method

```javascript
async runRoundEndReveal(oldState, newState, onComplete) {
    const T = window.TIMING?.reveal || {};

    // STEP 1: Voluntary flip window - let players peek at their own cards
    this.setStatus('Reveal your hidden cards!', 'reveal-window');
    await this.runVoluntaryFlipWindow(oldState, newState);

    // STEP 2: Auto-reveal remaining hidden cards
    // Recalculate what needs flipping (some may have been voluntarily revealed)
    const revealsByPlayer = this.getCardsToReveal(oldState, newState);

    // Get reveal order: knocker first, then clockwise
    const knockerId = newState.finisher_id;
    const revealOrder = this.getRevealOrder(newState.players, knockerId);

    // Initial dramatic pause before auto-reveals
    this.setStatus('Revealing cards...', 'reveal');
    await this.delay(T.initialPause || 500);

    // Reveal each player's cards
    for (const player of revealOrder) {
        const cardsToFlip = revealsByPlayer.get(player.id) || [];
        if (cardsToFlip.length === 0) continue;

        // Highlight player area
        this.highlightPlayerArea(player.id, true);
        await this.delay(T.highlightDuration || 200);

        // Flip each card with stagger
        for (const { position, card } of cardsToFlip) {
            this.animateRevealFlip(player.id, position, card);
            await this.delay(T.cardStagger || 100);
        }

        // Wait for last flip to complete + pause
        await this.delay(400 + (T.playerPause || 400));

        // Remove highlight
        this.highlightPlayerArea(player.id, false);
    }

    // All revealed
    onComplete();
}

getCardsToReveal(oldState, newState) {
    const reveals = new Map();

    for (const newPlayer of newState.players) {
        const oldPlayer = oldState.players.find(p => p.id === newPlayer.id);
        if (!oldPlayer) continue;

        const cardsToFlip = [];
        for (let i = 0; i < 6; i++) {
            const wasHidden = !oldPlayer.cards[i]?.face_up;
            const nowVisible = newPlayer.cards[i]?.face_up;

            if (wasHidden && nowVisible) {
                cardsToFlip.push({
                    position: i,
                    card: newPlayer.cards[i]
                });
            }
        }

        if (cardsToFlip.length > 0) {
            reveals.set(newPlayer.id, cardsToFlip);
        }
    }

    return reveals;
}

getRevealOrder(players, knockerId) {
    // Knocker first
    const knocker = players.find(p => p.id === knockerId);
    const others = players.filter(p => p.id !== knockerId);

    // Others in clockwise order (already sorted by player_order)
    if (knocker) {
        return [knocker, ...others];
    }
    return others;
}

highlightPlayerArea(playerId, highlight) {
    if (playerId === this.playerId) {
        this.playerArea.classList.toggle('revealing', highlight);
    } else {
        const area = this.opponentsRow.querySelector(
            `.opponent-area[data-player-id="${playerId}"]`
        );
        if (area) {
            area.classList.toggle('revealing', highlight);
        }
    }
}

animateRevealFlip(playerId, position, cardData) {
    // Reuse existing flip animation
    if (playerId === this.playerId) {
        this.fireLocalFlipAnimation(position, cardData);
    } else {
        this.fireFlipAnimation(playerId, position, cardData);
    }
}
```

### CSS for Reveal Prompt and Highlights

```css
/* Voluntary reveal prompt */
.reveal-prompt {
    position: fixed;
    top: 20%;
    left: 50%;
    transform: translateX(-50%);
    background: linear-gradient(135deg, #f4a460 0%, #d4845a 100%);
    color: white;
    padding: 15px 30px;
    border-radius: 12px;
    text-align: center;
    z-index: 200;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    animation: prompt-entrance 0.3s ease-out;
}

.reveal-prompt.fading {
    animation: prompt-fade 0.3s ease-out forwards;
}

@keyframes prompt-entrance {
    0% { transform: translateX(-50%) translateY(-20px); opacity: 0; }
    100% { transform: translateX(-50%) translateY(0); opacity: 1; }
}

@keyframes prompt-fade {
    0% { opacity: 1; }
    100% { opacity: 0; }
}

.reveal-prompt-text {
    font-size: 1.1em;
    margin-bottom: 8px;
}

.reveal-prompt-countdown {
    font-size: 2em;
    font-weight: bold;
}

/* Cards clickable during voluntary reveal */
.player-area.voluntary-flip .card.can-flip {
    cursor: pointer;
    animation: flip-hint 0.8s ease-in-out infinite;
}

@keyframes flip-hint {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.03); }
}

/* Player area highlight during reveal */
.player-area.revealing,
.opponent-area.revealing {
    animation: reveal-highlight 0.3s ease-out;
}

@keyframes reveal-highlight {
    0% {
        box-shadow: 0 0 0 0 rgba(244, 164, 96, 0);
    }
    50% {
        box-shadow: 0 0 20px 10px rgba(244, 164, 96, 0.4);
    }
    100% {
        box-shadow: 0 0 10px 5px rgba(244, 164, 96, 0.2);
    }
}

/* Keep highlight while revealing */
.player-area.revealing,
.opponent-area.revealing {
    box-shadow: 0 0 10px 5px rgba(244, 164, 96, 0.2);
}
```

---

## Special Cases

### All Cards Already Face-Up

If a player has no face-down cards (they knocked or flipped everything):
- Skip their reveal in the sequence
- Don't highlight their area

### Player Disconnected

If a player left before round end:
- Their cards still need to reveal for scoring
- Handle missing player areas gracefully

### Single Player (Debug/Test)

If only one player remains:
- Still do the reveal animation for their cards
- Feels consistent

### Quick Mode (Future)

Consider a setting to skip reveal animation:
```javascript
if (this.settings.quickMode) {
    this.gameState = newState;
    this.renderGame();
    return;
}
```

---

## Timing Tuning

The reveal should feel dramatic but not tedious:

| Scenario | Cards to Reveal | Approximate Duration |
|----------|----------------|---------------------|
| 2 players, 2 hidden each | 4 cards | ~2 seconds |
| 4 players, 3 hidden each | 12 cards | ~4 seconds |
| 6 players, 4 hidden each | 24 cards | ~7 seconds |

If too slow, reduce:
- `cardStagger`: 100ms → 60ms
- `playerPause`: 400ms → 250ms

---

## Test Scenarios

1. **Normal round end** - Knocker reveals first, others follow
2. **Knocker has no hidden cards** - Skip knocker, start with next player
3. **All players have hidden cards** - Full reveal sequence
4. **Some players have no hidden cards** - Skip them gracefully
5. **Player disconnected** - Handle gracefully
6. **2-player game** - Both players reveal in order
7. **Quick succession** - Multiple round ends don't overlap

---

## Acceptance Criteria

- [ ] **Voluntary flip window:** 4-second window for players to flip their own cards
- [ ] Countdown timer shows remaining time
- [ ] Players can tap their face-down cards to reveal early
- [ ] Auto-reveal starts after timeout (or if all cards flipped)
- [ ] Cards reveal sequentially during auto-reveal, not all at once
- [ ] Knocker (finisher) reveals first
- [ ] Other players reveal clockwise after knocker
- [ ] Cards within a hand have slight stagger
- [ ] Pause between players for drama
- [ ] Player area highlights during their reveal
- [ ] Flip sound plays for each card
- [ ] Reveal completes before scoreboard appears
- [ ] Handles players with no hidden cards
- [ ] Animation can be interrupted if needed

---

## Implementation Order

1. Add reveal timing to `timing-config.js`
2. Add `data-player-id` to opponent areas (if not done in V3_02)
3. Implement `getCardsToReveal()` method
4. Implement `getRevealOrder()` method
5. Implement `highlightPlayerArea()` method
6. Implement `runRoundEndReveal()` method
7. Intercept round_over state transition
8. Add reveal highlight CSS
9. Test with various player counts and card states
10. Tune timing for best dramatic effect

---

## Notes for Agent

- Use `window.cardAnimations.animateFlip()` or `animateOpponentFlip()` for reveals
- The existing CardAnimations class has all flip animation methods ready
- Don't forget to set `finisher_id` in game state (server may already do this)
- The reveal order should match the physical clockwise order
- Consider: Add a "drum roll" sound before reveals? (Nice to have)
- The scoreboard should NOT appear until all reveals complete
- State update is deferred until animation completes - ensure no race conditions
- All animations use anime.js timelines internally - no CSS keyframes needed
