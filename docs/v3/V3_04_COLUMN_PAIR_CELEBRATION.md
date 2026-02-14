# V3-04: Column Pair Celebration

## Overview

Matching cards in a column (positions 0+3, 1+4, or 2+5) score 0 points - a key strategic mechanic. In physical games, players often exclaim when they make a pair. Currently, there's no visual feedback when a pair is formed, missing a satisfying moment.

**Dependencies:** None
**Dependents:** V3_10 (Column Pair Indicator builds on this)

---

## Goals

1. Detect when a swap creates a new column pair
2. Play satisfying visual celebration on both cards
3. Play a distinct "pair matched" sound
4. Brief but noticeable - shouldn't slow gameplay
5. Works for both local player and opponent swaps

---

## Current State

Column pairs are calculated during scoring but there's no visual indication when a pair forms during play.

From the rules (RULES.md):
```
Column 0: positions (0, 3)
Column 1: positions (1, 4)
Column 2: positions (2, 5)
```

A pair is formed when both cards in a column are face-up and have the same rank.

---

## Design

### Detection

After any swap or flip, check if a new pair was formed:

```javascript
function detectNewPair(oldCards, newCards) {
    const columns = [[0, 3], [1, 4], [2, 5]];

    for (const [top, bottom] of columns) {
        const wasPaired = isPaired(oldCards, top, bottom);
        const nowPaired = isPaired(newCards, top, bottom);

        if (!wasPaired && nowPaired) {
            return { column: columns.indexOf([top, bottom]), positions: [top, bottom] };
        }
    }
    return null;
}

function isPaired(cards, pos1, pos2) {
    const card1 = cards[pos1];
    const card2 = cards[pos2];
    return card1?.face_up && card2?.face_up &&
           card1?.rank && card2?.rank &&
           card1.rank === card2.rank;
}
```

### Celebration Animation

When a pair forms:

```
1. Both cards pulse/glow simultaneously
2. Brief sparkle effect (optional)
3. "Pair!" sound plays
4. Animation lasts ~400ms
5. Cards return to normal
```

### Visual Effect Options

**Option A: Anime.js Glow Pulse** (Recommended - matches existing animation system)
```javascript
// Add to CardAnimations class
celebratePair(cardElement1, cardElement2) {
    this.playSound('pair');

    const duration = window.TIMING?.celebration?.pairDuration || 400;

    [cardElement1, cardElement2].forEach(el => {
        anime({
            targets: el,
            boxShadow: [
                '0 0 0 0 rgba(255, 215, 0, 0)',
                '0 0 15px 8px rgba(255, 215, 0, 0.5)',
                '0 0 0 0 rgba(255, 215, 0, 0)'
            ],
            scale: [1, 1.05, 1],
            duration: duration,
            easing: 'easeOutQuad'
        });
    });
}
```

**Option B: Scale Bounce**
```javascript
anime({
    targets: [cardElement1, cardElement2],
    scale: [1, 1.1, 1],
    duration: 400,
    easing: 'easeOutQuad'
});
```

**Option C: Connecting Line**
Draw a brief line connecting the paired cards (more complex).

**Recommendation:** Option A - anime.js glow pulse matches the existing animation system.

---

## Implementation

### Timing Configuration

```javascript
// In timing-config.js
celebration: {
    pairDuration: 400,    // Celebration animation length
    pairDelay: 50,        // Slight delay before celebration (let swap settle)
}
```

### Sound

Add a new sound type for pairs:

```javascript
// In playSound() method
} else if (type === 'pair') {
    // Two-tone "ding-ding" for pair match
    const osc1 = ctx.createOscillator();
    const osc2 = ctx.createOscillator();
    const gain = ctx.createGain();

    osc1.connect(gain);
    osc2.connect(gain);
    gain.connect(ctx.destination);

    osc1.frequency.setValueAtTime(880, ctx.currentTime);  // A5
    osc2.frequency.setValueAtTime(1108, ctx.currentTime); // C#6

    gain.gain.setValueAtTime(0.1, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);

    osc1.start(ctx.currentTime);
    osc2.start(ctx.currentTime);
    osc1.stop(ctx.currentTime + 0.3);
    osc2.stop(ctx.currentTime + 0.3);
}
```

### Detection Integration

In the state differ or after swap animations:

```javascript
// In triggerAnimationsForStateChange() or after swap completes

checkForNewPairs(oldState, newState, playerId) {
    const oldPlayer = oldState?.players?.find(p => p.id === playerId);
    const newPlayer = newState?.players?.find(p => p.id === playerId);

    if (!oldPlayer || !newPlayer) return;

    const columns = [[0, 3], [1, 4], [2, 5]];

    for (const [top, bottom] of columns) {
        const wasPaired = this.isPaired(oldPlayer.cards, top, bottom);
        const nowPaired = this.isPaired(newPlayer.cards, top, bottom);

        if (!wasPaired && nowPaired) {
            // New pair formed!
            setTimeout(() => {
                this.celebratePair(playerId, top, bottom);
            }, window.TIMING?.celebration?.pairDelay || 50);
        }
    }
}

isPaired(cards, pos1, pos2) {
    const c1 = cards[pos1];
    const c2 = cards[pos2];
    return c1?.face_up && c2?.face_up && c1?.rank === c2?.rank;
}

celebratePair(playerId, pos1, pos2) {
    const cards = this.getCardElements(playerId, pos1, pos2);
    if (cards.length === 0) return;

    // Use CardAnimations to animate (or add method to CardAnimations)
    window.cardAnimations.celebratePair(cards[0], cards[1]);
}

// Add to CardAnimations class in card-animations.js:
celebratePair(cardElement1, cardElement2) {
    this.playSound('pair');

    const duration = window.TIMING?.celebration?.pairDuration || 400;

    [cardElement1, cardElement2].forEach(el => {
        if (!el) return;

        // Temporarily raise z-index so glow shows above adjacent cards
        el.style.zIndex = '10';

        anime({
            targets: el,
            boxShadow: [
                '0 0 0 0 rgba(255, 215, 0, 0)',
                '0 0 15px 8px rgba(255, 215, 0, 0.5)',
                '0 0 0 0 rgba(255, 215, 0, 0)'
            ],
            scale: [1, 1.05, 1],
            duration: duration,
            easing: 'easeOutQuad',
            complete: () => {
                el.style.zIndex = '';
            }
        });
    });
}

getCardElements(playerId, ...positions) {
    const elements = [];

    if (playerId === this.playerId) {
        const cards = this.playerCards.querySelectorAll('.card');
        for (const pos of positions) {
            if (cards[pos]) elements.push(cards[pos]);
        }
    } else {
        const area = this.opponentsRow.querySelector(
            `.opponent-area[data-player-id="${playerId}"]`
        );
        if (area) {
            const cards = area.querySelectorAll('.card');
            for (const pos of positions) {
                if (cards[pos]) elements.push(cards[pos]);
            }
        }
    }

    return elements;
}
```

### CSS

No CSS keyframes needed - all animation is handled by anime.js in `CardAnimations.celebratePair()`.

The animation temporarily sets `z-index: 10` on cards during celebration to ensure the glow shows above adjacent cards. For opponent pairs, you can pass a different color parameter:

```javascript
// Optional: Different color for opponent pairs
celebratePair(cardElement1, cardElement2, isOpponent = false) {
    const color = isOpponent
        ? 'rgba(100, 200, 255, 0.4)'  // Blue for opponents
        : 'rgba(255, 215, 0, 0.5)';    // Gold for local player

    // ... anime.js animation with color ...
}
```

---

## Edge Cases

### Pair Broken Then Reformed

If a swap breaks one pair and creates another:
- Only celebrate the new pair
- Don't mourn the broken pair (no negative feedback)

### Multiple Pairs in One Move

Theoretically possible (swap creates pairs in adjacent columns):
- Celebrate all new pairs simultaneously
- Same sound, same animation on all involved cards

### Pair at Round Start (Initial Flip)

If initial flip creates a pair:
- Yes, celebrate it! Early luck deserves recognition

### Negative Card Pairs (2s, Jokers)

Pairing 2s or Jokers is strategically bad (wastes -2 value), but:
- Still celebrate the pair (it's mechanically correct)
- Player will learn the strategy over time
- Consider: different sound/color for "bad" pairs? (Too complex for V3)

---

## Test Scenarios

1. **Local player creates pair** - Both cards glow, sound plays
2. **Opponent creates pair** - Their cards glow, sound plays
3. **Initial flip creates pair** - Celebration after flip animation
4. **Swap breaks one pair, creates another** - Only new pair celebrates
5. **No pair formed** - No celebration
6. **Face-down card in column** - No false celebration

---

## Acceptance Criteria

- [ ] Swap that creates a pair triggers celebration
- [ ] Flip that creates a pair triggers celebration
- [ ] Both paired cards animate simultaneously
- [ ] Distinct "pair" sound plays
- [ ] Animation is brief (~400ms)
- [ ] Works for local player and opponents
- [ ] No celebration when pair isn't formed
- [ ] No celebration for already-existing pairs
- [ ] Animation doesn't block gameplay

---

## Implementation Order

1. Add `pair` sound to `playSound()` method
2. Add celebration timing to `timing-config.js`
3. Implement `isPaired()` helper method
4. Implement `checkForNewPairs()` method
5. Implement `celebratePair()` method
6. Implement `getCardElements()` helper
7. Add CSS animation for pair celebration
8. Integrate into state change detection
9. Test all pair formation scenarios
10. Tune sound and timing for satisfaction

---

## Notes for Agent

- Add `celebratePair()` method to the existing `CardAnimations` class
- Use anime.js for all animation - no CSS keyframes
- Keep the celebration brief - shouldn't slow down fast players
- The glow color (gold) suggests "success" - matches golf scoring concept
- Consider accessibility: animation should be visible but not overwhelming
- The existing swap animation completes before pair check runs
- Don't celebrate pairs that already existed before the action
- Opponent celebration can use slightly different color (optional parameter)
