# Golf Card Game - Project Context

A real-time multiplayer 6-card Golf card game with CPU opponents and smooth anime.js animations.

## Quick Start

```bash
# Install dependencies
pip install -r server/requirements.txt

# Run the server
python server/main.py

# Visit http://localhost:5000
```

## Architecture

```
golfgame/
├── server/           # Python FastAPI backend
│   ├── main.py       # HTTP routes, WebSocket handling
│   ├── game.py       # Game logic, state machine
│   └── ai.py         # CPU opponent AI with timing/personality
│
├── client/           # Vanilla JS frontend
│   ├── app.js        # Main game controller
│   ├── card-animations.js  # Unified anime.js animation system
│   ├── card-manager.js     # DOM management for cards
│   ├── animation-queue.js  # Animation sequencing
│   ├── timing-config.js    # Centralized timing configuration
│   ├── state-differ.js     # Diff game state for animations
│   ├── style.css           # Styles (NO card transitions)
│   └── ANIMATIONS.md       # Animation system documentation
│
└── docs/v3/          # Feature planning documents
```

## Key Technical Decisions

### Animation System

**All card animations use anime.js.** No CSS transitions on card elements.

- See `client/ANIMATIONS.md` for full documentation
- `CardAnimations` class in `card-animations.js` handles everything
- Timing configured in `timing-config.js`

### State Management

- Server is source of truth
- Client receives full game state on each update
- `state-differ.js` computes diffs to trigger appropriate animations
- `isDrawAnimating` flag prevents UI updates during animations

### CPU Players

- AI logic in `server/ai.py`
- Configurable timing delays for natural feel
- Multiple personality types affect decision-making

## Common Development Tasks

### Adjusting Animation Speed

Edit `timing-config.js` - all timings are centralized there.

### Adding New Animations

1. Add method to `CardAnimations` class in `card-animations.js`
2. Use anime.js, not CSS transitions
3. Track in `activeAnimations` Map for cancellation support
4. Add timing config to `timing-config.js` if needed

### Debugging Animations

```javascript
// Check what's animating
console.log(window.cardAnimations.activeAnimations);

// Force cleanup
window.cardAnimations.cancelAll();

// Check timing config
console.log(window.TIMING);
```

### Testing CPU Behavior

Adjust delays in `server/ai.py` `CPU_TIMING` dict.

## Important Patterns

### No CSS Transitions on Cards

Cards animate via anime.js only. The following should NOT have `transition`:
- `.card`, `.card-inner`
- `.real-card`, `.swap-card`
- `.held-card-floating`

### Animation Overlays

Complex animations create temporary overlay elements:
1. Create `.draw-anim-card` positioned over source
2. Hide original card
3. Animate overlay
4. Remove overlay, reveal updated card

### Fire-and-Forget for Opponents

Opponent animations don't block - no callbacks needed:
```javascript
cardAnimations.animateOpponentFlip(cardElement, cardData);
```

## Dependencies

### Server
- FastAPI
- uvicorn
- websockets

### Client
- anime.js (animations)
- No other frameworks

## Game Rules Reference

- 6 cards per player in 2x3 grid
- Lower score wins
- Matching columns cancel out (0 points)
- Jokers are -2 points
- Kings are 0 points
- Game ends when a player flips all cards
