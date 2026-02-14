# V3-05: Final Turn Urgency

## Overview

When a player reveals all their cards, the round enters "final turn" phase - each other player gets one last turn. This is a tense moment in physical games. Currently, only a small badge shows "Final Turn" which lacks urgency.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Create visual tension when final turn begins
2. Show who triggered final turn (the knocker)
3. Indicate how many players still need to act
4. Make each remaining turn feel consequential
5. Countdown feeling as players take their last turns

---

## Current State

From `app.js`:
```javascript
// Final turn badge exists but is minimal
if (isFinalTurn) {
    this.finalTurnBadge.classList.remove('hidden');
} else {
    this.finalTurnBadge.classList.add('hidden');
}
```

The badge just shows "FINAL TURN" text - no countdown, no urgency indicator.

---

## Design

### Visual Elements

1. **Pulsing Border** - Game area gets subtle pulsing red/orange border
2. **Enhanced Badge** - Larger badge with countdown
3. **Knocker Indicator** - Show who triggered final turn
4. **Turn Counter** - "2 players remaining" style indicator

### Badge Enhancement

```
Current:  [FINAL TURN]

Enhanced: [⚠️ FINAL TURN]
          [Player 2 of 3]
```

Or more dramatic:
```
[🔔 LAST CHANCE!]
[2 turns left]
```

### Color Scheme

- Normal play: Green felt background
- Final turn: Subtle warm/orange tint or border pulse
- Not overwhelming, but noticeable shift

---

## Implementation

### Enhanced Final Turn Badge

```html
<!-- Enhanced badge structure -->
<div id="final-turn-badge" class="hidden">
    <div class="final-turn-icon">⚡</div>
    <div class="final-turn-text">FINAL TURN</div>
    <div class="final-turn-remaining">2 turns left</div>
</div>
```

### CSS Enhancements

```css
/* Enhanced final turn badge */
#final-turn-badge {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: linear-gradient(135deg, #ff6b35 0%, #d63031 100%);
    color: white;
    padding: 12px 24px;
    border-radius: 12px;
    text-align: center;
    z-index: 100;
    box-shadow: 0 4px 20px rgba(214, 48, 49, 0.4);
    animation: final-turn-pulse 1.5s ease-in-out infinite;
}

#final-turn-badge.hidden {
    display: none;
}

.final-turn-icon {
    font-size: 1.5em;
    margin-bottom: 4px;
}

.final-turn-text {
    font-weight: bold;
    font-size: 1.2em;
    letter-spacing: 0.1em;
}

.final-turn-remaining {
    font-size: 0.9em;
    opacity: 0.9;
    margin-top: 4px;
}

@keyframes final-turn-pulse {
    0%, 100% {
        transform: translate(-50%, -50%) scale(1);
        box-shadow: 0 4px 20px rgba(214, 48, 49, 0.4);
    }
    50% {
        transform: translate(-50%, -50%) scale(1.02);
        box-shadow: 0 4px 30px rgba(214, 48, 49, 0.6);
    }
}

/* Game area border pulse during final turn */
#game-screen.final-turn-active {
    animation: game-area-urgency 2s ease-in-out infinite;
}

@keyframes game-area-urgency {
    0%, 100% {
        box-shadow: inset 0 0 0 0 rgba(255, 107, 53, 0);
    }
    50% {
        box-shadow: inset 0 0 30px 0 rgba(255, 107, 53, 0.15);
    }
}

/* Knocker highlight */
.player-area.is-knocker,
.opponent-area.is-knocker {
    border: 2px solid #ff6b35;
}

.knocker-badge {
    position: absolute;
    top: -10px;
    right: -10px;
    background: #ff6b35;
    color: white;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.7em;
    font-weight: bold;
}
```

### JavaScript Updates

```javascript
// In renderGame() or dedicated method

updateFinalTurnDisplay() {
    const isFinalTurn = this.gameState?.phase === 'final_turn';
    const finisherId = this.gameState?.finisher_id;

    // Toggle game area class
    this.gameScreen.classList.toggle('final-turn-active', isFinalTurn);

    if (isFinalTurn) {
        // Calculate remaining turns
        const remaining = this.countRemainingTurns();

        // Update badge content
        this.finalTurnBadge.querySelector('.final-turn-remaining').textContent =
            remaining === 1 ? '1 turn left' : `${remaining} turns left`;

        // Show badge with entrance animation
        this.finalTurnBadge.classList.remove('hidden');
        this.finalTurnBadge.classList.add('entering');
        setTimeout(() => {
            this.finalTurnBadge.classList.remove('entering');
        }, 300);

        // Mark knocker
        this.markKnocker(finisherId);

        // Play alert sound on first appearance
        if (!this.finalTurnAnnounced) {
            this.playSound('alert');
            this.finalTurnAnnounced = true;
        }
    } else {
        this.finalTurnBadge.classList.add('hidden');
        this.gameScreen.classList.remove('final-turn-active');
        this.finalTurnAnnounced = false;
        this.clearKnockerMark();
    }
}

countRemainingTurns() {
    if (!this.gameState || this.gameState.phase !== 'final_turn') return 0;

    const finisherId = this.gameState.finisher_id;
    const currentIdx = this.gameState.players.findIndex(
        p => p.id === this.gameState.current_player_id
    );
    const finisherIdx = this.gameState.players.findIndex(
        p => p.id === finisherId
    );

    if (currentIdx === -1 || finisherIdx === -1) return 0;

    // Count players between current and finisher (not including finisher)
    let count = 0;
    let idx = currentIdx;
    const numPlayers = this.gameState.players.length;

    while (idx !== finisherIdx) {
        count++;
        idx = (idx + 1) % numPlayers;
    }

    return count;
}

markKnocker(knockerId) {
    // Add knocker badge to the player who triggered final turn
    this.clearKnockerMark();

    if (!knockerId) return;

    if (knockerId === this.playerId) {
        this.playerArea.classList.add('is-knocker');
        // Add badge element
        const badge = document.createElement('div');
        badge.className = 'knocker-badge';
        badge.textContent = 'OUT';
        this.playerArea.appendChild(badge);
    } else {
        const area = this.opponentsRow.querySelector(
            `.opponent-area[data-player-id="${knockerId}"]`
        );
        if (area) {
            area.classList.add('is-knocker');
            const badge = document.createElement('div');
            badge.className = 'knocker-badge';
            badge.textContent = 'OUT';
            area.appendChild(badge);
        }
    }
}

clearKnockerMark() {
    // Remove all knocker indicators
    document.querySelectorAll('.is-knocker').forEach(el => {
        el.classList.remove('is-knocker');
    });
    document.querySelectorAll('.knocker-badge').forEach(el => {
        el.remove();
    });
}
```

### Alert Sound

```javascript
// In playSound() method
} else if (type === 'alert') {
    // Attention-getting sound for final turn
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.type = 'triangle';
    osc.frequency.setValueAtTime(523, ctx.currentTime);  // C5
    osc.frequency.setValueAtTime(659, ctx.currentTime + 0.1);  // E5
    osc.frequency.setValueAtTime(784, ctx.currentTime + 0.2);  // G5

    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);

    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.4);
}
```

---

## Entrance Animation

When final turn starts, badge should appear dramatically:

```css
#final-turn-badge.entering {
    animation: badge-entrance 0.3s ease-out;
}

@keyframes badge-entrance {
    0% {
        transform: translate(-50%, -50%) scale(0.5);
        opacity: 0;
    }
    70% {
        transform: translate(-50%, -50%) scale(1.1);
    }
    100% {
        transform: translate(-50%, -50%) scale(1);
        opacity: 1;
    }
}
```

---

## Turn Countdown Update

Each time a player takes their final turn, update the counter:

```javascript
// In state change detection
if (newState.phase === 'final_turn') {
    const oldRemaining = this.lastRemainingTurns;
    const newRemaining = this.countRemainingTurns();

    if (oldRemaining !== newRemaining) {
        this.updateFinalTurnCounter(newRemaining);
        this.lastRemainingTurns = newRemaining;

        // Pulse the badge on update
        this.finalTurnBadge.classList.add('counter-updated');
        setTimeout(() => {
            this.finalTurnBadge.classList.remove('counter-updated');
        }, 200);
    }
}
```

```css
#final-turn-badge.counter-updated {
    animation: counter-pulse 0.2s ease-out;
}

@keyframes counter-pulse {
    0% { transform: translate(-50%, -50%) scale(1); }
    50% { transform: translate(-50%, -50%) scale(1.05); }
    100% { transform: translate(-50%, -50%) scale(1); }
}
```

---

## Test Scenarios

1. **Enter final turn** - Badge appears with animation, sound plays
2. **Turn counter decrements** - Shows "2 turns left" → "1 turn left"
3. **Last turn** - Shows "1 turn left", extra urgency
4. **Round ends** - Badge disappears, border pulse stops
5. **Knocker marked** - OUT badge on player who triggered
6. **Multiple rounds** - Badge resets between rounds

---

## Acceptance Criteria

- [ ] Final turn badge appears when phase is `final_turn`
- [ ] Badge shows remaining turns count
- [ ] Count updates as players take turns
- [ ] Game area has subtle urgency visual
- [ ] Knocker is marked with badge
- [ ] Alert sound plays when final turn starts
- [ ] Badge has entrance animation
- [ ] All visuals reset when round ends
- [ ] Not overwhelming - tension without annoyance

---

## Implementation Order

1. Update HTML structure for enhanced badge
2. Add CSS for badge, urgency border, knocker indicator
3. Implement `countRemainingTurns()` method
4. Implement `updateFinalTurnDisplay()` method
5. Implement `markKnocker()` and `clearKnockerMark()`
6. Add alert sound to `playSound()`
7. Integrate into `renderGame()` or state change handler
8. Add entrance animation
9. Add counter update pulse
10. Test all scenarios

---

## Notes for Agent

- The urgency should enhance tension, not frustrate players
- Keep the pulsing subtle - not distracting during play
- The knocker badge helps players understand game state
- Consider mobile: badge should fit on small screens
- The remaining turns count helps players plan their last move
- Reset all state between rounds (finalTurnAnnounced flag)
