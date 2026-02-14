# V3-16: Realistic Card Sounds

## Overview

Current sounds use simple Web Audio oscillator beeps. Real card games have distinct sounds: shuffling, dealing, flipping, placing. This feature improves audio feedback to feel more physical.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Distinct sounds for each card action
2. Variation to avoid repetition fatigue
3. Physical "card" quality (paper, snap, thunk)
4. Volume control and mute option
5. Performant (Web Audio API synthesis or small samples)

---

## Current State

From `app.js` and `card-animations.js`:
```javascript
// app.js has the main playSound method
playSound(type) {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    // Simple beep tones for different actions
}

// CardAnimations routes to app.js via window.game.playSound()
playSound(type) {
    if (window.game && typeof window.game.playSound === 'function') {
        window.game.playSound(type);
    }
}
```

Sounds are functional but feel digital/arcade rather than physical. The existing sound types include:
- `card` - general card movement
- `flip` - card flip
- `shuffle` - deck shuffle

---

## Design

### Sound Palette

| Action | Sound Character | Notes |
|--------|-----------------|-------|
| Card flip | Sharp snap | Paper/cardboard flip |
| Card place | Soft thunk | Card landing on table |
| Card draw | Slide + lift | Taking from pile |
| Card shuffle | Multiple snaps | Riffle texture |
| Pair formed | Satisfying click | Success feedback |
| Knock | Table tap | Knuckle on table |
| Deal | Quick sequence | Multiple snaps |
| Turn notification | Subtle chime | Alert without jarring |
| Round end | Flourish | Resolution feel |

### Synthesis vs Samples

**Option A: Synthesized sounds (current approach, enhanced)**
- No external files needed
- Smaller bundle size
- More control over variations
- Can sound artificial

**Option B: Audio samples**
- More realistic
- Larger file size (small samples ~5-10KB each)
- Need to handle loading
- Can use Web Audio for variations

**Recommendation:** Hybrid - synthesized base with sample layering for key sounds.

---

## Implementation

### Enhanced Sound System

```javascript
// sound-system.js

class SoundSystem {
    constructor() {
        this.ctx = null;
        this.enabled = true;
        this.volume = 0.5;
        this.samples = {};
        this.initialized = false;
    }

    async init() {
        if (this.initialized) return;

        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        this.masterGain = this.ctx.createGain();
        this.masterGain.connect(this.ctx.destination);
        this.masterGain.gain.value = this.volume;

        // Load settings
        this.enabled = localStorage.getItem('soundEnabled') !== 'false';
        this.volume = parseFloat(localStorage.getItem('soundVolume') || '0.5');

        this.initialized = true;
    }

    setVolume(value) {
        this.volume = Math.max(0, Math.min(1, value));
        if (this.masterGain) {
            this.masterGain.gain.value = this.volume;
        }
        localStorage.setItem('soundVolume', this.volume.toString());
    }

    setEnabled(enabled) {
        this.enabled = enabled;
        localStorage.setItem('soundEnabled', enabled.toString());
    }

    async play(type) {
        if (!this.enabled) return;
        if (!this.ctx || this.ctx.state === 'suspended') {
            await this.ctx?.resume();
        }

        const now = this.ctx.currentTime;

        switch (type) {
            case 'flip':
                this.playFlip(now);
                break;
            case 'place':
            case 'discard':
                this.playPlace(now);
                break;
            case 'draw-deck':
                this.playDrawDeck(now);
                break;
            case 'draw-discard':
                this.playDrawDiscard(now);
                break;
            case 'pair':
                this.playPair(now);
                break;
            case 'knock':
                this.playKnock(now);
                break;
            case 'deal':
                this.playDeal(now);
                break;
            case 'shuffle':
                this.playShuffle(now);
                break;
            case 'turn':
                this.playTurn(now);
                break;
            case 'round-end':
                this.playRoundEnd(now);
                break;
            case 'win':
                this.playWin(now);
                break;
            default:
                this.playGeneric(now);
        }
    }

    // Card flip - sharp snap
    playFlip(now) {
        // White noise burst for paper snap
        const noise = this.createNoiseBurst(0.03, 0.02);

        // High frequency click
        const click = this.ctx.createOscillator();
        const clickGain = this.ctx.createGain();
        click.connect(clickGain);
        clickGain.connect(this.masterGain);

        click.type = 'square';
        click.frequency.setValueAtTime(2000 + Math.random() * 500, now);
        click.frequency.exponentialRampToValueAtTime(800, now + 0.02);

        clickGain.gain.setValueAtTime(0.15, now);
        clickGain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);

        click.start(now);
        click.stop(now + 0.05);
    }

    // Card place - soft thunk
    playPlace(now) {
        // Low thump
        const thump = this.ctx.createOscillator();
        const thumpGain = this.ctx.createGain();
        thump.connect(thumpGain);
        thumpGain.connect(this.masterGain);

        thump.type = 'sine';
        thump.frequency.setValueAtTime(150 + Math.random() * 30, now);
        thump.frequency.exponentialRampToValueAtTime(80, now + 0.08);

        thumpGain.gain.setValueAtTime(0.2, now);
        thumpGain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);

        thump.start(now);
        thump.stop(now + 0.1);

        // Soft noise
        this.createNoiseBurst(0.02, 0.04);
    }

    // Draw from deck - mysterious slide + flip
    playDrawDeck(now) {
        // Slide sound
        const slide = this.ctx.createOscillator();
        const slideGain = this.ctx.createGain();
        slide.connect(slideGain);
        slideGain.connect(this.masterGain);

        slide.type = 'triangle';
        slide.frequency.setValueAtTime(200, now);
        slide.frequency.exponentialRampToValueAtTime(400, now + 0.1);

        slideGain.gain.setValueAtTime(0.08, now);
        slideGain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);

        slide.start(now);
        slide.stop(now + 0.12);

        // Delayed flip
        setTimeout(() => this.playFlip(this.ctx.currentTime), 150);
    }

    // Draw from discard - quick grab
    playDrawDiscard(now) {
        const grab = this.ctx.createOscillator();
        const grabGain = this.ctx.createGain();
        grab.connect(grabGain);
        grabGain.connect(this.masterGain);

        grab.type = 'square';
        grab.frequency.setValueAtTime(600, now);
        grab.frequency.exponentialRampToValueAtTime(300, now + 0.04);

        grabGain.gain.setValueAtTime(0.1, now);
        grabGain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);

        grab.start(now);
        grab.stop(now + 0.05);
    }

    // Pair formed - satisfying double click
    playPair(now) {
        // Two quick clicks
        for (let i = 0; i < 2; i++) {
            const click = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            click.connect(gain);
            gain.connect(this.masterGain);

            click.type = 'triangle';
            click.frequency.setValueAtTime(800 + i * 200, now + i * 0.08);

            gain.gain.setValueAtTime(0.15, now + i * 0.08);
            gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.08 + 0.06);

            click.start(now + i * 0.08);
            click.stop(now + i * 0.08 + 0.06);
        }
    }

    // Knock - table tap
    playKnock(now) {
        // Low woody thunk
        const knock = this.ctx.createOscillator();
        const knockGain = this.ctx.createGain();
        knock.connect(knockGain);
        knockGain.connect(this.masterGain);

        knock.type = 'sine';
        knock.frequency.setValueAtTime(120, now);
        knock.frequency.exponentialRampToValueAtTime(60, now + 0.1);

        knockGain.gain.setValueAtTime(0.3, now);
        knockGain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);

        knock.start(now);
        knock.stop(now + 0.15);

        // Resonance
        const resonance = this.ctx.createOscillator();
        const resGain = this.ctx.createGain();
        resonance.connect(resGain);
        resGain.connect(this.masterGain);

        resonance.type = 'triangle';
        resonance.frequency.setValueAtTime(180, now);

        resGain.gain.setValueAtTime(0.1, now);
        resGain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);

        resonance.start(now);
        resonance.stop(now + 0.2);
    }

    // Deal - rapid card sequence
    playDeal(now) {
        // Multiple quick snaps
        for (let i = 0; i < 4; i++) {
            setTimeout(() => {
                const snap = this.ctx.createOscillator();
                const gain = this.ctx.createGain();
                snap.connect(gain);
                gain.connect(this.masterGain);

                snap.type = 'square';
                snap.frequency.setValueAtTime(1500 + Math.random() * 300, this.ctx.currentTime);

                gain.gain.setValueAtTime(0.08, this.ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.03);

                snap.start(this.ctx.currentTime);
                snap.stop(this.ctx.currentTime + 0.03);
            }, i * 80);
        }
    }

    // Shuffle - riffle texture
    playShuffle(now) {
        // Many tiny clicks with frequency variation
        for (let i = 0; i < 12; i++) {
            setTimeout(() => {
                this.createNoiseBurst(0.01, 0.01 + Math.random() * 0.02);
            }, i * 40 + Math.random() * 20);
        }
    }

    // Turn notification - gentle chime
    playTurn(now) {
        const freqs = [523, 659]; // C5, E5

        freqs.forEach((freq, i) => {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.connect(gain);
            gain.connect(this.masterGain);

            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, now + i * 0.1);

            gain.gain.setValueAtTime(0.1, now + i * 0.1);
            gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.1 + 0.3);

            osc.start(now + i * 0.1);
            osc.stop(now + i * 0.1 + 0.3);
        });
    }

    // Round end - resolution flourish
    playRoundEnd(now) {
        const freqs = [392, 494, 587, 784]; // G4, B4, D5, G5

        freqs.forEach((freq, i) => {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.connect(gain);
            gain.connect(this.masterGain);

            osc.type = 'triangle';
            osc.frequency.setValueAtTime(freq, now + i * 0.08);

            gain.gain.setValueAtTime(0.12, now + i * 0.08);
            gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.08 + 0.4);

            osc.start(now + i * 0.08);
            osc.stop(now + i * 0.08 + 0.4);
        });
    }

    // Win celebration
    playWin(now) {
        const freqs = [523, 659, 784, 1047]; // C5, E5, G5, C6

        freqs.forEach((freq, i) => {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.connect(gain);
            gain.connect(this.masterGain);

            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, now + i * 0.12);

            gain.gain.setValueAtTime(0.15, now + i * 0.12);
            gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.12 + 0.5);

            osc.start(now + i * 0.12);
            osc.stop(now + i * 0.12 + 0.5);
        });
    }

    // Generic click
    playGeneric(now) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.connect(gain);
        gain.connect(this.masterGain);

        osc.type = 'triangle';
        osc.frequency.setValueAtTime(440, now);

        gain.gain.setValueAtTime(0.1, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);

        osc.start(now);
        osc.stop(now + 0.1);
    }

    // Helper: Create white noise burst for paper/snap sounds
    createNoiseBurst(volume, duration) {
        const bufferSize = this.ctx.sampleRate * duration;
        const buffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
        const output = buffer.getChannelData(0);

        for (let i = 0; i < bufferSize; i++) {
            output[i] = Math.random() * 2 - 1;
        }

        const noise = this.ctx.createBufferSource();
        noise.buffer = buffer;

        const noiseGain = this.ctx.createGain();
        noise.connect(noiseGain);
        noiseGain.connect(this.masterGain);

        const now = this.ctx.currentTime;
        noiseGain.gain.setValueAtTime(volume, now);
        noiseGain.gain.exponentialRampToValueAtTime(0.001, now + duration);

        noise.start(now);
        noise.stop(now + duration);

        return noise;
    }
}

// Export singleton
const soundSystem = new SoundSystem();
export default soundSystem;
```

### Integration with App

The SoundSystem can replace the existing `playSound()` method in `app.js`:

```javascript
// In app.js - replace the existing playSound method
// Option 1: Direct integration (no import needed for non-module setup)

// Create global instance
window.soundSystem = new SoundSystem();

// Initialize on first interaction
document.addEventListener('click', async () => {
    await window.soundSystem.init();
}, { once: true });

// Replace existing playSound calls
playSound(type) {
    window.soundSystem.play(type);
}

// CardAnimations already routes through window.game.playSound()
// so no changes needed in card-animations.js
```

### Sound Variation

Add slight randomization to prevent repetitive sounds:

```javascript
playFlip(now) {
    // Random variation
    const pitchVariation = 1 + (Math.random() - 0.5) * 0.1;
    const volumeVariation = 1 + (Math.random() - 0.5) * 0.2;

    // Apply to sound...
    click.frequency.setValueAtTime(2000 * pitchVariation, now);
    clickGain.gain.setValueAtTime(0.15 * volumeVariation, now);
}
```

### Settings UI

```javascript
// In settings panel
renderSoundSettings() {
    return `
        <div class="setting-group">
            <label class="setting-toggle">
                <input type="checkbox" id="sound-enabled"
                       ${soundSystem.enabled ? 'checked' : ''}>
                <span>Sound Effects</span>
            </label>

            <label class="setting-slider" ${!soundSystem.enabled ? 'style="opacity: 0.5"' : ''}>
                <span>Volume</span>
                <input type="range" id="sound-volume"
                       min="0" max="1" step="0.1"
                       value="${soundSystem.volume}"
                       ${!soundSystem.enabled ? 'disabled' : ''}>
            </label>
        </div>
    `;
}

// Event handlers
document.getElementById('sound-enabled').addEventListener('change', (e) => {
    soundSystem.setEnabled(e.target.checked);
});

document.getElementById('sound-volume').addEventListener('input', (e) => {
    soundSystem.setVolume(parseFloat(e.target.value));
});
```

---

## CSS for Settings

```css
.setting-group {
    margin-bottom: 16px;
}

.setting-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
}

.setting-slider {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
    transition: opacity 0.2s;
}

.setting-slider input[type="range"] {
    flex: 1;
    -webkit-appearance: none;
    background: rgba(255, 255, 255, 0.2);
    height: 4px;
    border-radius: 2px;
}

.setting-slider input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    background: #f4a460;
    border-radius: 50%;
    cursor: pointer;
}
```

---

## Test Scenarios

1. **Card flip** - Sharp snap sound
2. **Card place/discard** - Soft thunk
3. **Draw from deck** - Slide + flip sequence
4. **Draw from discard** - Quick grab
5. **Pair formed** - Double click satisfaction
6. **Knock** - Table tap
7. **Deal sequence** - Rapid snaps
8. **Volume control** - Adjusts all sounds
9. **Mute toggle** - Silences all sounds
10. **Settings persist** - Reload maintains preferences
11. **First interaction** - AudioContext initializes

---

## Acceptance Criteria

- [ ] Distinct sounds for each card action
- [ ] Sounds feel physical (not arcade beeps)
- [ ] Variation prevents repetition fatigue
- [ ] Volume slider works
- [ ] Mute toggle works
- [ ] Settings persist in localStorage
- [ ] AudioContext handles browser restrictions
- [ ] No sound glitches or overlaps
- [ ] Performant (no audio lag)

---

## Implementation Order

1. Create SoundSystem class with basic structure
2. Implement individual sound methods
3. Add noise burst helper for paper sounds
4. Add volume/enabled controls
5. Integrate with existing playSound calls
6. Add variation to prevent repetition
7. Add settings UI
8. Test on various browsers
9. Fine-tune sound character

---

## Notes for Agent

- Replaces existing `playSound()` method in `app.js`
- CardAnimations already routes through `window.game.playSound()` - no changes needed there
- Web Audio API has good browser support
- AudioContext must be created after user interaction
- Noise bursts add realistic texture to card sounds
- Keep sounds short (<200ms) to stay responsive
- Volume variation and pitch variation prevent fatigue
- Test with headphones - sounds should be pleasant, not jarring
- Consider: different sound "themes"? (Classic, Minimal, Fun)
- Mobile: test performance impact of audio synthesis
- Settings should persist in localStorage
