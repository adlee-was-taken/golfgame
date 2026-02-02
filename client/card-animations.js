// CardAnimations - Unified anime.js-based animation system
// Replaces draw-animations.js and handles ALL card animations

class CardAnimations {
    constructor() {
        this.activeAnimations = new Map();
        this.isAnimating = false;
        this.cleanupTimeout = null;
    }

    // === UTILITY METHODS ===

    getDeckRect() {
        const deck = document.getElementById('deck');
        return deck ? deck.getBoundingClientRect() : null;
    }

    getDiscardRect() {
        const discard = document.getElementById('discard');
        return discard ? discard.getBoundingClientRect() : null;
    }

    getHoldingRect() {
        const deckRect = this.getDeckRect();
        const discardRect = this.getDiscardRect();
        if (!deckRect || !discardRect) return null;

        const centerX = (deckRect.left + deckRect.right + discardRect.left + discardRect.right) / 4;
        const cardWidth = deckRect.width;
        const cardHeight = deckRect.height;
        const overlapOffset = cardHeight * 0.35;

        return {
            left: centerX - cardWidth / 2,
            top: deckRect.top - overlapOffset,
            width: cardWidth,
            height: cardHeight
        };
    }

    getSuitSymbol(suit) {
        return { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' }[suit] || '';
    }

    isRedSuit(suit) {
        return suit === 'hearts' || suit === 'diamonds';
    }

    playSound(type) {
        if (window.game && typeof window.game.playSound === 'function') {
            window.game.playSound(type);
        }
    }

    getEasing(type) {
        const easings = window.TIMING?.anime?.easing || {};
        return easings[type] || 'easeOutQuad';
    }

    // Create animated card element with 3D flip structure
    createAnimCard(rect, showBack = false, deckColor = null) {
        const card = document.createElement('div');
        card.className = 'draw-anim-card';
        card.innerHTML = `
            <div class="draw-anim-inner">
                <div class="draw-anim-front card card-front"></div>
                <div class="draw-anim-back card card-back"></div>
            </div>
        `;
        document.body.appendChild(card);

        // Apply deck color to back
        if (deckColor) {
            const back = card.querySelector('.draw-anim-back');
            back.classList.add(`back-${deckColor}`);
        }

        if (showBack) {
            card.querySelector('.draw-anim-inner').style.transform = 'rotateY(180deg)';
        }

        if (rect) {
            card.style.left = rect.left + 'px';
            card.style.top = rect.top + 'px';
            card.style.width = rect.width + 'px';
            card.style.height = rect.height + 'px';
        }

        return card;
    }

    setCardContent(card, cardData) {
        const front = card.querySelector('.draw-anim-front');
        if (!front) return;
        front.className = 'draw-anim-front card card-front';

        if (!cardData) return;

        if (cardData.rank === '★') {
            front.classList.add('joker');
            const icon = cardData.suit === 'hearts' ? '🐉' : '👹';
            front.innerHTML = `<span class="joker-icon">${icon}</span><span class="joker-label">Joker</span>`;
        } else {
            const isRed = this.isRedSuit(cardData.suit);
            front.classList.add(isRed ? 'red' : 'black');
            front.innerHTML = `${cardData.rank}<br>${this.getSuitSymbol(cardData.suit)}`;
        }
    }

    getDeckColor() {
        if (window.game?.gameState?.deck_colors) {
            const deckId = window.game.gameState.deck_top_deck_id || 0;
            return window.game.gameState.deck_colors[deckId] || window.game.gameState.deck_colors[0];
        }
        return null;
    }

    cleanup() {
        document.querySelectorAll('.draw-anim-card').forEach(el => el.remove());
        this.isAnimating = false;
        if (this.cleanupTimeout) {
            clearTimeout(this.cleanupTimeout);
            this.cleanupTimeout = null;
        }
    }

    cancelAll() {
        // Cancel all tracked anime.js animations
        for (const [id, anim] of this.activeAnimations) {
            if (anim && typeof anim.pause === 'function') {
                anim.pause();
            }
        }
        this.activeAnimations.clear();
        this.cleanup();
    }

    // === DRAW ANIMATIONS ===

    // Draw from deck with suspenseful reveal
    animateDrawDeck(cardData, onComplete) {
        this.cleanup();

        const deckRect = this.getDeckRect();
        const holdingRect = this.getHoldingRect();
        if (!deckRect || !holdingRect) {
            if (onComplete) onComplete();
            return;
        }

        this.isAnimating = true;

        // Pulse the deck before drawing
        this.startDrawPulse(document.getElementById('deck'));

        // Delay card animation to let pulse be visible
        setTimeout(() => {
            this._animateDrawDeckCard(cardData, deckRect, holdingRect, onComplete);
        }, 250);
    }

    _animateDrawDeckCard(cardData, deckRect, holdingRect, onComplete) {
        const deckColor = this.getDeckColor();
        const animCard = this.createAnimCard(deckRect, true, deckColor);
        const inner = animCard.querySelector('.draw-anim-inner');

        if (cardData) {
            this.setCardContent(animCard, cardData);
        }

        this.playSound('card');

        // Failsafe cleanup
        this.cleanupTimeout = setTimeout(() => {
            this.cleanup();
            if (onComplete) onComplete();
        }, 1500);

        try {
            const timeline = anime.timeline({
                easing: this.getEasing('move'),
                complete: () => {
                    this.cleanup();
                    if (onComplete) onComplete();
                }
            });

            // Lift off deck with slight wobble
            timeline.add({
                targets: animCard,
                translateY: -15,
                rotate: [-2, 0],
                duration: 105,
                easing: this.getEasing('lift')
            });

            // Move to holding position
            timeline.add({
                targets: animCard,
                left: holdingRect.left,
                top: holdingRect.top,
                translateY: 0,
                duration: 175,
                easing: this.getEasing('move')
            });

            // Suspense pause
            timeline.add({ duration: 200 });

            // Flip to reveal
            if (cardData) {
                timeline.add({
                    targets: inner,
                    rotateY: 0,
                    duration: 245,
                    easing: this.getEasing('flip'),
                    begin: () => this.playSound('flip')
                });
            }

            // Brief pause to see card
            timeline.add({ duration: 150 });

            this.activeAnimations.set('drawDeck', timeline);
        } catch (e) {
            console.error('Draw animation error:', e);
            this.cleanup();
            if (onComplete) onComplete();
        }
    }

    // Draw from discard (quick decisive grab, no flip)
    animateDrawDiscard(cardData, onComplete) {
        this.cleanup();

        const discardRect = this.getDiscardRect();
        const holdingRect = this.getHoldingRect();
        if (!discardRect || !holdingRect) {
            if (onComplete) onComplete();
            return;
        }

        this.isAnimating = true;

        // Pulse discard pile
        this.startDrawPulse(document.getElementById('discard'));

        setTimeout(() => {
            this._animateDrawDiscardCard(cardData, discardRect, holdingRect, onComplete);
        }, 200);
    }

    _animateDrawDiscardCard(cardData, discardRect, holdingRect, onComplete) {
        const animCard = this.createAnimCard(discardRect, false);
        this.setCardContent(animCard, cardData);

        this.playSound('card');

        // Failsafe cleanup
        this.cleanupTimeout = setTimeout(() => {
            this.cleanup();
            if (onComplete) onComplete();
        }, 600);

        try {
            const timeline = anime.timeline({
                easing: this.getEasing('move'),
                complete: () => {
                    this.cleanup();
                    if (onComplete) onComplete();
                }
            });

            // Quick decisive lift
            timeline.add({
                targets: animCard,
                translateY: -12,
                scale: 1.05,
                duration: 42
            });

            // Direct move to holding
            timeline.add({
                targets: animCard,
                left: holdingRect.left,
                top: holdingRect.top,
                translateY: 0,
                scale: 1,
                duration: 126
            });

            // Minimal pause
            timeline.add({ duration: 80 });

            this.activeAnimations.set('drawDiscard', timeline);
        } catch (e) {
            console.error('Draw animation error:', e);
            this.cleanup();
            if (onComplete) onComplete();
        }
    }

    // === FLIP ANIMATIONS ===

    // Animate flipping a card element
    animateFlip(element, cardData, onComplete) {
        if (!element) {
            if (onComplete) onComplete();
            return;
        }

        const inner = element.querySelector('.card-inner');
        if (!inner) {
            if (onComplete) onComplete();
            return;
        }

        const duration = 245; // 30% faster flip

        try {
            const anim = anime({
                targets: inner,
                rotateY: [180, 0],
                duration: duration,
                easing: this.getEasing('flip'),
                begin: () => {
                    this.playSound('flip');
                    inner.classList.remove('flipped');
                },
                complete: () => {
                    if (onComplete) onComplete();
                }
            });

            this.activeAnimations.set(`flip-${Date.now()}`, anim);
        } catch (e) {
            console.error('Flip animation error:', e);
            inner.classList.remove('flipped');
            if (onComplete) onComplete();
        }
    }

    // Animate initial flip at game start - smooth flip only, no lift
    animateInitialFlip(cardElement, cardData, onComplete) {
        if (!cardElement) {
            if (onComplete) onComplete();
            return;
        }

        const rect = cardElement.getBoundingClientRect();
        const deckColor = this.getDeckColor();

        // Create overlay card for flip animation
        const animCard = this.createAnimCard(rect, true, deckColor);
        this.setCardContent(animCard, cardData);

        // Hide original card during animation
        cardElement.style.opacity = '0';

        const inner = animCard.querySelector('.draw-anim-inner');
        const duration = 245; // 30% faster flip

        try {
            // Simple smooth flip - no lift/settle
            anime({
                targets: inner,
                rotateY: 0,
                duration: duration,
                easing: this.getEasing('flip'),
                begin: () => this.playSound('flip'),
                complete: () => {
                    animCard.remove();
                    cardElement.style.opacity = '1';
                    if (onComplete) onComplete();
                }
            });

            this.activeAnimations.set(`initialFlip-${Date.now()}`, { pause: () => {} });
        } catch (e) {
            console.error('Initial flip animation error:', e);
            animCard.remove();
            cardElement.style.opacity = '1';
            if (onComplete) onComplete();
        }
    }

    // Fire-and-forget flip for opponent cards
    animateOpponentFlip(cardElement, cardData, rotation = 0) {
        if (!cardElement) return;

        const rect = cardElement.getBoundingClientRect();
        const deckColor = this.getDeckColor();

        const animCard = this.createAnimCard(rect, true, deckColor);
        this.setCardContent(animCard, cardData);

        // Apply rotation to match arch layout
        if (rotation) {
            animCard.style.transform = `rotate(${rotation}deg)`;
        }

        cardElement.classList.add('swap-out');

        const inner = animCard.querySelector('.draw-anim-inner');
        const duration = 245; // 30% faster flip

        try {
            anime({
                targets: inner,
                rotateY: 0,
                duration: duration,
                easing: this.getEasing('flip'),
                begin: () => this.playSound('flip'),
                complete: () => {
                    animCard.remove();
                    cardElement.classList.remove('swap-out');
                }
            });
        } catch (e) {
            console.error('Opponent flip animation error:', e);
            animCard.remove();
            cardElement.classList.remove('swap-out');
        }
    }

    // === SWAP ANIMATIONS ===

    // Animate player swapping drawn card with hand card
    animateSwap(position, oldCard, newCard, handCardElement, onComplete) {
        if (!handCardElement) {
            if (onComplete) onComplete();
            return;
        }

        const isAlreadyFaceUp = oldCard?.face_up;

        if (isAlreadyFaceUp) {
            // Face-up swap: subtle pulse, no flip needed
            this._animateFaceUpSwap(handCardElement, onComplete);
        } else {
            // Face-down swap: flip reveal then swap
            this._animateFaceDownSwap(position, oldCard, handCardElement, onComplete);
        }
    }

    _animateFaceUpSwap(handCardElement, onComplete) {
        this.playSound('card');

        // Apply swap pulse via anime.js
        try {
            const timeline = anime.timeline({
                easing: 'easeOutQuad',
                complete: () => {
                    if (onComplete) onComplete();
                }
            });

            timeline.add({
                targets: handCardElement,
                scale: [1, 0.92, 1.08, 1],
                filter: ['brightness(1)', 'brightness(0.85)', 'brightness(1.15)', 'brightness(1)'],
                duration: 400,
                easing: 'easeOutQuad'
            });

            this.activeAnimations.set(`swapPulse-${Date.now()}`, timeline);
        } catch (e) {
            console.error('Face-up swap animation error:', e);
            if (onComplete) onComplete();
        }
    }

    _animateFaceDownSwap(position, oldCard, handCardElement, onComplete) {
        const rect = handCardElement.getBoundingClientRect();
        const discardRect = this.getDiscardRect();
        const deckColor = this.getDeckColor();

        // Create animated card at hand position
        const animCard = this.createAnimCard(rect, true, deckColor);

        // Set content to show what's being revealed (the OLD card going to discard)
        if (oldCard) {
            this.setCardContent(animCard, oldCard);
        }

        handCardElement.classList.add('swap-out');

        const inner = animCard.querySelector('.draw-anim-inner');
        const flipDuration = 245; // 30% faster flip

        try {
            const timeline = anime.timeline({
                easing: this.getEasing('flip'),
                complete: () => {
                    animCard.remove();
                    handCardElement.classList.remove('swap-out');
                    if (onComplete) onComplete();
                }
            });

            // Flip to reveal old card
            timeline.add({
                targets: inner,
                rotateY: 0,
                duration: flipDuration,
                begin: () => this.playSound('flip')
            });

            // Brief pause to see the card
            timeline.add({ duration: 100 });

            this.activeAnimations.set(`swap-${Date.now()}`, timeline);
        } catch (e) {
            console.error('Face-down swap animation error:', e);
            animCard.remove();
            handCardElement.classList.remove('swap-out');
            if (onComplete) onComplete();
        }
    }

    // Fire-and-forget opponent swap animation
    animateOpponentSwap(playerId, position, discardCard, sourceCardElement, rotation = 0, wasFaceUp = false) {
        if (wasFaceUp && sourceCardElement) {
            // Face-to-face swap: just pulse
            this.pulseSwap(sourceCardElement);
            return;
        }

        if (!sourceCardElement) return;

        const rect = sourceCardElement.getBoundingClientRect();
        const deckColor = this.getDeckColor();

        const animCard = this.createAnimCard(rect, true, deckColor);
        this.setCardContent(animCard, discardCard);

        if (rotation) {
            animCard.style.transform = `rotate(${rotation}deg)`;
        }

        sourceCardElement.classList.add('swap-out');

        const inner = animCard.querySelector('.draw-anim-inner');
        const flipDuration = 245; // 30% faster flip

        try {
            anime.timeline({
                easing: this.getEasing('flip'),
                complete: () => {
                    animCard.remove();
                    this.pulseDiscard();
                }
            })
            .add({
                targets: inner,
                rotateY: 0,
                duration: flipDuration,
                begin: () => this.playSound('flip')
            });
        } catch (e) {
            console.error('Opponent swap animation error:', e);
            animCard.remove();
        }
    }

    // === DISCARD ANIMATIONS ===

    // Animate held card swooping to discard pile
    animateDiscard(heldCardElement, targetCard, onComplete) {
        if (!heldCardElement) {
            if (onComplete) onComplete();
            return;
        }

        const discardRect = this.getDiscardRect();
        if (!discardRect) {
            if (onComplete) onComplete();
            return;
        }

        this.playSound('card');

        try {
            const timeline = anime.timeline({
                easing: this.getEasing('move'),
                complete: () => {
                    this.pulseDiscard();
                    if (onComplete) onComplete();
                }
            });

            timeline.add({
                targets: heldCardElement,
                left: discardRect.left,
                top: discardRect.top,
                width: discardRect.width,
                height: discardRect.height,
                scale: 1,
                duration: 350,
                easing: 'cubicBezier(0.25, 0.1, 0.25, 1)'
            });

            this.activeAnimations.set(`discard-${Date.now()}`, timeline);
        } catch (e) {
            console.error('Discard animation error:', e);
            if (onComplete) onComplete();
        }
    }

    // Animate deck draw then immediate discard (for draw-discard by other players)
    animateDeckToDiscard(card, onComplete) {
        const deckRect = this.getDeckRect();
        const discardRect = this.getDiscardRect();
        if (!deckRect || !discardRect) {
            if (onComplete) onComplete();
            return;
        }

        const deckColor = this.getDeckColor();
        const animCard = this.createAnimCard(deckRect, true, deckColor);
        this.setCardContent(animCard, card);

        const inner = animCard.querySelector('.draw-anim-inner');
        const moveDuration = window.TIMING?.card?.move || 270;

        try {
            const timeline = anime.timeline({
                easing: this.getEasing('move'),
                complete: () => {
                    animCard.remove();
                    this.pulseDiscard();
                    if (onComplete) onComplete();
                }
            });

            // Small delay
            timeline.add({ duration: 50 });

            // Move to discard while flipping
            timeline.add({
                targets: animCard,
                left: discardRect.left,
                top: discardRect.top,
                duration: moveDuration,
                begin: () => this.playSound('card')
            });

            timeline.add({
                targets: inner,
                rotateY: 0,
                duration: moveDuration * 0.8,
                easing: this.getEasing('flip')
            }, `-=${moveDuration * 0.6}`);

            this.activeAnimations.set(`deckToDiscard-${Date.now()}`, timeline);
        } catch (e) {
            console.error('Deck to discard animation error:', e);
            animCard.remove();
            if (onComplete) onComplete();
        }
    }

    // === AMBIENT EFFECTS (looping) ===

    // Your turn to draw - quick rattlesnake shake every few seconds
    startTurnPulse(element) {
        if (!element) return;

        const id = 'turnPulse';
        this.stopTurnPulse(element);

        // Quick shake animation
        const doShake = () => {
            if (!this.activeAnimations.has(id)) return;

            anime({
                targets: element,
                translateX: [0, -4, 4, -3, 2, 0],
                duration: 200,
                easing: 'easeInOutQuad'
            });
        };

        // Do initial shake, then repeat every 3 seconds
        doShake();
        const interval = setInterval(doShake, 3000);
        this.activeAnimations.set(id, { interval });
    }

    stopTurnPulse(element) {
        const id = 'turnPulse';
        const existing = this.activeAnimations.get(id);
        if (existing) {
            if (existing.interval) clearInterval(existing.interval);
            if (existing.pause) existing.pause();
            this.activeAnimations.delete(id);
        }
        if (element) {
            anime.remove(element);
            element.style.transform = '';
        }
    }

    // CPU thinking - glow on discard pile
    startCpuThinking(element) {
        if (!element) return;

        const id = 'cpuThinking';
        this.stopCpuThinking(element);

        const config = window.TIMING?.anime?.loop?.cpuThinking || { duration: 1500 };

        try {
            const anim = anime({
                targets: element,
                boxShadow: [
                    '0 4px 12px rgba(0,0,0,0.3)',
                    '0 4px 12px rgba(0,0,0,0.3), 0 0 18px rgba(59, 130, 246, 0.5)',
                    '0 4px 12px rgba(0,0,0,0.3)'
                ],
                duration: config.duration,
                easing: 'easeInOutSine',
                loop: true
            });
            this.activeAnimations.set(id, anim);
        } catch (e) {
            console.error('CPU thinking animation error:', e);
        }
    }

    stopCpuThinking(element) {
        const id = 'cpuThinking';
        const existing = this.activeAnimations.get(id);
        if (existing) {
            existing.pause();
            this.activeAnimations.delete(id);
        }
        if (element) {
            anime.remove(element);
            element.style.boxShadow = '';
        }
    }

    // Initial flip phase - clickable cards glow
    startInitialFlipPulse(element) {
        if (!element) return;

        const id = `initialFlipPulse-${element.dataset.position || Date.now()}`;

        const config = window.TIMING?.anime?.loop?.initialFlipGlow || { duration: 1500 };

        try {
            const anim = anime({
                targets: element,
                boxShadow: [
                    '0 0 0 2px rgba(244, 164, 96, 0.5)',
                    '0 0 0 4px rgba(244, 164, 96, 0.8), 0 0 15px rgba(244, 164, 96, 0.4)',
                    '0 0 0 2px rgba(244, 164, 96, 0.5)'
                ],
                duration: config.duration,
                easing: 'easeInOutSine',
                loop: true
            });
            this.activeAnimations.set(id, anim);
        } catch (e) {
            console.error('Initial flip pulse animation error:', e);
        }
    }

    stopInitialFlipPulse(element) {
        if (!element) return;

        const id = `initialFlipPulse-${element.dataset.position || ''}`;
        // Try to find and stop any matching animation
        for (const [key, anim] of this.activeAnimations) {
            if (key.startsWith('initialFlipPulse')) {
                anim.pause();
                this.activeAnimations.delete(key);
            }
        }
        anime.remove(element);
        element.style.boxShadow = '';
    }

    stopAllInitialFlipPulses() {
        for (const [key, anim] of this.activeAnimations) {
            if (key.startsWith('initialFlipPulse')) {
                anim.pause();
                this.activeAnimations.delete(key);
            }
        }
    }

    // === ONE-SHOT EFFECTS ===

    // Pulse when card lands on discard
    pulseDiscard() {
        const discard = document.getElementById('discard');
        if (!discard) return;

        const duration = window.TIMING?.feedback?.discardLand || 375;

        try {
            anime({
                targets: discard,
                scale: [1, 1.08, 1],
                duration: duration,
                easing: 'easeOutQuad'
            });
        } catch (e) {
            console.error('Discard pulse error:', e);
        }
    }

    // Pulse effect on swap
    pulseSwap(element) {
        if (!element) return;

        this.playSound('card');

        try {
            anime({
                targets: element,
                scale: [1, 0.92, 1.08, 1],
                filter: ['brightness(1)', 'brightness(0.85)', 'brightness(1.15)', 'brightness(1)'],
                duration: 400,
                easing: 'easeOutQuad'
            });
        } catch (e) {
            console.error('Swap pulse error:', e);
        }
    }

    // Pop-in effect when card appears
    popIn(element) {
        if (!element) return;

        try {
            anime({
                targets: element,
                scale: [0.5, 1.25, 1.15],
                opacity: [0, 1, 1],
                duration: 300,
                easing: 'easeOutQuad'
            });
        } catch (e) {
            console.error('Pop-in error:', e);
        }
    }

    // Draw pulse effect (gold ring expanding)
    startDrawPulse(element) {
        if (!element) return;

        element.classList.add('draw-pulse');
        setTimeout(() => {
            element.classList.remove('draw-pulse');
        }, 450);
    }

    // === HELPER METHODS ===

    isBusy() {
        return this.isAnimating;
    }

    cancel() {
        this.cancelAll();
    }
}

// Create global instance
window.cardAnimations = new CardAnimations();

// Backwards compatibility - point drawAnimations to the new system
window.drawAnimations = window.cardAnimations;
