# V3.17: Mobile Portrait Layout

**Version:** 3.1.1
**Commits:** `4fcdf13`, `fb3bd53`

## Overview

Full mobile portrait layout for phones, triggered by JS `matchMedia` on narrow portrait screens (`max-width: 500px`, `orientation: portrait`). The desktop layout is completely untouched — all mobile rules are scoped under `body.mobile-portrait`.

## Key Features

### Responsive Game Layout
- Viewport fills 100dvh with no scroll; `overscroll-behavior: contain` prevents pull-to-refresh
- Game screen uses flexbox column: compact header → opponents row → player row → bottom bar
- Safe-area insets respected for notched devices (`env(safe-area-inset-top/bottom)`)

### Compact Header
- Single-row header with reduced font sizes (0.75rem) and tight gaps
- Non-essential items hidden on mobile: username display, logout button, active rules bar
- Status message, round info, final turn badge, and leave button all use `white-space: nowrap` with ellipsis overflow

### Opponent Cards
- Flat horizontal strip (no arch rotation) with horizontal scroll for 4+ opponents
- Cards scaled to 32x45px with 0.6rem font (26x36px on short screens)
- Dealer chip scaled from 38px to 20px diameter to fit compact opponent areas
- Showing score badge sized proportionally

### Deck/Discard Area
- Deck and discard cards match player card size (72x101px) for visual consistency
- Held card floating matches player card size with proportional font scaling

### Player Cards
- Fixed 72x101px cards with 1.5rem font in 3-column grid
- 60x84px with 1.3rem font on short screens (max-height: 600px)
- Font size set inline by `card-manager.js` proportional to card width (0.35x ratio on mobile)

### Side Panels as Bottom Drawers
- Standings and scoreboard panels slide up as bottom drawers from a mobile bottom bar
- Drawer backdrop overlay with tap-to-dismiss
- Drag handle visual indicator on each drawer
- Drawers auto-close on screen change or layout change back to desktop

### Short Screen Fallback
- `@media (max-height: 600px)` reduces all card sizes, gaps, and padding
- Opponent cards: 26x36px, deck/discard: 60x84px, player cards: 60x84px

## Animation Fixes

### Deal Animation Guard
- `renderGame()` returns early when `dealAnimationInProgress` is true
- Prevents WebSocket state updates from destroying card slot DOM elements mid-deal animation
- Cards were piling up at (0,0) because `getCardSlotRect()` read stale/null positions after `innerHTML = ''`

### Animation Overlay Card Sizing
- **Root cause:** Base `.card` CSS (`width: clamp(65px, 5.5vw, 100px)`) was leaking into animation overlay elements (`.draw-anim-front.card`), overriding the intended `width: 100%` inherited from the overlay container
- **Effect:** Opponent flip overlays appeared at 65px instead of 32px (too big); deck/discard draw overlays appeared at 65px instead of 72px (too small)
- **Fix:** Added `!important` to `.draw-anim-front/.draw-anim-back` `width` and `height` rules to ensure animation overlays always match their parent container's inline dimensions from JavaScript

### Opponent Swap Held Card Sizing
- `fireSwapAnimation()` now passes a `heldRect` sized to match the opponent card (32px) positioned at the holding location, instead of defaulting to deck dimensions (72px)
- The traveling held card no longer appears oversized relative to opponent cards during the swap arc

### Font Size Consistency
- `cardFontSize()` helper in `CardAnimations` uses 0.35x width ratio on mobile (vs 0.5x desktop)
- Applied consistently across all animation paths: `createAnimCard`, `createCardFromData`, and arc swap font transitions
- Held card floating gets inline font-size scaled to card width on mobile

## CSS Architecture

All mobile rules use the `body.mobile-portrait` scope:

```css
/* Applied by JS matchMedia, not CSS media query */
body.mobile-portrait .selector { ... }

/* Short screen fallback uses both */
@media (max-height: 600px) {
    body.mobile-portrait .selector { ... }
}
```

Card sizing uses `!important` to override base `.card` clamp values:
```css
body.mobile-portrait .opponent-area .card {
    width: 32px !important;
    height: 45px !important;
}
```

Animation overlays use `!important` to override base `.card` leaking:
```css
.draw-anim-front,
.draw-anim-back {
    width: 100% !important;
    height: 100% !important;
}
```

## Files Modified

| File | Changes |
|------|---------|
| `client/style.css` | ~470 lines of mobile portrait CSS added at end of file |
| `client/app.js` | Mobile detection, drawer management, `renderGame()` guard, swap heldRect sizing, held card font scaling |
| `client/card-animations.js` | `cardFontSize()` helper, consistent font scaling across all animation paths |
| `client/card-manager.js` | Inline font-size on mobile for `updateCardElement()` |
| `client/index.html` | Mobile bottom bar, drawer backdrop, viewport-fit=cover |

## Testing

- **Desktop:** No visual changes — all rules scoped under `body.mobile-portrait`
- **Mobile portrait:** Verify game fits 100dvh, no scroll, cards properly sized
- **Deal animation:** Cards fly to correct grid positions (not piling up)
- **Draw/discard:** Animation overlay matches source card size
- **Opponent swap:** Flip and arc animations use opponent card dimensions
- **Short screens (iPhone SE):** All elements fit with reduced sizes
- **Orientation change:** Layout switches cleanly between mobile and desktop
