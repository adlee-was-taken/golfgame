// Centralized timing configuration for all animations and pauses
// Edit these values to tune the feel of card animations and CPU gameplay

const TIMING = {
    // Card animations (milliseconds) - smooth, unhurried
    card: {
        flip: 400,              // Card flip duration (must match CSS transition)
        move: 400,              // Card movement - slower = smoother
        lift: 0,                // No lift pause
        moving: 400,            // Card moving class duration
    },

    // Pauses - minimal, let animations flow
    pause: {
        afterFlip: 0,           // No pause - flow into next action
        afterDiscard: 100,      // Brief settle
        beforeNewCard: 0,       // No pause
        afterSwapComplete: 100, // Brief settle
        betweenAnimations: 0,   // No gaps - continuous flow
        beforeFlip: 0,          // No pause
    },

    // Beat timing for animation phases (~1.2 sec with variance)
    beat: {
        base: 1200,             // Base beat duration (longer to see results)
        variance: 200,          // +/- variance for natural feel
        fadeOut: 300,           // Fade out duration
        fadeIn: 300,            // Fade in duration
    },

    // UI feedback durations (milliseconds)
    feedback: {
        drawPulse: 375,         // Draw pile highlight duration (25% slower for clear sequencing)
        discardLand: 375,       // Discard land effect duration (25% slower)
        cardFlipIn: 300,        // Card flip-in effect duration
        statusMessage: 2000,    // Toast/status message duration
        copyConfirm: 2000,      // Copy button confirmation duration
        discardPickup: 250,     // Discard pickup animation duration
    },

    // CSS animation timing (for reference - actual values in style.css)
    css: {
        cpuConsidering: 1500,   // CPU considering pulse cycle
    },

    // Anime.js animation configuration
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
    },

    // Card manager specific
    cardManager: {
        flipDuration: 400,      // Card flip animation
        moveDuration: 400,      // Card move animation
    },

    // Player swap animation steps - smooth continuous motion
    playerSwap: {
        flipToReveal: 400,      // Initial flip to show card
        pauseAfterReveal: 50,   // Tiny beat to register the card
        moveToDiscard: 400,     // Move old card to discard
        pulseBeforeSwap: 0,     // No pulse - just flow
        completePause: 50,      // Tiny settle
    },
};

// Helper to get beat duration with variance
function getBeatDuration() {
    const base = TIMING.beat.base;
    const variance = TIMING.beat.variance;
    return base + (Math.random() * variance * 2 - variance);
}

// Export for module systems, also attach to window for direct use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TIMING;
}
if (typeof window !== 'undefined') {
    window.TIMING = TIMING;
    window.getBeatDuration = getBeatDuration;
}
