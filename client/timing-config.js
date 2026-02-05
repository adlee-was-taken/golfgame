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

    // V3_02: Dealing animation
    dealing: {
        shufflePause: 400,        // Pause after shuffle sound
        cardFlyTime: 150,         // Time for card to fly to destination
        cardStagger: 80,          // Delay between cards
        roundPause: 50,           // Pause between deal rounds
        discardFlipDelay: 200,    // Pause before flipping discard
    },

    // V3_03: Round end reveal timing
    reveal: {
        voluntaryWindow: 4000,    // Time for players to flip their own cards
        initialPause: 500,        // Pause before auto-reveals start
        cardStagger: 100,         // Between cards in same hand
        playerPause: 400,         // Pause after each player's reveal
        highlightDuration: 200,   // Player area highlight fade-in
    },

    // V3_04: Pair celebration
    celebration: {
        pairDuration: 400,        // Celebration animation length
        pairDelay: 50,            // Slight delay before celebration
    },

    // V3_07: Score tallying animation
    tally: {
        initialPause: 200,        // After reveal, before tally
        cardHighlight: 140,       // Duration to show each card value
        columnPause: 100,         // Between columns
        pairCelebration: 300,     // Pair cancel effect
        playerPause: 350,         // Between players
        finalScoreReveal: 400,    // Final score animation
    },

    // Opponent initial flip stagger (after dealing)
    // All players flip concurrently within this window (not taking turns)
    initialFlips: {
        windowStart: 500,         // Minimum delay before any opponent starts flipping
        windowEnd: 2500,          // Maximum delay before opponent starts (random in range)
        cardStagger: 400,         // Delay between an opponent's two card flips
    },

    // V3_11: Physical swap animation
    swap: {
        lift: 80,             // Time to lift cards
        arc: 280,             // Time for arc travel
        settle: 60,           // Time to settle into place
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
