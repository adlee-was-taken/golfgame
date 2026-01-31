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

        // Timing configuration (ms) - use centralized TIMING config
        const T = window.TIMING || {};
        this.timing = {
            flipDuration: T.card?.flip || 540,
            moveDuration: T.card?.move || 270,
            cardLift: T.card?.lift || 100,
            pauseAfterFlip: T.pause?.afterFlip || 144,
            pauseAfterDiscard: T.pause?.afterDiscard || 550,
            pauseBeforeNewCard: T.pause?.beforeNewCard || 150,
            pauseAfterSwapComplete: T.pause?.afterSwapComplete || 400,
            pauseBetweenAnimations: T.pause?.betweenAnimations || 90,
            pauseBeforeFlip: T.pause?.beforeFlip || 50,
            // Beat timing
            beatBase: T.beat?.base || 1000,
            beatVariance: T.beat?.variance || 200,
            fadeOut: T.beat?.fadeOut || 300,
            fadeIn: T.beat?.fadeIn || 300,
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
        await this.delay(this.timing.pauseBeforeFlip);

        // Remove flipped to trigger animation to front
        inner.classList.remove('flipped');

        await this.delay(this.timing.flipDuration);
        await this.delay(this.timing.pauseAfterFlip);

        // Clean up
        animCard.remove();
    }

    // Animate a card swap - smooth continuous motion
    async animateSwap(movement) {
        const { playerId, position, oldCard, newCard } = movement;

        const slotRect = this.getSlotRect(playerId, position);
        const discardRect = this.getLocationRect('discard');
        const holdingRect = this.getLocationRect('holding');

        if (!slotRect || !discardRect || slotRect.width === 0) {
            return;
        }

        // Create animation cards
        const handCard = this.createAnimCard();
        this.cardManager.cardLayer.appendChild(handCard);
        this.setCardPosition(handCard, slotRect);

        const handInner = handCard.querySelector('.card-inner');
        const handFront = handCard.querySelector('.card-face-front');

        const heldCard = this.createAnimCard();
        this.cardManager.cardLayer.appendChild(heldCard);
        this.setCardPosition(heldCard, holdingRect || discardRect);

        const heldInner = heldCard.querySelector('.card-inner');
        const heldFront = heldCard.querySelector('.card-face-front');

        // Set up initial state
        this.setCardFront(handFront, oldCard);
        if (!oldCard.face_up) {
            handInner.classList.add('flipped');
        }
        this.setCardFront(heldFront, newCard);
        heldInner.classList.remove('flipped');

        // Step 1: If face-down, flip to reveal
        if (!oldCard.face_up) {
            this.playSound('flip');
            handInner.classList.remove('flipped');
            await this.delay(this.timing.flipDuration);
        }

        // Step 2: Quick crossfade swap
        handCard.classList.add('fade-out');
        heldCard.classList.add('fade-out');
        await this.delay(150);

        this.setCardPosition(handCard, discardRect);
        this.setCardPosition(heldCard, slotRect);

        this.playSound('card');
        handCard.classList.remove('fade-out');
        heldCard.classList.remove('fade-out');
        handCard.classList.add('fade-in');
        heldCard.classList.add('fade-in');
        await this.delay(150);

        // Clean up
        handCard.remove();
        heldCard.remove();
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

        // Same timing as player swap - let discard land and pulse settle
        await this.delay(this.timing.pauseAfterDiscard);

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
        animCard.classList.add('moving');
        this.setCardPosition(animCard, holdingRect);
        await this.delay(this.timing.moveDuration);
        animCard.classList.remove('moving');

        // Brief settle before state updates
        await this.delay(this.timing.pauseBeforeNewCard);

        // Clean up - renderGame will show the holding card state
        animCard.remove();
    }

    // Animate drawing from discard - show card lifting and moving to holding position
    async animateDrawDiscard(movement) {
        const { card } = movement;

        const discardRect = this.getLocationRect('discard');
        const holdingRect = this.getLocationRect('holding');

        if (!discardRect || !holdingRect) return;

        // Create animation card at discard position (face UP - visible card)
        const animCard = this.createAnimCard();
        this.cardManager.cardLayer.appendChild(animCard);
        this.setCardPosition(animCard, discardRect);

        const inner = animCard.querySelector('.card-inner');
        const front = animCard.querySelector('.card-face-front');

        // Show the card face (discard is always visible)
        if (card) {
            this.setCardFront(front, card);
        }
        inner.classList.remove('flipped'); // Face up

        // Lift effect before moving - card rises slightly
        animCard.style.transform = 'translateY(-8px) scale(1.05)';
        animCard.style.transition = `transform ${this.timing.cardLift}ms ease-out`;
        await this.delay(this.timing.cardLift);

        // Move to holding position
        this.playSound('card');
        animCard.classList.add('moving');
        animCard.style.transform = '';
        this.setCardPosition(animCard, holdingRect);
        await this.delay(this.timing.moveDuration);
        animCard.classList.remove('moving');

        // Brief settle before state updates
        await this.delay(this.timing.pauseBeforeNewCard);

        // Clean up - renderGame will show the holding card state
        animCard.remove();
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
