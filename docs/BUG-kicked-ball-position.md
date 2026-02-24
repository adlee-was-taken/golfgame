# BUG: Kicked ball animation starts from golfer's back foot

## Problem

The `⚪` kicked ball animation (`.kicked-ball`) appears to launch from the golfer's **back foot** (left side) instead of the **front foot** (right side). The golfer faces right in both landscape (two-row) and mobile (single-line) views due to `scaleX(-1)`.

## What we want

The ball should appear at the golfer's front foot (right side) and arc up and to the right — matching the "good" landscape behavior seen at wide desktop widths (~1100px+).

## Good reference

- Video: `good.mp4` (landscape wide view)
- Extracted frames: `/tmp/golf-frames-good/`
- Frame 025: Ball clearly appears to the RIGHT of the golfer, arcing up-right

## Bad behavior

- Videos: `Screencast_20260224_005555.mp4`, `Screencast_20260224_013326.mp4`
- The ball appears to the LEFT of the golfer (between the golf ball logo and golfer emoji)
- Happens at the user's phone viewport width (two-row layout, inline-grid)

## Root cause analysis

### The scaleX(-1) offset problem

The golfer emoji (`.golfer-swing`) has `transform: scaleX(-1)` which flips it visually. This means:
- The golfer's **layout box** occupies the same inline flow position
- But the **visual** left/right is flipped — the front foot (visually on the right) is at the LEFT edge of the layout box
- The `.kicked-ball` span comes right after `.golfer-swing` in inline flow, so its natural position is at the **right edge** of the golfer's layout box
- But due to `scaleX(-1)`, the right edge of the layout box is the golfer's **visual back** (left side)
- So `translate(0, 0)` places the ball at the golfer's back, not front

### CSS translate values tested

| Start X | Result |
|---------|--------|
| `-30px` (original) | Ball appears way behind golfer (further left) |
| `+20px` | Ball still appears to LEFT of golfer, but slightly closer |
| `+80px` | Not confirmed (staging 404 during test) |

### Key finding: The kicked-ball's natural position needs ~60-80px positive X offset to reach the golfer's visual front foot

The golfer emoji is roughly 30-40px wide at this viewport. Since `scaleX(-1)` flips the visual, the ball needs to translate **past the entire emoji width** to reach the visual front.

### Media query issues encountered

1. First attempt: Added `ball-kicked-mobile` keyframes with `@media (max-width: 500px)` override
2. **CSS source order bug**: The mobile override at line 144 was being overridden by the base `.kicked-ball` rule at line 216 (later = higher priority at equal specificity)
3. Moved override after base rule — still didn't work
4. Added `!important` — still didn't work
5. Raised breakpoint from 500px to 768px, then 1200px — still no visible change
6. **Breakthrough**: Added `outline: 3px solid red; background: yellow` debug styles to base `.kicked-ball` — these DID appear, confirming CSS was loading
7. Changed base `ball-kicked` keyframes from `-30px` to `+20px` — ball DID move, confirming the base keyframes are what's being used
8. The mobile override keyframes may never have been applied (unclear if `ball-kicked-mobile` was actually used)

### What the Chrome extension Claude analysis said

> "The breakpoint is 500px, but the viewport is above 500px. At 700px+, ball-kicked-mobile never kicks in — it still uses the desktop ball-kicked animation. But the layout at this width has already shifted to a more centered layout which changes where .kicked-ball is positioned relative to the golfer."

## Suggested fix approach

1. **Don't use separate mobile keyframes** — just fix the base `ball-kicked` to work at all viewport widths
2. The starting X needs to be **much larger positive** (60-80px) to account for `scaleX(-1)` placing the natural position at the golfer's visual back
3. Alternatively, restructure the HTML: move `.kicked-ball` BEFORE `.golfer-swing` in the DOM, so its natural inline position is at the golfer's visual front (since scaleX(-1) flips left/right)
4. Or use `position: absolute` on `.kicked-ball` and position it relative to the golfer container explicitly

## Files involved

- `client/style.css` — `.kicked-ball`, `@keyframes ball-kicked`, `.golfer-swing`
- `client/index.html` — line 19: `<span class="golfer-swing">🏌️</span><span class="kicked-ball">⚪</span>`

## Current state (reverted to clean)

All debug styles removed. Base keyframes restored to original `translate(-30px, 8px)` start. No mobile override keyframes. The bug still exists but the code is clean.

## Extracted frames for reference

- `/tmp/golf-frames-good/` — good landscape behavior (from `good.mp4`)
- `/tmp/golf-frames-bad/` — bad behavior (from old video)
- `/tmp/golf-frames-new/` — debug session with red outline (from `Screencast_20260224_013326.mp4`)
