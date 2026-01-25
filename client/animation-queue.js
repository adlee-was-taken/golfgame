// AnimationQueue - Sequences card animations properly
// Ensures animations play in order without overlap

class AnimationQueue {
    constructor(cardManager, getSlotRect, getLocationRect, playSound) {
        this.cardManager = cardManager;
        this.getSlotRect = getSlotRect;      // Function to get slot position
        this.getLocationRect = getLocationRect; // Function to get deck/discard position
        this.playSound = playSound || (() => {}); // Sound callback
        this.queue = [];
        this.processing = false;
        this.animationInProgress = false;

        // Timing configuration (ms)
        this.timing = {
            flipDuration: 400,
            moveDuration: 300,
            pauseAfterMove: 200,
            pauseAfterFlip: 100,
            pauseBetweenAnimations: 100
        };
    }

    // Add movements to the queue and start processing
    async enqueue(movements, onComplete) {
        if (!movements || movements.length === 0) {
            if (onComplete) onComplete();
            return;
        }

        // Add completion callback to last movement
        const movementsWithCallback = movements.map((m, i) => ({
            ...m,
            onComplete: i === movements.length - 1 ? onComplete : null
        }));

        this.queue.push(...movementsWithCallback);

        if (!this.processing) {
            await this.processQueue();
        }
    }

    // Process queued animations one at a time
    async processQueue() {
        if (this.processing) return;
        this.processing = true;
        this.animationInProgress = true;

        while (this.queue.length > 0) {
            const movement = this.queue.shift();

            try {
                await this.animate(movement);
            } catch (e) {
                console.error('Animation error:', e);
            }

            // Callback after last movement
            if (movement.onComplete) {
                movement.onComplete();
            }

            // Pause between animations
            if (this.queue.length > 0) {
                await this.delay(this.timing.pauseBetweenAnimations);
            }
        }

        this.processing = false;
        this.animationInProgress = false;
    }

    // Route to appropriate animation
    async animate(movement) {
        switch (movement.type) {
            case 'flip':
                await this.animateFlip(movement);
                break;
            case 'swap':
                await this.animateSwap(movement);
                break;
            case 'discard':
                await this.animateDiscard(movement);
                break;
            case 'draw-deck':
                await this.animateDrawDeck(movement);
                break;
            case 'draw-discard':
                await this.animateDrawDiscard(movement);
                break;
        }
    }

    // Animate a card flip
    async animateFlip(movement) {
        const { playerId, position, faceUp, card } = movement;

        // Get slot position
        const slotRect = this.getSlotRect(playerId, position);
        if (!slotRect || slotRect.width === 0 || slotRect.height === 0) {
            return;
        }

        // Create animation card at slot position
        const animCard = this.createAnimCard();
        this.cardManager.cardLayer.appendChild(animCard);
        this.setCardPosition(animCard, slotRect);

        const inner = animCard.querySelector('.card-inner');
        const front = animCard.querySelector('.card-face-front');

        // Set up what we're flipping to (front face)
        this.setCardFront(front, card);

        // Start face down (flipped = showing back)
        inner.classList.add('flipped');

        // Force a reflow to ensure the initial state is applied
        animCard.offsetHeight;

        // Animate the flip
        this.playSound('flip');
        await this.delay(50); // Brief pause before flip

        // Remove flipped to trigger animation to front
        inner.classList.remove('flipped');

        await this.delay(this.timing.flipDuration);
        await this.delay(this.timing.pauseAfterFlip);

        // Clean up
        animCard.remove();
    }

    // Animate a card swap (hand card to discard, drawn card to hand)
    async animateSwap(movement) {
        const { playerId, position, oldCard, newCard } = movement;

        // Get positions
        const slotRect = this.getSlotRect(playerId, position);
        const discardRect = this.getLocationRect('discard');
        const holdingRect = this.getLocationRect('holding');

        if (!slotRect || !discardRect || slotRect.width === 0) {
            return;
        }

        // Create a temporary card element for the animation
        const animCard = this.createAnimCard();
        this.cardManager.cardLayer.appendChild(animCard);

        // Position at slot
        this.setCardPosition(animCard, slotRect);

        // Start face down (showing back)
        const inner = animCard.querySelector('.card-inner');
        const front = animCard.querySelector('.card-face-front');
        inner.classList.add('flipped');

        // Step 1: If card was face down, flip to reveal it
        if (!oldCard.face_up) {
            // Set up the front with the old card content (what we're discarding)
            this.setCardFront(front, oldCard);

            this.playSound('flip');
            inner.classList.remove('flipped');
            await this.delay(this.timing.flipDuration);
        } else {
            // Already face up, just show it
            this.setCardFront(front, oldCard);
            inner.classList.remove('flipped');
        }

        await this.delay(100);

        // Step 2: Move card to discard pile
        this.playSound('card');
        animCard.classList.add('moving');
        this.setCardPosition(animCard, discardRect);
        await this.delay(this.timing.moveDuration);
        animCard.classList.remove('moving');

        // Pause to show the card landing on discard
        await this.delay(this.timing.pauseAfterMove + 200);

        // Step 3: Create second card for the new card coming into hand
        const newAnimCard = this.createAnimCard();
        this.cardManager.cardLayer.appendChild(newAnimCard);

        // New card starts at holding/discard position
        this.setCardPosition(newAnimCard, holdingRect || discardRect);
        const newInner = newAnimCard.querySelector('.card-inner');
        const newFront = newAnimCard.querySelector('.card-face-front');

        // Show new card (it's face up from the drawn card)
        this.setCardFront(newFront, newCard);
        newInner.classList.remove('flipped');

        // Step 4: Move new card to the hand slot
        this.playSound('card');
        newAnimCard.classList.add('moving');
        this.setCardPosition(newAnimCard, slotRect);
        await this.delay(this.timing.moveDuration);
        newAnimCard.classList.remove('moving');

        // Clean up animation cards
        await this.delay(this.timing.pauseAfterMove);
        animCard.remove();
        newAnimCard.remove();
    }

    // Create a temporary animation card element
    createAnimCard() {
        const card = document.createElement('div');
        card.className = 'real-card anim-card';
        card.innerHTML = `
            <div class="card-inner">
                <div class="card-face card-face-front"></div>
                <div class="card-face card-face-back"><span>?</span></div>
            </div>
        `;
        return card;
    }

    // Set card position
    setCardPosition(card, rect) {
        card.style.left = `${rect.left}px`;
        card.style.top = `${rect.top}px`;
        card.style.width = `${rect.width}px`;
        card.style.height = `${rect.height}px`;
    }

    // Set card front content
    setCardFront(frontEl, cardData) {
        frontEl.className = 'card-face card-face-front';

        if (!cardData) return;

        if (cardData.rank === '★') {
            frontEl.classList.add('joker');
            const jokerIcon = cardData.suit === 'hearts' ? '🐉' : '👹';
            frontEl.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        } else {
            const isRed = cardData.suit === 'hearts' || cardData.suit === 'diamonds';
            frontEl.classList.add(isRed ? 'red' : 'black');
            const suitSymbol = this.getSuitSymbol(cardData.suit);
            frontEl.innerHTML = `${cardData.rank}<br>${suitSymbol}`;
        }
    }

    getSuitSymbol(suit) {
        const symbols = { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' };
        return symbols[suit] || '';
    }

    // Animate discarding a card (from hand to discard pile) - called for other players
    async animateDiscard(movement) {
        const { card, fromPlayerId, fromPosition } = movement;

        // If no specific position, animate from opponent's area
        const discardRect = this.getLocationRect('discard');
        if (!discardRect) return;

        let startRect;

        if (fromPosition !== null && fromPosition !== undefined) {
            startRect = this.getSlotRect(fromPlayerId, fromPosition);
        }

        // Fallback: use discard position offset upward
        if (!startRect) {
            startRect = {
                left: discardRect.left,
                top: discardRect.top - 80,
                width: discardRect.width,
                height: discardRect.height
            };
        }

        // Create animation card
        const animCard = this.createAnimCard();
        this.cardManager.cardLayer.appendChild(animCard);
        this.setCardPosition(animCard, startRect);

        const inner = animCard.querySelector('.card-inner');
        const front = animCard.querySelector('.card-face-front');

        // Show the card that was discarded
        this.setCardFront(front, card);
        inner.classList.remove('flipped');

        // Move to discard
        this.playSound('card');
        animCard.classList.add('moving');
        this.setCardPosition(animCard, discardRect);
        await this.delay(this.timing.moveDuration);
        animCard.classList.remove('moving');

        await this.delay(this.timing.pauseAfterMove);

        // Clean up
        animCard.remove();
    }

    // Animate drawing from deck
    async animateDrawDeck(movement) {
        const { playerId } = movement;

        const deckRect = this.getLocationRect('deck');
        const holdingRect = this.getLocationRect('holding');

        if (!deckRect || !holdingRect) return;

        // Create animation card at deck position (face down)
        const animCard = this.createAnimCard();
        this.cardManager.cardLayer.appendChild(animCard);
        this.setCardPosition(animCard, deckRect);

        const inner = animCard.querySelector('.card-inner');
        inner.classList.add('flipped'); // Show back

        // Move to holding position
        this.playSound('card');
        await this.delay(50);

        animCard.classList.add('moving');
        this.setCardPosition(animCard, holdingRect);
        await this.delay(this.timing.moveDuration);
        animCard.classList.remove('moving');

        // The card stays face down until the player decides what to do
        // (the actual card reveal happens when server sends card_drawn)

        await this.delay(this.timing.pauseAfterMove);

        // Clean up - renderGame will show the holding card state
        animCard.remove();
    }

    // Animate drawing from discard
    async animateDrawDiscard(movement) {
        const { playerId } = movement;

        // Discard to holding is mostly visual feedback
        // The card "lifts" slightly

        const discardRect = this.getLocationRect('discard');
        const holdingRect = this.getLocationRect('holding');

        if (!discardRect || !holdingRect) return;

        // Just play sound - visual handled by CSS :holding state
        this.playSound('card');

        await this.delay(this.timing.moveDuration);
    }

    // Check if animations are currently playing
    isAnimating() {
        return this.animationInProgress;
    }

    // Clear the queue (for interruption)
    clear() {
        this.queue = [];
    }

    // Utility delay
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Export for use in app.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AnimationQueue;
}
