# Golf Card Game - V3 Master Plan

## Overview

Transform the current Golf card game into a more natural, physical-feeling experience through enhanced animations, visual feedback, and gameplay flow improvements. The goal is to make the digital game feel as satisfying as playing with real cards.

**Theme:** "Make it feel like a real card game"

---

## Document Structure (VDD)

This plan is split into independent vertical slices ordered by priority and impact. Each document is self-contained and can be worked on by a separate agent.

| Document | Scope | Priority | Effort | Dependencies |
|----------|-------|----------|--------|--------------|
| `V3_01_DEALER_ROTATION.md` | Rotate dealer/first player each round | High | Low | None (server change) |
| `V3_02_DEALING_ANIMATION.md` | Animated card dealing at round start | High | Medium | 01 |
| `V3_03_ROUND_END_REVEAL.md` | Dramatic sequential card reveal | High | Medium | None |
| `V3_04_COLUMN_PAIR_CELEBRATION.md` | Visual feedback for matching pairs | High | Low | None |
| `V3_05_FINAL_TURN_URGENCY.md` | Enhanced final turn visual tension | High | Low | None |
| `V3_06_OPPONENT_THINKING.md` | Visible opponent consideration phase | Medium | Low | None |
| `V3_07_SCORE_TALLYING.md` | Animated score counting | Medium | Medium | 03 |
| `V3_08_CARD_HOVER_SELECTION.md` | Enhanced card selection preview | Medium | Low | None |
| `V3_09_KNOCK_EARLY_DRAMA.md` | Dramatic knock early presentation | Medium | Low | None |
| `V3_10_COLUMN_PAIR_INDICATOR.md` | Visual connector for paired columns | Medium | Low | 04 |
| `V3_11_SWAP_ANIMATION_IMPROVEMENTS.md` | More physical swap motion | Medium | Medium | None |
| `V3_12_DRAW_SOURCE_DISTINCTION.md` | Visual distinction deck vs discard draw | Low | Low | None |
| `V3_13_CARD_VALUE_TOOLTIPS.md` | Long-press card value display | Low | Medium | None |
| `V3_14_ACTIVE_RULES_CONTEXT.md` | Contextual rule highlighting | Low | Low | None |
| `V3_15_DISCARD_PILE_HISTORY.md` | Show recent discards fanned | Low | Medium | None |
| `V3_16_REALISTIC_CARD_SOUNDS.md` | Improved audio feedback | Nice | Medium | None |
| `V3_17_MOBILE_PORTRAIT_LAYOUT.md` | Full mobile portrait layout + animation fixes | High | High | 02, 11 |

---

## Current State (V2)

```
Client (Vanilla JS)
├── app.js              - Main game logic (2500+ lines)
├── card-manager.js     - DOM card element management (3D flip structure)
├── animation-queue.js  - Sequential animation processing
├── card-animations.js  - Unified anime.js animation system (replaces draw-animations.js)
├── state-differ.js     - State change detection
├── timing-config.js    - Centralized animation timing + anime.js easing config
├── anime.min.js        - Anime.js library for all animations
└── style.css           - Minimal CSS, mostly layout
```

**What works well:**
- **Unified anime.js system** - All card animations use `window.cardAnimations` (CardAnimations class)
- State diffing detects changes and triggers appropriate animations
- Animation queue ensures sequential, non-overlapping animations
- Centralized timing config with anime.js easing presets (`TIMING.anime.easing`)
- Sound effects via Web Audio API
- CardAnimations provides: draw, flip, swap, discard, ambient loops (turn pulse, CPU thinking)
- Opponent turn visibility with CPU action announcements

**Limitations:**
- Cards appear instantly at round start (no dealing animation)
- Round end reveals all cards simultaneously
- No visual celebration for column pairs
- Final turn phase lacks urgency/tension
- Swap animation uses crossfade rather than physical motion
- Limited feedback during card selection
- Discard pile shows only top card

---

## V3 Target Experience

### Physical Card Game Feel Checklist

| Aspect | Physical Game | Current Digital | V3 Target |
|--------|---------------|-----------------|-----------|
| **Dealer Rotation** | Deal passes clockwise each round | Always starts with host | Rotating dealer/first player |
| **Dealing** | Cards dealt one at a time | Cards appear instantly | Animated dealing sequence |
| **Drawing** | Card lifts, player considers | Card pops in | Source-appropriate pickup |
| **Swapping** | Old card slides out, new slides in | Teleport swap | Cross-over motion |
| **Pairing** | "Nice!" moment when match noticed | No feedback | Visual celebration |
| **Round End** | Dramatic reveal, one player at a time | All cards flip at once | Staggered reveal |
| **Scoring** | Count card by card | Score appears | Animated tally |
| **Final Turn** | Tension in the room | Badge shows | Visual urgency |
| **Sounds** | Shuffle, flip, slap | Synth beeps | Realistic card sounds |

---

## Tech Approach

### Animation Strategy

All **card animations** use the unified `CardAnimations` class (`card-animations.js`):
- **Anime.js timelines** for all card animations (flip, swap, draw, discard)
- **CardAnimations methods** - `animateDrawDeck()`, `animateFlip()`, `animateSwap()`, etc.
- **Ambient loops** - `startTurnPulse()`, `startCpuThinking()`, `startInitialFlipPulse()`
- **One-shot effects** - `pulseDiscard()`, `pulseSwap()`, `popIn()`
- **Animation queue** for sequencing multi-step animations
- **State differ** to trigger animations on state changes

**When to use CSS vs anime.js:**
- **Anime.js (CardAnimations)**: Card movements, flips, swaps, draws - anything involving card elements
- **CSS keyframes/transitions**: Simple UI feedback (button hover, badge entrance, status message fades) - non-card elements

**General rule:** If it moves a card, use anime.js. If it's UI chrome, CSS is fine.

### Timing Philosophy

From `timing-config.js`:
```javascript
// Current values - animations are smooth but quick
card: {
    flip: 400,    // Card flip duration
    move: 400,    // Card movement
},
pause: {
    afterFlip: 0,      // No pause - flow into next action
    betweenAnimations: 0,  // No gaps
},
// Anime.js easing presets
anime: {
    easing: {
        flip: 'easeInOutQuad',
        move: 'easeOutCubic',
        lift: 'easeOutQuad',
        pulse: 'easeInOutSine',
    },
    loop: {
        turnPulse: { duration: 2000 },
        cpuThinking: { duration: 1500 },
        initialFlipGlow: { duration: 1500 },
    }
}
```

V3 will introduce **optional pauses for drama** without slowing normal gameplay:
- Quick pauses at key moments (pair formed, round end)
- Staggered timing for dealing/reveal (perceived faster than actual)
- User preference for animation speed (future consideration)

### Sound Strategy

Current sounds are oscillator-based (Web Audio API synthesis). V3 options:
1. **Enhanced synthesis** - More realistic waveforms, envelopes
2. **Audio sprites** - Short recordings of real card sounds
3. **Hybrid** - Synthesis for some, samples for others

Recommendation: Start with enhanced synthesis (no asset loading), consider audio sprites later.

---

## Phases & Milestones

### Phase 1: Core Feel (High Priority)
**Goal:** Make the game feel noticeably more physical

| Item | Description | Document |
|------|-------------|----------|
| Dealer rotation | First player rotates each round (like real cards) | 01 |
| Dealing animation | Cards dealt sequentially at round start | 02 |
| Round end reveal | Dramatic staggered flip at round end | 03 |
| Column pair celebration | Glow/pulse when pairs form | 04 |
| Final turn urgency | Visual tension enhancement | 05 |

### Phase 2: Turn Polish (Medium Priority)
**Goal:** Improve the feel of individual turns

| Item | Description | Document |
|------|-------------|----------|
| Opponent thinking | Visible consideration phase | 06 |
| Score tallying | Animated counting | 07 |
| Card hover/selection | Better swap preview | 08 |
| Knock early drama | Dramatic knock presentation | 09 |
| Column pair indicator | Visual pair connector | 10 |
| Swap improvements | Physical swap motion | 11 |

### Phase 3: Polish & Extras (Low Priority)
**Goal:** Nice-to-have improvements

| Item | Description | Document |
|------|-------------|----------|
| Draw distinction | Deck vs discard visual difference | 12 |
| Card value tooltips | Long-press to see points | 13 |
| Active rules context | Highlight relevant rules | 14 |
| Discard history | Show fanned recent cards | 15 |
| Realistic sounds | Better audio feedback | 16 |

---

## File Structure (Changes)

```
server/
├── game.py                   # Add dealer rotation logic (V3_01)

client/
├── app.js                    # Enhance existing methods
├── timing-config.js          # Add new timing values + anime.js config
├── card-animations.js        # Extend with new animation methods
├── animation-queue.js        # Add new animation types
├── style.css                 # Minimal additions (mostly layout)
└── sounds/                   # OPTIONAL: Audio sprites
    ├── shuffle.mp3
    ├── deal.mp3
    └── flip.mp3
```

**Note:** All new animations should be added to `CardAnimations` class in `card-animations.js`. Do not add CSS keyframe animations for card movements.

---

## Acceptance Criteria (V3 Complete)

1. **Dealer rotates properly** - First player advances clockwise each round
2. **Dealing feels physical** - Cards dealt one by one with shuffle sound
3. **Round end is dramatic** - Staggered reveal with tension pause
4. **Pairs are satisfying** - Visual celebration when columns match
5. **Final turn has urgency** - Clear visual indication of tension
6. **Swaps look natural** - Cards appear to exchange positions
7. **No performance regression** - Animations run at 60fps on mobile
8. **Timing is tunable** - All values in timing-config.js

---

## Design Principles

### 1. Enhance, Don't Slow Down
Animations should make the game feel better without making it slower. Use perceived timing tricks:
- Start next animation before previous fully completes
- Stagger start times, not end times
- Quick movements with slight ease-out

### 2. Respect the Player's Time
- First-time experience: full animations
- Repeat plays: consider faster mode option
- Never block input unnecessarily

### 3. Clear Visual Hierarchy
- Active player highlighted
- Current action obvious
- Next expected action hinted

### 4. Consistent Feedback
- Same action = same animation
- Similar duration for similar actions
- Predictable timing helps player flow

### 5. Graceful Degradation
- Animations enhance but aren't required
- State updates should work without animations
- Handle animation interruption gracefully

---

## How to Use These Documents

Each `V3_XX_*.md` document is designed to be:

1. **Self-contained** - Has all context needed to implement that feature
2. **Agent-ready** - Can be given to a Claude agent as the primary context
3. **Testable** - Includes visual verification criteria
4. **Incremental** - Can be implemented and shipped independently

**Workflow:**
1. Pick a document based on current priority
2. Start a new Claude session with that document as context
3. Implement the feature
4. Verify against acceptance criteria
5. Test on mobile and desktop
6. Merge and move to next

---

## Notes for Implementation

- **Don't break existing functionality** - All current animations must still work
- **Use existing infrastructure** - Build on animation-queue, timing-config
- **Test on mobile** - Animations must run smoothly on phones
- **Consider reduced motion** - Respect `prefers-reduced-motion` media query
- **Keep it vanilla** - No new frameworks, Anime.js is sufficient

---

## Success Metrics

After V3 implementation, the game should:
- Feel noticeably more satisfying to play
- Get positive feedback on "polish" or "feel"
- Not feel slower despite more animations
- Work smoothly on all devices
- Be easy to tune timing via config
