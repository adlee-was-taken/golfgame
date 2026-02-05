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

    getDealerRect(dealerId) {
        if (!dealerId) return null;

        // Check if dealer is the local player
        const playerArea = document.querySelector('.player-area');
        if (playerArea && window.game?.playerId === dealerId) {
            return playerArea.getBoundingClientRect();
        }

        // Check opponents
        const opponentArea = document.querySelector(`.opponent-area[data-player-id="${dealerId}"]`);
        if (opponentArea) {
            return opponentArea.getBoundingClientRect();
        }

        return null;
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

        // Set position BEFORE appending to avoid flash at 0,0
        if (rect) {
            card.style.left = rect.left + 'px';
            card.style.top = rect.top + 'px';
            card.style.width = rect.width + 'px';
            card.style.height = rect.height + 'px';
        }

        // Apply deck color to back
        if (deckColor) {
            const back = card.querySelector('.draw-anim-back');
            back.classList.add(`back-${deckColor}`);
        }

        if (showBack) {
            card.querySelector('.draw-anim-inner').style.transform = 'rotateY(180deg)';
        }

        // Now append to body after all styles are set
        document.body.appendChild(card);

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
        // Cancel all tracked anime.js animations to prevent stale callbacks
        for (const [id, anim] of this.activeAnimations) {
            if (anim && typeof anim.pause === 'function') {
                anim.pause();
            }
        }
        this.activeAnimations.clear();

        // Remove all animation card elements (including those marked as animating)
        document.querySelectorAll('.draw-anim-card').forEach(el => {
            delete el.dataset.animating;
            el.remove();
        });

        // Restore discard pile visibility if it was hidden during animation
        const discardPile = document.getElementById('discard');
        if (discardPile && discardPile.style.opacity === '0') {
            discardPile.style.opacity = '';
        }

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
        animCard.dataset.animating = 'true'; // Mark as actively animating
        const inner = animCard.querySelector('.draw-anim-inner');

        if (cardData) {
            this.setCardContent(animCard, cardData);
        }

        this.playSound('draw-deck');

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
                duration: 63,
                easing: this.getEasing('lift')
            });

            // Move to holding position
            timeline.add({
                targets: animCard,
                left: holdingRect.left,
                top: holdingRect.top,
                translateY: 0,
                duration: 105,
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
        animCard.dataset.animating = 'true'; // Mark as actively animating
        this.setCardContent(animCard, cardData);

        // Hide actual discard pile during animation to prevent visual conflict
        const discardPile = document.getElementById('discard');
        if (discardPile) {
            discardPile.style.opacity = '0';
        }

        this.playSound('draw-discard');

        // Failsafe cleanup
        this.cleanupTimeout = setTimeout(() => {
            if (discardPile) discardPile.style.opacity = '';
            this.cleanup();
            if (onComplete) onComplete();
        }, 600);

        try {
            const timeline = anime.timeline({
                easing: this.getEasing('move'),
                complete: () => {
                    if (discardPile) discardPile.style.opacity = '';
                    this.cleanup();
                    if (onComplete) onComplete();
                }
            });

            // Quick decisive lift
            timeline.add({
                targets: animCard,
                translateY: -12,
                scale: 1.05,
                duration: 25
            });

            // Direct move to holding
            timeline.add({
                targets: animCard,
                left: holdingRect.left,
                top: holdingRect.top,
                translateY: 0,
                scale: 1,
                duration: 76
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

        // Helper to restore card to face-up state
        const restoreCard = () => {
            animCard.remove();
            cardElement.classList.remove('swap-out');
            // Restore face-up appearance
            if (cardData) {
                cardElement.className = 'card card-front';
                if (cardData.rank === '★') {
                    cardElement.classList.add('joker');
                    const icon = cardData.suit === 'hearts' ? '🐉' : '👹';
                    cardElement.innerHTML = `<span class="joker-icon">${icon}</span><span class="joker-label">Joker</span>`;
                } else {
                    const isRed = cardData.suit === 'hearts' || cardData.suit === 'diamonds';
                    cardElement.classList.add(isRed ? 'red' : 'black');
                    cardElement.innerHTML = `${cardData.rank}<br>${this.getSuitSymbol(cardData.suit)}`;
                }
            }
        };

        try {
            anime({
                targets: inner,
                rotateY: 0,
                duration: duration,
                easing: this.getEasing('flip'),
                begin: () => this.playSound('flip'),
                complete: restoreCard
            });
        } catch (e) {
            console.error('Opponent flip animation error:', e);
            restoreCard();
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
                translateX: [0, -8, 8, -6, 4, 0],
                duration: 400,
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

    // V3_06: Opponent area thinking glow
    startOpponentThinking(area) {
        if (!area) return;
        const playerId = area.dataset.playerId;
        const id = `opponentThinking-${playerId}`;

        // Don't restart if already running for this player
        if (this.activeAnimations.has(id)) return;

        try {
            const anim = anime({
                targets: area,
                boxShadow: [
                    '0 0 0 rgba(244, 164, 96, 0)',
                    '0 0 15px rgba(244, 164, 96, 0.4)',
                    '0 0 0 rgba(244, 164, 96, 0)'
                ],
                duration: 1500,
                easing: 'easeInOutSine',
                loop: true
            });
            this.activeAnimations.set(id, anim);
        } catch (e) {
            console.error('Opponent thinking animation error:', e);
        }
    }

    stopOpponentThinking(area) {
        if (!area) return;
        const playerId = area.dataset.playerId;
        const id = `opponentThinking-${playerId}`;
        const existing = this.activeAnimations.get(id);
        if (existing) {
            existing.pause();
            this.activeAnimations.delete(id);
        }
        anime.remove(area);
        area.style.boxShadow = '';
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

    // V3_11: Physical swap animation - cards visibly exchange positions
    animatePhysicalSwap(handCardEl, heldCardEl, onComplete) {
        if (!handCardEl || !heldCardEl) {
            if (onComplete) onComplete();
            return;
        }

        const T = window.TIMING?.swap || { lift: 80, arc: 280, settle: 60 };
        const handRect = handCardEl.getBoundingClientRect();
        const heldRect = heldCardEl.getBoundingClientRect();
        const discardRect = this.getDiscardRect();

        if (!discardRect) {
            this.pulseSwap(handCardEl);
            if (onComplete) setTimeout(onComplete, 400);
            return;
        }

        // Create traveling clones
        const travelingHand = this.createTravelingCard(handCardEl);
        const travelingHeld = this.createTravelingCard(heldCardEl);
        document.body.appendChild(travelingHand);
        document.body.appendChild(travelingHeld);

        // Position at source
        this.positionAt(travelingHand, handRect);
        this.positionAt(travelingHeld, heldRect);

        // Hide originals
        handCardEl.style.visibility = 'hidden';
        heldCardEl.style.visibility = 'hidden';

        this.playSound('card');

        try {
            const timeline = anime.timeline({
                easing: this.getEasing('move'),
                complete: () => {
                    travelingHand.remove();
                    travelingHeld.remove();
                    handCardEl.style.visibility = '';
                    heldCardEl.style.visibility = '';
                    this.activeAnimations.delete('physicalSwap');
                    if (onComplete) onComplete();
                }
            });

            // Arc midpoints
            const arcUp = Math.min(handRect.top, heldRect.top) - 30;

            // Lift
            timeline.add({
                targets: [travelingHand, travelingHeld],
                translateY: -8,
                scale: 1.02,
                duration: T.lift,
                easing: this.getEasing('lift')
            });

            // Hand card arcs to discard
            timeline.add({
                targets: travelingHand,
                left: discardRect.left,
                top: [
                    { value: arcUp, duration: T.arc / 2 },
                    { value: discardRect.top, duration: T.arc / 2 }
                ],
                rotate: [0, -3, 0],
                duration: T.arc,
            }, `-=${T.lift / 2}`);

            // Held card arcs to hand slot (parallel)
            timeline.add({
                targets: travelingHeld,
                left: handRect.left,
                top: [
                    { value: arcUp + 20, duration: T.arc / 2 },
                    { value: handRect.top, duration: T.arc / 2 }
                ],
                rotate: [0, 3, 0],
                duration: T.arc,
            }, `-=${T.arc + T.lift / 2}`);

            // Settle
            timeline.add({
                targets: [travelingHand, travelingHeld],
                translateY: 0,
                scale: 1,
                duration: T.settle,
            });

            this.activeAnimations.set('physicalSwap', timeline);
        } catch (e) {
            console.error('Physical swap animation error:', e);
            travelingHand.remove();
            travelingHeld.remove();
            handCardEl.style.visibility = '';
            heldCardEl.style.visibility = '';
            if (onComplete) onComplete();
        }
    }

    // Unified swap animation for ALL swap scenarios
    // handCardData: the card in hand being swapped out (goes to discard)
    // heldCardData: the drawn/held card being swapped in (goes to hand)
    // handRect: position of the hand card
    // heldRect: position of the held card (or null to use default holding position)
    // options: { rotation, wasHandFaceDown, onComplete }
    animateUnifiedSwap(handCardData, heldCardData, handRect, heldRect, options = {}) {
        const { rotation = 0, wasHandFaceDown = false, onComplete } = options;
        const T = window.TIMING?.swap || { lift: 80, arc: 280, settle: 60 };
        const discardRect = this.getDiscardRect();

        // Safety checks
        if (!handRect || !discardRect || !handCardData || !heldCardData) {
            console.warn('animateUnifiedSwap: missing required data');
            if (onComplete) onComplete();
            return;
        }

        // Use holding position if heldRect not provided
        if (!heldRect) {
            heldRect = this.getHoldingRect();
        }
        if (!heldRect) {
            if (onComplete) onComplete();
            return;
        }

        // Wait for any in-progress draw animation to complete
        // Check if there's an active draw animation by looking for overlay cards
        const existingDrawCards = document.querySelectorAll('.draw-anim-card[data-animating="true"]');
        if (existingDrawCards.length > 0) {
            // Draw animation still in progress - wait a bit and retry
            setTimeout(() => {
                // Clean up the draw animation overlay
                existingDrawCards.forEach(el => {
                    delete el.dataset.animating;
                    el.remove();
                });
                // Now run the swap animation
                this._runUnifiedSwap(handCardData, heldCardData, handRect, heldRect, discardRect, T, rotation, wasHandFaceDown, onComplete);
            }, 100);
            return;
        }

        this._runUnifiedSwap(handCardData, heldCardData, handRect, heldRect, discardRect, T, rotation, wasHandFaceDown, onComplete);
    }

    _runUnifiedSwap(handCardData, heldCardData, handRect, heldRect, discardRect, T, rotation, wasHandFaceDown, onComplete) {
        // Create the two traveling cards
        const travelingHand = this.createCardFromData(handCardData, handRect, rotation);
        const travelingHeld = this.createCardFromData(heldCardData, heldRect, 0);
        travelingHand.dataset.animating = 'true';
        travelingHeld.dataset.animating = 'true';
        document.body.appendChild(travelingHand);
        document.body.appendChild(travelingHeld);

        this.playSound('card');

        // If hand card was face-down, flip it first
        if (wasHandFaceDown) {
            const inner = travelingHand.querySelector('.draw-anim-inner');
            if (inner) {
                // Start showing back
                inner.style.transform = 'rotateY(180deg)';

                // Flip to reveal, then do the swap
                this.playSound('flip');
                anime({
                    targets: inner,
                    rotateY: 0,
                    duration: 245,
                    easing: this.getEasing('flip'),
                    complete: () => {
                        this._doArcSwap(travelingHand, travelingHeld, handRect, heldRect, discardRect, T, rotation, onComplete);
                    }
                });
                return;
            }
        }

        // Both face-up, do the swap immediately
        this._doArcSwap(travelingHand, travelingHeld, handRect, heldRect, discardRect, T, rotation, onComplete);
    }

    _doArcSwap(travelingHand, travelingHeld, handRect, heldRect, discardRect, T, rotation, onComplete) {
        try {
            const arcUp = Math.min(handRect.top, heldRect.top, discardRect.top) - 40;

            const timeline = anime.timeline({
                easing: this.getEasing('move'),
                complete: () => {
                    travelingHand.remove();
                    travelingHeld.remove();
                    this.activeAnimations.delete('unifiedSwap');
                    if (onComplete) onComplete();
                }
            });

            // Lift both cards
            timeline.add({
                targets: [travelingHand, travelingHeld],
                translateY: -10,
                scale: 1.03,
                duration: T.lift,
                easing: this.getEasing('lift')
            });

            // Hand card arcs to discard (apply counter-rotation to land flat)
            timeline.add({
                targets: travelingHand,
                left: discardRect.left,
                top: [
                    { value: arcUp, duration: T.arc / 2 },
                    { value: discardRect.top, duration: T.arc / 2 }
                ],
                width: discardRect.width,
                height: discardRect.height,
                rotate: [rotation, rotation - 3, 0],
                duration: T.arc,
            }, `-=${T.lift / 2}`);

            // Held card arcs to hand slot (apply rotation to match hand position)
            timeline.add({
                targets: travelingHeld,
                left: handRect.left,
                top: [
                    { value: arcUp + 25, duration: T.arc / 2 },
                    { value: handRect.top, duration: T.arc / 2 }
                ],
                width: handRect.width,
                height: handRect.height,
                rotate: [0, 3, rotation],
                duration: T.arc,
            }, `-=${T.arc + T.lift / 2}`);

            // Settle
            timeline.add({
                targets: [travelingHand, travelingHeld],
                translateY: 0,
                scale: 1,
                duration: T.settle,
            });

            this.activeAnimations.set('unifiedSwap', timeline);
        } catch (e) {
            console.error('Unified swap animation error:', e);
            travelingHand.remove();
            travelingHeld.remove();
            if (onComplete) onComplete();
        }
    }

    // Animate held card (drawn from deck) to discard pile
    animateHeldToDiscard(cardData, heldRect, onComplete) {
        const discardRect = this.getDiscardRect();

        if (!heldRect || !discardRect) {
            if (onComplete) onComplete();
            return;
        }

        const T = window.TIMING?.swap || { lift: 80, arc: 280, settle: 60 };

        // Create a traveling card showing the face at the held card's actual position
        const travelingCard = this.createCardFromData(cardData, heldRect, 0);
        travelingCard.dataset.animating = 'true';
        document.body.appendChild(travelingCard);

        this.playSound('card');

        try {
            // Arc peak slightly above both positions
            const arcUp = Math.min(heldRect.top, discardRect.top) - 30;

            const timeline = anime.timeline({
                easing: this.getEasing('move'),
                complete: () => {
                    travelingCard.remove();
                    this.activeAnimations.delete('heldToDiscard');
                    if (onComplete) onComplete();
                }
            });

            // Lift
            timeline.add({
                targets: travelingCard,
                translateY: -8,
                scale: 1.02,
                duration: T.lift,
                easing: this.getEasing('lift')
            });

            // Arc to discard
            timeline.add({
                targets: travelingCard,
                left: discardRect.left,
                top: [
                    { value: arcUp, duration: T.arc / 2 },
                    { value: discardRect.top, duration: T.arc / 2 }
                ],
                width: discardRect.width,
                height: discardRect.height,
                rotate: [0, -2, 0],
                duration: T.arc,
            }, `-=${T.lift / 2}`);

            // Settle
            timeline.add({
                targets: travelingCard,
                translateY: 0,
                scale: 1,
                duration: T.settle,
            });

            this.activeAnimations.set('heldToDiscard', timeline);
        } catch (e) {
            console.error('Held to discard animation error:', e);
            travelingCard.remove();
            if (onComplete) onComplete();
        }
    }

    // Animate opponent/CPU discarding from holding position (hold → discard)
    // The draw animation already handled deck → hold, so this just completes the motion
    animateOpponentDiscard(cardData, onComplete) {
        const holdingRect = this.getHoldingRect();
        const discardRect = this.getDiscardRect();

        if (!holdingRect || !discardRect) {
            if (onComplete) onComplete();
            return;
        }

        // Wait for any in-progress draw animation to complete
        const existingDrawCards = document.querySelectorAll('.draw-anim-card[data-animating="true"]');
        if (existingDrawCards.length > 0) {
            // Draw animation still in progress - wait a bit and retry
            setTimeout(() => {
                // Clean up the draw animation overlay
                existingDrawCards.forEach(el => {
                    delete el.dataset.animating;
                    el.remove();
                });
                // Now run the discard animation
                this._runOpponentDiscard(cardData, holdingRect, discardRect, onComplete);
            }, 100);
            return;
        }

        this._runOpponentDiscard(cardData, holdingRect, discardRect, onComplete);
    }

    _runOpponentDiscard(cardData, holdingRect, discardRect, onComplete) {
        const T = window.TIMING?.swap || { lift: 80, arc: 280, settle: 60 };

        // Create card at holding position, face-up (already revealed by draw animation)
        const travelingCard = this.createAnimCard(holdingRect, false);
        travelingCard.dataset.animating = 'true'; // Mark as actively animating
        this.setCardContent(travelingCard, cardData);

        this.playSound('card');

        try {
            // Arc peak slightly above both positions
            const arcUp = Math.min(holdingRect.top, discardRect.top) - 30;

            const timeline = anime.timeline({
                easing: this.getEasing('move'),
                complete: () => {
                    travelingCard.remove();
                    this.activeAnimations.delete('opponentDiscard');
                    if (onComplete) onComplete();
                }
            });

            // Lift
            timeline.add({
                targets: travelingCard,
                translateY: -8,
                scale: 1.02,
                duration: T.lift,
                easing: this.getEasing('lift')
            });

            // Arc to discard
            timeline.add({
                targets: travelingCard,
                left: discardRect.left,
                top: [
                    { value: arcUp, duration: T.arc / 2 },
                    { value: discardRect.top, duration: T.arc / 2 }
                ],
                width: discardRect.width,
                height: discardRect.height,
                translateY: 0,
                scale: 1,
                rotate: [0, -2, 0],
                duration: T.arc,
            });

            // Settle
            timeline.add({
                targets: travelingCard,
                translateY: 0,
                scale: 1,
                duration: T.settle,
            });

            this.activeAnimations.set('opponentDiscard', timeline);
        } catch (e) {
            console.error('Opponent discard animation error:', e);
            travelingCard.remove();
            if (onComplete) onComplete();
        }
    }

    createCardFromData(cardData, rect, rotation = 0) {
        const card = document.createElement('div');
        card.className = 'draw-anim-card';
        card.innerHTML = `
            <div class="draw-anim-inner">
                <div class="draw-anim-front card card-front"></div>
                <div class="draw-anim-back card card-back"></div>
            </div>
        `;

        // Apply deck color to back
        const deckColor = this.getDeckColor();
        if (deckColor) {
            const back = card.querySelector('.draw-anim-back');
            back.classList.add(`back-${deckColor}`);
        }

        // Set front content
        this.setCardContent(card, cardData);

        // Position and size
        card.style.left = rect.left + 'px';
        card.style.top = rect.top + 'px';
        card.style.width = rect.width + 'px';
        card.style.height = rect.height + 'px';

        if (rotation) {
            card.style.transform = `rotate(${rotation}deg)`;
        }

        return card;
    }

    createTravelingCard(sourceEl) {
        const clone = sourceEl.cloneNode(true);
        // Preserve original classes and add traveling-card
        clone.classList.add('traveling-card');
        // Remove classes that interfere with animation
        clone.classList.remove('hidden', 'your-turn-pulse', 'held-card-floating', 'swap-out');
        clone.removeAttribute('id');
        // Override positioning for animation
        clone.style.position = 'fixed';
        clone.style.pointerEvents = 'none';
        clone.style.zIndex = '1000';
        clone.style.transform = 'none';
        clone.style.transformOrigin = 'center center';
        clone.style.borderRadius = '6px';
        clone.style.overflow = 'hidden';
        return clone;
    }

    positionAt(element, rect) {
        element.style.left = `${rect.left}px`;
        element.style.top = `${rect.top}px`;
        element.style.width = `${rect.width}px`;
        element.style.height = `${rect.height}px`;
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

    // === DEALING ANIMATION ===

    async animateDealing(gameState, getPlayerRect, onComplete) {
        const T = window.TIMING?.dealing || {};
        const shufflePause = T.shufflePause || 400;
        const cardFlyTime = T.cardFlyTime || 150;
        const cardStagger = T.cardStagger || 80;
        const roundPause = T.roundPause || 50;
        const discardFlipDelay = T.discardFlipDelay || 200;

        // Get deck position as the source for dealt cards
        // Cards are dealt from the deck, not from the dealer's position
        const deckRect = this.getDeckRect();
        if (!deckRect) {
            if (onComplete) onComplete();
            return;
        }

        // Get player order starting from dealer's left
        const dealerIdx = gameState.dealer_idx || 0;
        const playerOrder = this.getDealOrder(gameState.players, dealerIdx);

        // Create container for animation cards
        const container = document.createElement('div');
        container.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;pointer-events:none;z-index:1000;';
        document.body.appendChild(container);

        // Shuffle pause
        await this._delay(shufflePause);

        // Deal 6 rounds of cards
        for (let cardIdx = 0; cardIdx < 6; cardIdx++) {
            for (const player of playerOrder) {
                const targetRect = getPlayerRect(player.id, cardIdx);
                if (!targetRect) continue;

                // Use individual card's deck color if available
                const playerCards = player.cards || [];
                const cardData = playerCards[cardIdx];
                const deckColors = gameState.deck_colors || window.currentDeckColors || ['red', 'blue', 'gold'];
                const deckColor = cardData && cardData.deck_id !== undefined
                    ? deckColors[cardData.deck_id] || deckColors[0]
                    : this.getDeckColor();
                const card = this.createAnimCard(deckRect, true, deckColor);
                container.appendChild(card);

                // Move card from deck to target via anime.js
                // Animate position and size (deck cards are larger than player cards)
                try {
                    anime({
                        targets: card,
                        left: targetRect.left,
                        top: targetRect.top,
                        width: targetRect.width,
                        height: targetRect.height,
                        duration: cardFlyTime,
                        easing: this.getEasing('move'),
                    });
                } catch (e) {
                    console.error('Deal animation error:', e);
                }

                this.playSound('card');
                await this._delay(cardStagger);
            }

            if (cardIdx < 5) {
                await this._delay(roundPause);
            }
        }

        // Wait for last cards to land
        await this._delay(cardFlyTime);

        // Flip discard
        if (gameState.discard_top) {
            await this._delay(discardFlipDelay);
            this.playSound('flip');
        }

        // Clean up
        container.remove();
        if (onComplete) onComplete();
    }

    getDealOrder(players, dealerIdx) {
        const order = [...players];
        const startIdx = (dealerIdx + 1) % order.length;
        return [...order.slice(startIdx), ...order.slice(0, startIdx)];
    }

    _delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // === PAIR CELEBRATION ===

    celebratePair(cardElement1, cardElement2) {
        this.playSound('pair');

        const duration = window.TIMING?.celebration?.pairDuration || 400;

        [cardElement1, cardElement2].forEach(el => {
            if (!el) return;

            el.style.zIndex = '10';

            try {
                anime({
                    targets: el,
                    boxShadow: [
                        '0 0 0 0 rgba(255, 215, 0, 0)',
                        '0 0 15px 8px rgba(255, 215, 0, 0.5)',
                        '0 0 0 0 rgba(255, 215, 0, 0)'
                    ],
                    scale: [1, 1.05, 1],
                    duration: duration,
                    easing: 'easeOutQuad',
                    complete: () => {
                        el.style.zIndex = '';
                    }
                });
            } catch (e) {
                console.error('Pair celebration error:', e);
                el.style.zIndex = '';
            }
        });
    }

    // === CARD HOVER EFFECTS ===

    // Animate card hover in (called on mouseenter)
    hoverIn(element, isSwappable = false) {
        if (!element || element.dataset.hoverAnimating === 'true') return;

        element.dataset.hoverAnimating = 'true';

        try {
            anime.remove(element); // Cancel any existing animation

            if (isSwappable) {
                // Swappable card - lift and scale
                anime({
                    targets: element,
                    translateY: -5,
                    scale: 1.02,
                    duration: 150,
                    easing: 'easeOutQuad',
                    complete: () => {
                        element.dataset.hoverAnimating = 'false';
                    }
                });
            } else {
                // Regular card - just scale
                anime({
                    targets: element,
                    scale: 1.05,
                    duration: 150,
                    easing: 'easeOutQuad',
                    complete: () => {
                        element.dataset.hoverAnimating = 'false';
                    }
                });
            }
        } catch (e) {
            console.error('Hover in error:', e);
            element.dataset.hoverAnimating = 'false';
        }
    }

    // Animate card hover out (called on mouseleave)
    hoverOut(element) {
        if (!element) return;

        element.dataset.hoverAnimating = 'true';

        try {
            anime.remove(element); // Cancel any existing animation

            anime({
                targets: element,
                translateY: 0,
                scale: 1,
                duration: 150,
                easing: 'easeOutQuad',
                complete: () => {
                    element.dataset.hoverAnimating = 'false';
                    element.style.transform = ''; // Clean up inline styles
                }
            });
        } catch (e) {
            console.error('Hover out error:', e);
            element.dataset.hoverAnimating = 'false';
            element.style.transform = '';
        }
    }

    // Initialize hover listeners on card elements
    initHoverListeners(container = document) {
        const cards = container.querySelectorAll('.card');
        cards.forEach(card => {
            // Skip if already initialized
            if (card.dataset.hoverInitialized) return;
            card.dataset.hoverInitialized = 'true';

            card.addEventListener('mouseenter', () => {
                // Check if card is in a swappable context
                const isSwappable = card.closest('.player-area.can-swap') !== null;
                this.hoverIn(card, isSwappable);
            });

            card.addEventListener('mouseleave', () => {
                this.hoverOut(card);
            });
        });
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

// Initialize hover listeners when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.cardAnimations.initHoverListeners();
    });
} else {
    window.cardAnimations.initHoverListeners();
}
