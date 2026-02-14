// StateDiffer - Detects what changed between game states
// Generates movement instructions for the animation queue

class StateDiffer {
    constructor() {
        this.previousState = null;
    }

    // Compare old and new state, return array of movements
    diff(oldState, newState) {
        const movements = [];

        if (!oldState || !newState) {
            return movements;
        }

        // Check for initial flip phase - still animate initial flips
        if (oldState.waiting_for_initial_flip && !newState.waiting_for_initial_flip) {
            // Initial flip just completed - detect which cards were flipped
            for (const newPlayer of newState.players) {
                const oldPlayer = oldState.players.find(p => p.id === newPlayer.id);
                if (oldPlayer) {
                    for (let i = 0; i < 6; i++) {
                        if (!oldPlayer.cards[i].face_up && newPlayer.cards[i].face_up) {
                            movements.push({
                                type: 'flip',
                                playerId: newPlayer.id,
                                position: i,
                                faceUp: true,
                                card: newPlayer.cards[i]
                            });
                        }
                    }
                }
            }
            return movements;
        }

        // Still in initial flip selection - no animations
        if (newState.waiting_for_initial_flip) {
            return movements;
        }

        // Check for turn change - the previous player just acted
        const previousPlayerId = oldState.current_player_id;
        const currentPlayerId = newState.current_player_id;
        const turnChanged = previousPlayerId !== currentPlayerId;

        // Detect if a swap happened (discard changed AND a hand position changed)
        const newTop = newState.discard_top;
        const oldTop = oldState.discard_top;
        const discardChanged = newTop && (!oldTop ||
            oldTop.rank !== newTop.rank ||
            oldTop.suit !== newTop.suit);

        // Find hand changes for the player who just played
        if (turnChanged && previousPlayerId) {
            const oldPlayer = oldState.players.find(p => p.id === previousPlayerId);
            const newPlayer = newState.players.find(p => p.id === previousPlayerId);

            if (oldPlayer && newPlayer) {
                // First pass: detect swaps (card identity changed)
                const swappedPositions = new Set();
                for (let i = 0; i < 6; i++) {
                    const oldCard = oldPlayer.cards[i];
                    const newCard = newPlayer.cards[i];

                    // Card identity changed = swap happened at this position
                    if (this.cardIdentityChanged(oldCard, newCard)) {
                        swappedPositions.add(i);

                        // Use discard_top for the revealed card (more reliable for opponents)
                        const revealedCard = newState.discard_top || { ...oldCard, face_up: true };

                        movements.push({
                            type: 'swap',
                            playerId: previousPlayerId,
                            position: i,
                            oldCard: revealedCard,
                            newCard: newCard
                        });
                        break; // Only one swap per turn
                    }
                }

                // Second pass: detect flips (card went from face_down to face_up, not a swap)
                for (let i = 0; i < 6; i++) {
                    if (swappedPositions.has(i)) continue; // Skip if already detected as swap

                    const oldCard = oldPlayer.cards[i];
                    const newCard = newPlayer.cards[i];

                    if (this.cardWasFlipped(oldCard, newCard)) {
                        movements.push({
                            type: 'flip',
                            playerId: previousPlayerId,
                            position: i,
                            faceUp: true,
                            card: newCard
                        });
                    }
                }
            }
        }

        // Detect drawing (current player just drew)
        if (newState.has_drawn_card && !oldState.has_drawn_card) {
            // Discard pile decreased = drew from discard
            const drewFromDiscard = !newState.discard_top ||
                (oldState.discard_top &&
                 (!newState.discard_top ||
                  oldState.discard_top.rank !== newState.discard_top.rank ||
                  oldState.discard_top.suit !== newState.discard_top.suit));

            movements.push({
                type: drewFromDiscard ? 'draw-discard' : 'draw-deck',
                playerId: currentPlayerId,
                card: drewFromDiscard ? oldState.discard_top : null  // Include card for discard draw animation
            });
        }

        return movements;
    }

    // Check if the card identity (rank+suit) changed between old and new
    // Returns true if definitely different cards, false if same or unknown
    cardIdentityChanged(oldCard, newCard) {
        // If both have rank/suit data, compare directly
        if (oldCard.rank && newCard.rank) {
            return oldCard.rank !== newCard.rank || oldCard.suit !== newCard.suit;
        }
        // Can't determine - assume same card (flip, not swap)
        return false;
    }

    // Check if a card was just flipped (same card, now face up)
    cardWasFlipped(oldCard, newCard) {
        return !oldCard.face_up && newCard.face_up;
    }

    // Get a summary of movements for debugging
    summarize(movements) {
        return movements.map(m => {
            switch (m.type) {
                case 'flip':
                    return `Flip: Player ${m.playerId} position ${m.position}`;
                case 'swap':
                    return `Swap: Player ${m.playerId} position ${m.position}`;
                case 'discard':
                    return `Discard: ${m.card.rank}${m.card.suit} from player ${m.fromPlayerId}`;
                case 'draw-deck':
                    return `Draw from deck: Player ${m.playerId}`;
                case 'draw-discard':
                    return `Draw from discard: Player ${m.playerId}`;
                default:
                    return `Unknown: ${m.type}`;
            }
        }).join('\n');
    }
}

// Export for use in app.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = StateDiffer;
}
