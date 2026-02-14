# V3-09: Knock Early Drama

## Overview

The "Knock Early" house rule lets players flip all remaining face-down cards (if 2 or fewer) to immediately trigger final turn. This is a high-risk, high-reward move that deserves dramatic presentation.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Make knock early feel dramatic and consequential
2. Show confirmation dialog (optional - it's risky!)
3. Dramatic animation when knock happens
4. Clear feedback showing the decision
5. Other players see "Player X knocked early!"

---

## Current State

From `app.js`:
```javascript
knockEarly() {
    if (!this.gameState || !this.gameState.knock_early) return;
    this.send({ type: 'knock_early' });
    this.hideToast();
}
```

The knock early button exists but there's no special visual treatment.

---

## Design

### Knock Early Flow

```
1. Player clicks "Knock Early" button
2. Confirmation prompt: "Reveal your hidden cards and go out?"
3. If confirmed:
   a. Dramatic sound effect
   b. Player's hidden cards flip rapidly in sequence
   c. "KNOCK!" banner appears
   d. Final turn badge triggers
4. Other players see announcement
```

### Visual Elements

- **Confirmation dialog** - "Are you sure?" with preview
- **Rapid flip animation** - Cards flip faster than normal
- **"KNOCK!" banner** - Large dramatic announcement
- **Screen shake** (subtle) - Impact feeling

---

## Implementation

### Confirmation Dialog

```javascript
knockEarly() {
    if (!this.gameState || !this.gameState.knock_early) return;

    // Count hidden cards
    const myData = this.getMyPlayerData();
    const hiddenCards = myData.cards.filter(c => !c.face_up);

    if (hiddenCards.length === 0 || hiddenCards.length > 2) {
        return; // Can't knock
    }

    // Show confirmation
    this.showKnockConfirmation(hiddenCards.length, () => {
        this.executeKnockEarly();
    });
}

showKnockConfirmation(hiddenCount, onConfirm) {
    // Create modal
    const modal = document.createElement('div');
    modal.className = 'knock-confirm-modal';
    modal.innerHTML = `
        <div class="knock-confirm-content">
            <div class="knock-confirm-icon">⚡</div>
            <h3>Knock Early?</h3>
            <p>You'll reveal ${hiddenCount} hidden card${hiddenCount > 1 ? 's' : ''} and trigger final turn.</p>
            <p class="knock-warning">This cannot be undone!</p>
            <div class="knock-confirm-buttons">
                <button class="btn btn-secondary knock-cancel">Cancel</button>
                <button class="btn btn-primary knock-confirm">Knock!</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Bind events
    modal.querySelector('.knock-cancel').addEventListener('click', () => {
        this.playSound('click');
        modal.remove();
    });

    modal.querySelector('.knock-confirm').addEventListener('click', () => {
        this.playSound('click');
        modal.remove();
        onConfirm();
    });

    // Click outside to cancel
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.remove();
        }
    });
}

async executeKnockEarly() {
    // Play dramatic sound
    this.playSound('knock');

    // Get positions of hidden cards
    const myData = this.getMyPlayerData();
    const hiddenPositions = myData.cards
        .map((card, i) => ({ card, position: i }))
        .filter(({ card }) => !card.face_up)
        .map(({ position }) => position);

    // Start rapid flip animation
    await this.animateKnockFlips(hiddenPositions);

    // Show KNOCK banner
    this.showKnockBanner();

    // Send to server
    this.send({ type: 'knock_early' });
    this.hideToast();
}

async animateKnockFlips(positions) {
    // Rapid sequential flips
    const flipDelay = 150; // Faster than normal

    for (const position of positions) {
        const myData = this.getMyPlayerData();
        const card = myData.cards[position];
        this.fireLocalFlipAnimation(position, card);
        this.playSound('flip');
        await this.delay(flipDelay);
    }

    // Wait for last flip
    await this.delay(300);
}

showKnockBanner() {
    const banner = document.createElement('div');
    banner.className = 'knock-banner';
    banner.innerHTML = '<span>KNOCK!</span>';
    document.body.appendChild(banner);

    // Screen shake effect
    document.body.classList.add('screen-shake');

    // Remove after animation
    setTimeout(() => {
        banner.classList.add('fading');
        document.body.classList.remove('screen-shake');
    }, 800);

    setTimeout(() => {
        banner.remove();
    }, 1100);
}
```

### CSS

```css
/* Knock confirmation modal */
.knock-confirm-modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 300;
    animation: modal-fade-in 0.2s ease-out;
}

@keyframes modal-fade-in {
    0% { opacity: 0; }
    100% { opacity: 1; }
}

.knock-confirm-content {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    padding: 30px;
    border-radius: 15px;
    text-align: center;
    max-width: 320px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
    animation: modal-scale-in 0.2s ease-out;
}

@keyframes modal-scale-in {
    0% { transform: scale(0.9); }
    100% { transform: scale(1); }
}

.knock-confirm-icon {
    font-size: 3em;
    margin-bottom: 10px;
}

.knock-confirm-content h3 {
    margin: 0 0 15px;
    color: #f4a460;
}

.knock-confirm-content p {
    margin: 0 0 10px;
    color: rgba(255, 255, 255, 0.8);
}

.knock-warning {
    color: #e74c3c !important;
    font-size: 0.9em;
}

.knock-confirm-buttons {
    display: flex;
    gap: 10px;
    margin-top: 20px;
}

.knock-confirm-buttons .btn {
    flex: 1;
}

/* KNOCK banner */
.knock-banner {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) scale(0);
    z-index: 400;
    pointer-events: none;
    animation: knock-banner-in 0.3s ease-out forwards;
}

.knock-banner span {
    display: block;
    font-size: 4em;
    font-weight: 900;
    color: #f4a460;
    text-shadow:
        0 0 20px rgba(244, 164, 96, 0.8),
        0 0 40px rgba(244, 164, 96, 0.4),
        2px 2px 0 #1a1a2e;
    letter-spacing: 0.2em;
}

@keyframes knock-banner-in {
    0% {
        transform: translate(-50%, -50%) scale(0);
        opacity: 0;
    }
    50% {
        transform: translate(-50%, -50%) scale(1.2);
        opacity: 1;
    }
    100% {
        transform: translate(-50%, -50%) scale(1);
        opacity: 1;
    }
}

.knock-banner.fading {
    animation: knock-banner-out 0.3s ease-out forwards;
}

@keyframes knock-banner-out {
    0% {
        transform: translate(-50%, -50%) scale(1);
        opacity: 1;
    }
    100% {
        transform: translate(-50%, -50%) scale(0.8);
        opacity: 0;
    }
}

/* Screen shake effect */
@keyframes screen-shake {
    0%, 100% { transform: translateX(0); }
    20% { transform: translateX(-3px); }
    40% { transform: translateX(3px); }
    60% { transform: translateX(-2px); }
    80% { transform: translateX(2px); }
}

body.screen-shake {
    animation: screen-shake 0.3s ease-out;
}

/* Enhanced knock early button */
#knock-early-btn {
    background: linear-gradient(135deg, #ff6b35 0%, #d63031 100%);
    animation: knock-btn-pulse 2s ease-in-out infinite;
}

@keyframes knock-btn-pulse {
    0%, 100% {
        box-shadow: 0 2px 10px rgba(214, 48, 49, 0.3);
    }
    50% {
        box-shadow: 0 2px 20px rgba(214, 48, 49, 0.5);
    }
}
```

### Knock Sound

```javascript
// In playSound() method
} else if (type === 'knock') {
    // Dramatic "knock" sound - low thud
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.type = 'sine';
    osc.frequency.setValueAtTime(80, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(40, ctx.currentTime + 0.15);

    gain.gain.setValueAtTime(0.4, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);

    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.2);

    // Secondary impact
    setTimeout(() => {
        const osc2 = ctx.createOscillator();
        const gain2 = ctx.createGain();
        osc2.connect(gain2);
        gain2.connect(ctx.destination);
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(60, ctx.currentTime);
        gain2.gain.setValueAtTime(0.2, ctx.currentTime);
        gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
        osc2.start(ctx.currentTime);
        osc2.stop(ctx.currentTime + 0.1);
    }, 100);
}
```

### Opponent Sees Knock

When another player knocks, show announcement:

```javascript
// In state change detection or game_state handler

if (newState.phase === 'final_turn' && oldState?.phase !== 'final_turn') {
    const knocker = newState.players.find(p => p.id === newState.finisher_id);
    if (knocker && knocker.id !== this.playerId) {
        // Someone else knocked
        this.showOpponentKnockAnnouncement(knocker.name);
    }
}

showOpponentKnockAnnouncement(playerName) {
    this.playSound('alert');

    const banner = document.createElement('div');
    banner.className = 'opponent-knock-banner';
    banner.innerHTML = `<span>${playerName} knocked!</span>`;
    document.body.appendChild(banner);

    setTimeout(() => {
        banner.classList.add('fading');
    }, 1500);

    setTimeout(() => {
        banner.remove();
    }, 1800);
}
```

---

## Test Scenarios

1. **Knock with 1 hidden card** - Single flip, then knock banner
2. **Knock with 2 hidden cards** - Rapid double flip
3. **Cancel confirmation** - Modal closes, no action
4. **Opponent knocks** - See announcement
5. **Can't knock (3+ hidden)** - Button disabled
6. **Can't knock (all face-up)** - Button disabled

---

## Acceptance Criteria

- [ ] Confirmation dialog appears before knock
- [ ] Dialog shows number of cards to reveal
- [ ] Cancel button works
- [ ] Knock triggers rapid flip animation
- [ ] "KNOCK!" banner appears with fanfare
- [ ] Subtle screen shake effect
- [ ] Other players see announcement
- [ ] Final turn triggers after knock
- [ ] Sound effects enhance the drama

---

## Implementation Order

1. Add knock sound to `playSound()`
2. Implement `showKnockConfirmation()` method
3. Implement `executeKnockEarly()` method
4. Implement `animateKnockFlips()` method
5. Implement `showKnockBanner()` method
6. Add CSS for modal and banner
7. Implement opponent knock announcement
8. Add screen shake effect
9. Test all scenarios
10. Tune timing for maximum drama

---

## Notes for Agent

- **CSS vs anime.js**: CSS is fine for modal/button animations (UI chrome). Screen shake can use anime.js for precision.
- The confirmation prevents accidental knocks (it's irreversible)
- Keep animation fast - drama without delay
- The screen shake should be subtle (accessibility)
- Consider: skip confirmation option for experienced players?
- Make sure knock works even if animations fail
