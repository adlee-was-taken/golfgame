// CardManager - Manages persistent card DOM elements
// Cards are REAL elements that exist in ONE place and move between locations

class CardManager {
    constructor(cardLayer) {
        this.cardLayer = cardLayer;
        // Map of "playerId-position" -> card element
        this.handCards = new Map();
        // Special cards
        this.deckCard = null;
        this.discardCard = null;
        this.holdingCard = null;
    }

    // Initialize cards for a game state
    initializeCards(gameState, playerId, getSlotRect, getDeckRect, getDiscardRect) {
        this.clear();

        // Create cards for each player's hand
        for (const player of gameState.players) {
            for (let i = 0; i < 6; i++) {
                const card = player.cards[i];
                const slotKey = `${player.id}-${i}`;
                const cardEl = this.createCardElement(card);

                // Position at slot (will be updated later if rect not ready)
                const rect = getSlotRect(player.id, i);
                if (rect && rect.width > 0) {
                    this.positionCard(cardEl, rect);
                } else {
                    // Start invisible, will be positioned by updateAllPositions
                    cardEl.style.opacity = '0';
                }

                this.handCards.set(slotKey, {
                    element: cardEl,
                    cardData: card,
                    playerId: player.id,
                    position: i
                });

                this.cardLayer.appendChild(cardEl);
            }
        }
    }

    // Create a card DOM element with 3D flip structure
    createCardElement(cardData) {
        const card = document.createElement('div');
        card.className = 'real-card';

        card.innerHTML = `
            <div class="card-inner">
                <div class="card-face card-face-front"></div>
                <div class="card-face card-face-back"></div>
            </div>
        `;

        this.updateCardAppearance(card, cardData);
        return card;
    }

    // Update card visual state (face up/down, content)
    updateCardAppearance(cardEl, cardData) {
        const inner = cardEl.querySelector('.card-inner');
        const front = cardEl.querySelector('.card-face-front');
        const back = cardEl.querySelector('.card-face-back');

        // Reset front classes
        front.className = 'card-face card-face-front';

        // Apply deck color to card back
        if (back) {
            // Remove any existing deck color classes
            back.className = back.className.replace(/\bdeck-\w+/g, '').trim();
            back.className = 'card-face card-face-back';
            const deckColor = this.getDeckColorClass(cardData);
            if (deckColor) {
                back.classList.add(deckColor);
            }
        }

        if (!cardData || !cardData.face_up || !cardData.rank) {
            // Face down or no data
            inner.classList.add('flipped');
            front.innerHTML = '';
        } else {
            // Face up with data
            inner.classList.remove('flipped');

            if (cardData.rank === '★') {
                front.classList.add('joker');
                const icon = cardData.suit === 'hearts' ? '🐉' : '👹';
                front.innerHTML = `<span class="joker-icon">${icon}</span><span class="joker-label">Joker</span>`;
            } else {
                const isRed = cardData.suit === 'hearts' || cardData.suit === 'diamonds';
                front.classList.add(isRed ? 'red' : 'black');
                front.innerHTML = `${cardData.rank}<br>${this.getSuitSymbol(cardData.suit)}`;
            }
        }
    }

    // Get the deck color class for a card based on its deck_id
    getDeckColorClass(cardData) {
        if (!cardData || cardData.deck_id === undefined || cardData.deck_id === null) {
            return null;
        }
        // Get deck colors from game state (set by app.js)
        const deckColors = window.currentDeckColors || ['red', 'blue', 'gold'];
        const colorName = deckColors[cardData.deck_id] || deckColors[0] || 'red';
        return `deck-${colorName}`;
    }

    getSuitSymbol(suit) {
        return { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' }[suit] || '';
    }

    // Position a card at a rect
    positionCard(cardEl, rect, animate = false) {
        if (animate) {
            cardEl.classList.add('moving');
        }

        cardEl.style.left = `${rect.left}px`;
        cardEl.style.top = `${rect.top}px`;
        cardEl.style.width = `${rect.width}px`;
        cardEl.style.height = `${rect.height}px`;

        // On mobile, scale font proportional to card width so rank/suit fit
        if (document.body.classList.contains('mobile-portrait')) {
            cardEl.style.fontSize = `${rect.width * 0.35}px`;
        } else {
            cardEl.style.fontSize = '';
        }

        if (animate) {
            const moveDuration = window.TIMING?.card?.moving || 350;
            setTimeout(() => cardEl.classList.remove('moving'), moveDuration);
        }
    }

    // Get a hand card by player and position
    getHandCard(playerId, position) {
        return this.handCards.get(`${playerId}-${position}`);
    }

    // Update all card positions to match current slot positions
    // Returns number of cards successfully positioned
    updateAllPositions(getSlotRect) {
        let positioned = 0;
        for (const [key, cardInfo] of this.handCards) {
            const rect = getSlotRect(cardInfo.playerId, cardInfo.position);
            if (rect && rect.width > 0) {
                this.positionCard(cardInfo.element, rect, false);
                // Restore visibility if it was hidden
                cardInfo.element.style.opacity = '1';
                positioned++;
            }
        }
        return positioned;
    }

    // Animate a card flip
    async flipCard(playerId, position, newCardData, duration = null) {
        // Use centralized timing if not specified
        if (duration === null) {
            duration = window.TIMING?.cardManager?.flipDuration || 400;
        }
        const cardInfo = this.getHandCard(playerId, position);
        if (!cardInfo) return;

        const inner = cardInfo.element.querySelector('.card-inner');
        const front = cardInfo.element.querySelector('.card-face-front');

        // Set up the front content before flip
        front.className = 'card-face card-face-front';
        if (newCardData.rank === '★') {
            front.classList.add('joker');
            const icon = newCardData.suit === 'hearts' ? '🐉' : '👹';
            front.innerHTML = `<span class="joker-icon">${icon}</span><span class="joker-label">Joker</span>`;
        } else {
            const isRed = newCardData.suit === 'hearts' || newCardData.suit === 'diamonds';
            front.classList.add(isRed ? 'red' : 'black');
            front.innerHTML = `${newCardData.rank}<br>${this.getSuitSymbol(newCardData.suit)}`;
        }

        // Animate flip
        inner.classList.remove('flipped');

        await this.delay(duration);

        cardInfo.cardData = newCardData;
    }

    // Animate a swap: hand card goes to discard, new card comes to hand
    async animateSwap(playerId, position, oldCardData, newCardData, getSlotRect, getDiscardRect, duration = null) {
        // Use centralized timing if not specified
        if (duration === null) {
            duration = window.TIMING?.cardManager?.moveDuration || 250;
        }
        const cardInfo = this.getHandCard(playerId, position);
        if (!cardInfo) return;

        const slotRect = getSlotRect(playerId, position);
        const discardRect = getDiscardRect();

        if (!slotRect || !discardRect) return;
        if (!oldCardData || !oldCardData.rank) {
            // Can't animate without card data - just update appearance
            this.updateCardAppearance(cardInfo.element, newCardData);
            cardInfo.cardData = newCardData;
            return;
        }

        const cardEl = cardInfo.element;
        const inner = cardEl.querySelector('.card-inner');
        const front = cardEl.querySelector('.card-face-front');

        // Step 1: If face down, flip to reveal the old card
        if (!oldCardData.face_up) {
            // Set front to show old card
            front.className = 'card-face card-face-front';
            if (oldCardData.rank === '★') {
                front.classList.add('joker');
                const icon = oldCardData.suit === 'hearts' ? '🐉' : '👹';
                front.innerHTML = `<span class="joker-icon">${icon}</span><span class="joker-label">Joker</span>`;
            } else {
                const isRed = oldCardData.suit === 'hearts' || oldCardData.suit === 'diamonds';
                front.classList.add(isRed ? 'red' : 'black');
                front.innerHTML = `${oldCardData.rank}<br>${this.getSuitSymbol(oldCardData.suit)}`;
            }

            inner.classList.remove('flipped');
            const flipDuration = window.TIMING?.cardManager?.flipDuration || 400;
            await this.delay(flipDuration);
        }

        // Step 2: Move card to discard
        cardEl.classList.add('moving');
        this.positionCard(cardEl, discardRect);
        await this.delay(duration + 50);
        cardEl.classList.remove('moving');

        // Pause to show the discarded card
        const pauseDuration = window.TIMING?.cardManager?.moveDuration || 250;
        await this.delay(pauseDuration);

        // Step 3: Update card to show new card and move back to hand
        front.className = 'card-face card-face-front';
        if (newCardData.rank === '★') {
            front.classList.add('joker');
            const icon = newCardData.suit === 'hearts' ? '🐉' : '👹';
            front.innerHTML = `<span class="joker-icon">${icon}</span><span class="joker-label">Joker</span>`;
        } else {
            const isRed = newCardData.suit === 'hearts' || newCardData.suit === 'diamonds';
            front.classList.add(isRed ? 'red' : 'black');
            front.innerHTML = `${newCardData.rank}<br>${this.getSuitSymbol(newCardData.suit)}`;
        }

        if (!newCardData.face_up) {
            inner.classList.add('flipped');
        }

        cardEl.classList.add('moving');
        this.positionCard(cardEl, slotRect);
        await this.delay(duration + 50);
        cardEl.classList.remove('moving');

        cardInfo.cardData = newCardData;
    }

    // Set holding state for a card (drawn card highlight)
    setHolding(playerId, position, isHolding) {
        const cardInfo = this.getHandCard(playerId, position);
        if (cardInfo) {
            cardInfo.element.classList.toggle('holding', isHolding);
        }
    }

    // Clear all cards
    clear() {
        for (const [key, cardInfo] of this.handCards) {
            cardInfo.element.remove();
        }
        this.handCards.clear();

        if (this.holdingCard) {
            this.holdingCard.remove();
            this.holdingCard = null;
        }
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = CardManager;
}
