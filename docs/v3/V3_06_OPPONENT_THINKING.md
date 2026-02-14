# V3-06: Opponent Thinking Phase

## Overview

In physical card games, you watch opponents pick up a card, consider it, and decide. Currently, CPU turns happen quickly with minimal visual indication that they're "thinking." This feature adds visible consideration time.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Show when an opponent is considering their move
2. Highlight which pile they're considering (deck vs discard)
3. Add brief thinking pause before CPU actions
4. Make CPU feel more like a real player
5. Human opponents should also show consideration state

---

## Current State

From `app.js` and `card-animations.js`:
```javascript
// In app.js
updateCpuConsideringState() {
    const currentPlayer = this.gameState.players.find(
        p => p.id === this.gameState.current_player_id
    );
    const isCpuTurn = currentPlayer && currentPlayer.is_cpu;
    const hasNotDrawn = !this.gameState.has_drawn_card;

    if (isCpuTurn && hasNotDrawn) {
        this.discard.classList.add('cpu-considering');
    } else {
        this.discard.classList.remove('cpu-considering');
    }
}

// CardAnimations already has CPU thinking glow:
startCpuThinking(element) {
    anime({
        targets: element,
        boxShadow: [
            '0 4px 12px rgba(0,0,0,0.3)',
            '0 4px 12px rgba(0,0,0,0.3), 0 0 18px rgba(59, 130, 246, 0.5)',
            '0 4px 12px rgba(0,0,0,0.3)'
        ],
        duration: 1500,
        easing: 'easeInOutSine',
        loop: true
    });
}
```

The existing `startCpuThinking()` method in CardAnimations provides a looping glow animation. This feature enhances visibility further.

---

## Design

### Enhanced Consideration Display

1. **Opponent area highlight** - Active player's area glows
2. **"Thinking" indicator** - Small animation near their name
3. **Deck/discard highlight** - Show which pile they're eyeing
4. **Held card consideration** - After draw, show they're deciding

### States

```
1. WAITING_TO_DRAW
   - Player area highlighted
   - Deck and discard both subtly available
   - Brief pause before action (CPU)

2. CONSIDERING_DISCARD
   - Player looks at discard pile
   - Discard pile pulses brighter
   - "Eye" indicator on discard

3. DREW_CARD
   - Held card visible (existing)
   - Player area still highlighted

4. CONSIDERING_SWAP
   - Player deciding which card to swap
   - Their hand cards subtly indicate options
```

### Timing (CPU only)

```javascript
// In timing-config.js
cpuThinking: {
    beforeDraw: 800,        // Pause before CPU draws
    discardConsider: 400,   // Extra pause when looking at discard
    beforeSwap: 500,        // Pause before CPU swaps
    beforeDiscard: 300,     // Pause before CPU discards drawn card
}
```

Human players don't need artificial pauses - their actual thinking provides the delay.

---

## Implementation

### Thinking Indicator

Add a small animated indicator near the current player's name:

```html
<!-- In opponent area -->
<div class="opponent-area" data-player-id="...">
    <h4>
        <span class="thinking-indicator hidden">🤔</span>
        <span class="opponent-name">Sofia</span>
        ...
    </h4>
</div>
```

### CSS and Animations

Most animations should use anime.js via CardAnimations class for consistency:

```javascript
// In CardAnimations class - the startCpuThinking method already exists
// Add similar methods for other thinking states:

startOpponentThinking(opponentArea) {
    const id = `opponentThinking-${opponentArea.dataset.playerId}`;
    this.stopOpponentThinking(opponentArea);

    anime({
        targets: opponentArea,
        boxShadow: [
            '0 0 15px rgba(244, 164, 96, 0.4)',
            '0 0 25px rgba(244, 164, 96, 0.6)',
            '0 0 15px rgba(244, 164, 96, 0.4)'
        ],
        duration: 1500,
        easing: 'easeInOutSine',
        loop: true
    });
}

stopOpponentThinking(opponentArea) {
    anime.remove(opponentArea);
    opponentArea.style.boxShadow = '';
}
```

Minimal CSS for layout only:

```css
/* Thinking indicator - simple show/hide */
.thinking-indicator {
    display: inline-block;
    margin-right: 4px;
}

.thinking-indicator.hidden {
    display: none;
}

/* Current turn highlight base (animation handled by anime.js) */
.opponent-area.current-turn {
    border-color: #f4a460;
}

/* Eye indicator positioning */
.pile-eye-indicator {
    position: absolute;
    top: -15px;
    right: -10px;
    font-size: 1.2em;
}
```

For the thinking indicator bobbing, use anime.js:

```javascript
// Animate emoji indicator
startThinkingIndicator(element) {
    anime({
        targets: element,
        translateY: [0, -3, 0],
        duration: 800,
        easing: 'easeInOutSine',
        loop: true
    });
}
```

### JavaScript Updates

```javascript
// Enhanced consideration state management

updateConsiderationState() {
    const currentPlayer = this.gameState?.players?.find(
        p => p.id === this.gameState.current_player_id
    );

    if (!currentPlayer || currentPlayer.id === this.playerId) {
        this.clearConsiderationState();
        return;
    }

    const hasDrawn = this.gameState.has_drawn_card;
    const isCpu = currentPlayer.is_cpu;

    // Find opponent area
    const area = this.opponentsRow.querySelector(
        `.opponent-area[data-player-id="${currentPlayer.id}"]`
    );

    if (!area) return;

    // Show thinking indicator for CPUs
    const indicator = area.querySelector('.thinking-indicator');
    if (indicator) {
        indicator.classList.toggle('hidden', !isCpu || hasDrawn);
    }

    // Add thinking class to area
    area.classList.toggle('thinking', !hasDrawn);

    // Show which pile they might be considering
    if (!hasDrawn && isCpu) {
        // CPU AI hint: check if discard is attractive
        const discardValue = this.getDiscardValue();
        if (discardValue !== null && discardValue <= 4) {
            this.discard.classList.add('being-considered');
            this.deck.classList.remove('being-considered');
        } else {
            this.deck.classList.add('being-considered');
            this.discard.classList.remove('being-considered');
        }
    } else {
        this.deck.classList.remove('being-considered');
        this.discard.classList.remove('being-considered');
    }
}

clearConsiderationState() {
    // Remove all consideration indicators
    this.opponentsRow.querySelectorAll('.thinking-indicator').forEach(el => {
        el.classList.add('hidden');
    });
    this.opponentsRow.querySelectorAll('.opponent-area').forEach(el => {
        el.classList.remove('thinking');
    });
    this.deck.classList.remove('being-considered');
    this.discard.classList.remove('being-considered');
}

getDiscardValue() {
    const card = this.gameState?.discard_top;
    if (!card) return null;

    const values = this.gameState?.card_values || {
        'A': 1, '2': -2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
        '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 0, '★': -2
    };

    return values[card.rank] ?? 10;
}
```

### Server-Side CPU Thinking Delay

The server should add pauses for CPU thinking (or the client can delay rendering):

```python
# In ai.py or game.py, after CPU makes decision

async def cpu_take_turn(self, game, player_id):
    thinking_time = self.profile.get_thinking_time()  # 500-1500ms based on profile

    # Pre-draw consideration
    await asyncio.sleep(thinking_time * 0.5)

    # Make draw decision
    source = self.decide_draw_source(game, player_id)

    # Broadcast "considering" state
    await self.broadcast_cpu_considering(game, player_id, source)
    await asyncio.sleep(thinking_time * 0.3)

    # Execute draw
    game.draw_card(player_id, source)

    # Post-draw consideration
    await asyncio.sleep(thinking_time * 0.4)

    # Make swap/discard decision
    ...
```

Alternatively, handle all delays on the client side by adding pauses before rendering CPU actions.

---

## CPU Personality Integration

Different AI profiles could have different thinking patterns:

```javascript
// Thinking time variance by personality (from ai.py profiles)
const thinkingProfiles = {
    'Sofia': { baseTime: 1200, variance: 200 },     // Calculated & Patient
    'Maya': { baseTime: 600, variance: 100 },       // Aggressive Closer
    'Priya': { baseTime: 1000, variance: 300 },     // Pair Hunter (considers more)
    'Marcus': { baseTime: 800, variance: 150 },     // Steady Eddie
    'Kenji': { baseTime: 500, variance: 200 },      // Risk Taker (quick)
    'Diego': { baseTime: 700, variance: 400 },      // Chaotic Gambler (variable)
    'River': { baseTime: 900, variance: 250 },      // Adaptive Strategist
    'Sage': { baseTime: 1100, variance: 150 },      // Sneaky Finisher
};
```

---

## Test Scenarios

1. **CPU turn starts** - Area highlights, thinking indicator shows
2. **CPU considering discard** - Discard pile glows if valuable card
3. **CPU draws** - Thinking indicator changes to held card state
4. **CPU swaps** - Brief consideration before swap
5. **Human opponent turn** - Area highlights but no thinking indicator
6. **Local player turn** - No consideration UI (they know what they're doing)

---

## Acceptance Criteria

- [ ] Current opponent's area highlights during their turn
- [ ] CPU players show thinking indicator (emoji)
- [ ] Deck/discard shows which pile CPU is considering
- [ ] Brief pause before CPU actions (feels like thinking)
- [ ] Different CPU personalities have different timing
- [ ] Human opponents highlight without thinking indicator
- [ ] All indicators clear when turn ends
- [ ] Doesn't slow down the game significantly

---

## Implementation Order

1. Add thinking indicator element to opponent areas
2. Add CSS for thinking animations
3. Implement `updateConsiderationState()` method
4. Implement `clearConsiderationState()` method
5. Add pile consideration highlighting
6. Integrate CPU thinking delays (server or client)
7. Test with various CPU profiles
8. Tune timing for natural feel

---

## Notes for Agent

- Use existing CardAnimations methods: `startCpuThinking()`, `stopCpuThinking()`
- Add new methods to CardAnimations for opponent area glow
- Use anime.js for all looping animations, not CSS keyframes
- Keep thinking pauses short enough to not frustrate players
- The goal is to make CPUs feel more human, not slow
- Different profiles should feel distinct in their play speed
- Human players don't need artificial delays
- Consider: Option to speed up CPU thinking? (Future setting)
- The "being considered" pile indicator is a subtle hint at AI logic
- Track animations in `activeAnimations` for proper cleanup
