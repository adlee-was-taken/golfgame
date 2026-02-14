// Golf Card Game - Client Application

// Debug logging - set to true to see detailed state/animation logs
const DEBUG_GAME = false;

function debugLog(category, message, data = null) {
    if (!DEBUG_GAME) return;
    const timestamp = new Date().toISOString().substr(11, 12);
    const prefix = `[${timestamp}] [${category}]`;
    if (data) {
        console.log(prefix, message, data);
    } else {
        console.log(prefix, message);
    }
}

class GolfGame {
    constructor() {
        this.ws = null;
        this.playerId = null;
        this.roomCode = null;
        this.isHost = false;
        this.gameState = null;
        this.drawnCard = null;
        this.drawnFromDiscard = false;
        this.selectedCards = [];
        this.waitingForFlip = false;
        this.currentPlayers = [];
        this.allProfiles = [];
        this.soundEnabled = true;
        this.audioCtx = null;

        // Swap animation state
        this.swapAnimationInProgress = false;
        this.swapAnimationCardEl = null;
        this.swapAnimationFront = null;
        this.swapAnimationContentSet = false;
        this.pendingSwapData = null;
        this.pendingGameState = null;

        // Track cards we've locally flipped (for immediate feedback during selection)
        this.locallyFlippedCards = new Set();

        // Animation lock - prevent overlapping animations on same elements
        this.animatingPositions = new Set();

        // Track opponent swap animation in progress (to apply swap-out class after render)
        this.opponentSwapAnimation = null; // { playerId, position }

        // Track draw pulse animation in progress (defer held card display until pulse completes)
        this.drawPulseAnimation = false;

        // Track local discard animation in progress (prevent renderGame from updating discard)
        this.localDiscardAnimating = false;

        // Track opponent discard animation in progress (prevent renderGame from updating discard)
        this.opponentDiscardAnimating = false;

        // Track deal animation in progress (suppress flip prompts until dealing complete)
        this.dealAnimationInProgress = false;

        // Track round winners for visual highlight
        this.roundWinnerNames = new Set();

        // V3_15: Discard pile history
        this.discardHistory = [];
        this.maxDiscardHistory = 5;

        this.initElements();
        this.initAudio();
        this.initCardTooltips();
        this.bindEvents();
        this.checkUrlParams();
    }

    checkUrlParams() {
        // Handle ?room=XXXX share links
        const params = new URLSearchParams(window.location.search);
        const roomCode = params.get('room');
        if (roomCode) {
            this.roomCodeInput.value = roomCode.toUpperCase();
            // Focus name input so user can quickly enter name and join
            this.playerNameInput.focus();
            // Clean up URL without reloading
            window.history.replaceState({}, '', window.location.pathname);
        }
    }

    initAudio() {
        // Initialize audio context on first user interaction
        const initCtx = () => {
            if (!this.audioCtx) {
                this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            document.removeEventListener('click', initCtx);
        };
        document.addEventListener('click', initCtx);
    }

    playSound(type = 'click') {
        if (!this.soundEnabled || !this.audioCtx) return;

        const ctx = this.audioCtx;
        const oscillator = ctx.createOscillator();
        const gainNode = ctx.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(ctx.destination);

        if (type === 'click') {
            oscillator.frequency.setValueAtTime(600, ctx.currentTime);
            oscillator.frequency.exponentialRampToValueAtTime(200, ctx.currentTime + 0.05);
            gainNode.gain.setValueAtTime(0.1, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.05);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.05);
        } else if (type === 'card') {
            // V3_16: Card place with variation + noise
            const pitchVar = 1 + (Math.random() - 0.5) * 0.1;
            oscillator.frequency.setValueAtTime(800 * pitchVar, ctx.currentTime);
            oscillator.frequency.exponentialRampToValueAtTime(400 * pitchVar, ctx.currentTime + 0.08);
            gainNode.gain.setValueAtTime(0.08, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.08);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.08);
            this.playNoiseBurst(ctx, 0.02, 0.03);
        } else if (type === 'success') {
            oscillator.frequency.setValueAtTime(400, ctx.currentTime);
            oscillator.frequency.setValueAtTime(600, ctx.currentTime + 0.1);
            gainNode.gain.setValueAtTime(0.1, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.2);
        } else if (type === 'flip') {
            // V3_16: Enhanced sharp snap with noise texture + pitch variation
            const pitchVar = 1 + (Math.random() - 0.5) * 0.15;
            oscillator.type = 'square';
            oscillator.frequency.setValueAtTime(1800 * pitchVar, ctx.currentTime);
            oscillator.frequency.exponentialRampToValueAtTime(600 * pitchVar, ctx.currentTime + 0.02);
            gainNode.gain.setValueAtTime(0.12, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.025);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.025);
            // Add noise burst for paper texture
            this.playNoiseBurst(ctx, 0.03, 0.02);
        } else if (type === 'shuffle') {
            // Multiple quick sounds to simulate shuffling
            for (let i = 0; i < 8; i++) {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.type = 'square';
                const time = ctx.currentTime + i * 0.06;
                osc.frequency.setValueAtTime(200 + Math.random() * 400, time);
                gain.gain.setValueAtTime(0.03, time);
                gain.gain.exponentialRampToValueAtTime(0.001, time + 0.05);
                osc.start(time);
                osc.stop(time + 0.05);
            }
            return; // Early return since we don't use the main oscillator
        } else if (type === 'reject') {
            // Low buzz for rejected action
            oscillator.type = 'sawtooth';
            oscillator.frequency.setValueAtTime(150, ctx.currentTime);
            oscillator.frequency.setValueAtTime(100, ctx.currentTime + 0.08);
            gainNode.gain.setValueAtTime(0.08, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.12);
        } else if (type === 'alert') {
            // Rising triad for final turn announcement
            oscillator.type = 'triangle';
            oscillator.frequency.setValueAtTime(523, ctx.currentTime);      // C5
            oscillator.frequency.setValueAtTime(659, ctx.currentTime + 0.1); // E5
            oscillator.frequency.setValueAtTime(784, ctx.currentTime + 0.2); // G5
            gainNode.gain.setValueAtTime(0.15, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.4);
        } else if (type === 'pair') {
            // Two-tone ding for column pair match
            const osc2 = ctx.createOscillator();
            osc2.connect(gainNode);
            oscillator.frequency.setValueAtTime(880, ctx.currentTime);   // A5
            osc2.frequency.setValueAtTime(1108, ctx.currentTime);        // C#6
            gainNode.gain.setValueAtTime(0.1, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
            oscillator.start(ctx.currentTime);
            osc2.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.3);
            osc2.stop(ctx.currentTime + 0.3);
        } else if (type === 'draw-deck') {
            // Mysterious slide + rise for unknown card
            oscillator.type = 'triangle';
            oscillator.frequency.setValueAtTime(300, ctx.currentTime);
            oscillator.frequency.exponentialRampToValueAtTime(500, ctx.currentTime + 0.1);
            oscillator.frequency.exponentialRampToValueAtTime(350, ctx.currentTime + 0.15);
            gainNode.gain.setValueAtTime(0.08, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.2);
        } else if (type === 'draw-discard') {
            // Quick decisive grab sound
            oscillator.type = 'square';
            oscillator.frequency.setValueAtTime(600, ctx.currentTime);
            oscillator.frequency.exponentialRampToValueAtTime(300, ctx.currentTime + 0.05);
            gainNode.gain.setValueAtTime(0.08, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.06);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.06);
        } else if (type === 'knock') {
            // Dramatic low thud for knock early
            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(80, ctx.currentTime);
            oscillator.frequency.exponentialRampToValueAtTime(40, ctx.currentTime + 0.15);
            gainNode.gain.setValueAtTime(0.4, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.2);
            // Secondary impact
            setTimeout(() => {
                const osc2 = ctx.createOscillator();
                const gain2 = ctx.createGain();
                osc2.connect(gain2);
                gain2.connect(ctx.destination);
                osc2.type = 'sine';
                osc2.frequency.setValueAtTime(60, ctx.currentTime);
                gain2.gain.setValueAtTime(0.2, ctx.currentTime);
                gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
                osc2.start(ctx.currentTime);
                osc2.stop(ctx.currentTime + 0.1);
            }, 100);
        }
    }

    // V3_16: Noise burst for realistic card texture
    playNoiseBurst(ctx, volume, duration) {
        try {
            const bufferSize = Math.floor(ctx.sampleRate * duration);
            const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
            const output = buffer.getChannelData(0);
            for (let i = 0; i < bufferSize; i++) {
                output[i] = Math.random() * 2 - 1;
            }
            const noise = ctx.createBufferSource();
            noise.buffer = buffer;
            const noiseGain = ctx.createGain();
            noise.connect(noiseGain);
            noiseGain.connect(ctx.destination);
            noiseGain.gain.setValueAtTime(volume, ctx.currentTime);
            noiseGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
            noise.start(ctx.currentTime);
            noise.stop(ctx.currentTime + duration);
        } catch (e) {
            // Noise burst is optional, don't break if it fails
        }
    }

    toggleSound() {
        this.soundEnabled = !this.soundEnabled;
        this.muteBtn.textContent = this.soundEnabled ? '🔊' : '🔇';
        this.playSound('click');
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // --- V3_13: Card Value Tooltips ---

    initCardTooltips() {
        this.tooltip = document.createElement('div');
        this.tooltip.className = 'card-value-tooltip hidden';
        document.body.appendChild(this.tooltip);
        this.tooltipTimeout = null;
    }

    bindCardTooltipEvents(cardElement, cardData) {
        if (!cardData?.face_up || !cardData?.rank) return;

        // Desktop hover with delay
        cardElement.addEventListener('mouseenter', () => {
            this.scheduleTooltip(cardElement, cardData);
        });
        cardElement.addEventListener('mouseleave', () => {
            this.hideCardTooltip();
        });

        // Mobile long-press
        let pressTimer = null;
        cardElement.addEventListener('touchstart', () => {
            pressTimer = setTimeout(() => {
                this.showCardTooltip(cardElement, cardData);
            }, 400);
        }, { passive: true });
        cardElement.addEventListener('touchend', () => {
            clearTimeout(pressTimer);
            this.hideCardTooltip();
        });
        cardElement.addEventListener('touchmove', () => {
            clearTimeout(pressTimer);
            this.hideCardTooltip();
        }, { passive: true });
    }

    scheduleTooltip(cardElement, cardData) {
        this.hideCardTooltip();
        if (!cardData?.face_up || !cardData?.rank) return;
        this.tooltipTimeout = setTimeout(() => {
            this.showCardTooltip(cardElement, cardData);
        }, 500);
    }

    showCardTooltip(cardElement, cardData) {
        if (!cardData?.face_up || !cardData?.rank) return;
        if (this.swapAnimationInProgress) return;
        // Only show tooltips on your turn
        if (!this.isMyTurn() && !this.gameState?.waiting_for_initial_flip) return;

        const value = this.getCardPointValue(cardData);
        const special = this.getCardSpecialNote(cardData);

        let content = `<span class="tooltip-value ${value < 0 ? 'negative' : ''}">${value} pts</span>`;
        if (special) {
            content += `<span class="tooltip-note">${special}</span>`;
        }
        this.tooltip.innerHTML = content;
        this.tooltip.classList.remove('hidden');

        // Position below card
        const rect = cardElement.getBoundingClientRect();
        let left = rect.left + rect.width / 2;
        let top = rect.bottom + 8;

        // Keep on screen
        if (top + 50 > window.innerHeight) {
            top = rect.top - 50;
        }
        left = Math.max(40, Math.min(window.innerWidth - 40, left));

        this.tooltip.style.left = `${left}px`;
        this.tooltip.style.top = `${top}px`;
    }

    hideCardTooltip() {
        clearTimeout(this.tooltipTimeout);
        if (this.tooltip) this.tooltip.classList.add('hidden');
    }

    getCardPointValue(cardData) {
        const values = this.gameState?.card_values || this.getDefaultCardValues();
        return values[cardData.rank] ?? 0;
    }

    getCardSpecialNote(cardData) {
        const rank = cardData.rank;
        const value = this.getCardPointValue(cardData);
        if (value < 0) return 'Negative - keep it!';
        if (rank === 'K' && value === 0) return 'Safe card';
        if (rank === 'K' && value === -2) return 'Super King!';
        if (rank === '10' && value === 1) return 'Ten Penny rule';
        if ((rank === 'J' || rank === 'Q') && value >= 10) return 'High - replace if possible';
        return null;
    }

    initElements() {
        // Screens
        this.lobbyScreen = document.getElementById('lobby-screen');
        this.waitingScreen = document.getElementById('waiting-screen');
        this.gameScreen = document.getElementById('game-screen');

        // Lobby elements
        this.playerNameInput = document.getElementById('player-name');
        this.roomCodeInput = document.getElementById('room-code');
        this.createRoomBtn = document.getElementById('create-room-btn');
        this.joinRoomBtn = document.getElementById('join-room-btn');
        this.lobbyError = document.getElementById('lobby-error');

        // Waiting room elements
        this.displayRoomCode = document.getElementById('display-room-code');
        this.copyRoomCodeBtn = document.getElementById('copy-room-code');
        this.shareRoomLinkBtn = document.getElementById('share-room-link');
        this.playersList = document.getElementById('players-list');
        this.hostSettings = document.getElementById('host-settings');
        this.waitingMessage = document.getElementById('waiting-message');
        this.numDecksInput = document.getElementById('num-decks');
        this.numDecksDisplay = document.getElementById('num-decks-display');
        this.decksMinus = document.getElementById('decks-minus');
        this.decksPlus = document.getElementById('decks-plus');
        this.deckRecommendation = document.getElementById('deck-recommendation');
        this.deckColorsGroup = document.getElementById('deck-colors-group');
        this.deckColorPresetSelect = document.getElementById('deck-color-preset');
        this.deckColorPreview = document.getElementById('deck-color-preview');
        this.numRoundsSelect = document.getElementById('num-rounds');
        this.initialFlipsSelect = document.getElementById('initial-flips');
        this.flipModeSelect = document.getElementById('flip-mode');
        this.knockPenaltyCheckbox = document.getElementById('knock-penalty');

        // Rules screen elements
        this.rulesScreen = document.getElementById('rules-screen');
        this.rulesBtn = document.getElementById('rules-btn');
        this.rulesBackBtn = document.getElementById('rules-back-btn');
        // House Rules - Point Modifiers
        this.superKingsCheckbox = document.getElementById('super-kings');
        this.tenPennyCheckbox = document.getElementById('ten-penny');
        // House Rules - Bonuses/Penalties
        this.knockBonusCheckbox = document.getElementById('knock-bonus');
        this.underdogBonusCheckbox = document.getElementById('underdog-bonus');
        this.tiedShameCheckbox = document.getElementById('tied-shame');
        this.blackjackCheckbox = document.getElementById('blackjack');
        this.wolfpackCheckbox = document.getElementById('wolfpack');
        // House Rules - New Variants
        this.flipAsActionCheckbox = document.getElementById('flip-as-action');
        this.fourOfAKindCheckbox = document.getElementById('four-of-a-kind');
        this.negativePairsCheckbox = document.getElementById('negative-pairs-keep-value');
        this.oneEyedJacksCheckbox = document.getElementById('one-eyed-jacks');
        this.knockEarlyCheckbox = document.getElementById('knock-early');
        this.wolfpackComboNote = document.getElementById('wolfpack-combo-note');
        this.startGameBtn = document.getElementById('start-game-btn');
        this.leaveRoomBtn = document.getElementById('leave-room-btn');
        this.addCpuBtn = document.getElementById('add-cpu-btn');
        this.removeCpuBtn = document.getElementById('remove-cpu-btn');
        this.cpuControlsSection = document.getElementById('cpu-controls-section');
        this.cpuSelectModal = document.getElementById('cpu-select-modal');
        this.cpuProfilesGrid = document.getElementById('cpu-profiles-grid');
        this.cancelCpuBtn = document.getElementById('cancel-cpu-btn');
        this.addSelectedCpusBtn = document.getElementById('add-selected-cpus-btn');

        // Game elements
        this.currentRoundSpan = document.getElementById('current-round');
        this.totalRoundsSpan = document.getElementById('total-rounds');
        this.statusMessage = document.getElementById('status-message');
        this.playerHeader = document.getElementById('player-header');
        this.yourScore = document.getElementById('your-score');
        this.muteBtn = document.getElementById('mute-btn');
        this.opponentsRow = document.getElementById('opponents-row');
        this.deckArea = document.querySelector('.deck-area');
        this.deck = document.getElementById('deck');
        this.discard = document.getElementById('discard');
        this.discardContent = document.getElementById('discard-content');
        this.discardBtn = document.getElementById('discard-btn');
        this.skipFlipBtn = document.getElementById('skip-flip-btn');
        this.knockEarlyBtn = document.getElementById('knock-early-btn');
        this.playerCards = document.getElementById('player-cards');
        this.playerArea = this.playerCards.closest('.player-area');
        this.swapAnimation = document.getElementById('swap-animation');
        this.swapCardFromHand = document.getElementById('swap-card-from-hand');
        this.heldCardSlot = document.getElementById('held-card-slot');
        this.heldCardDisplay = document.getElementById('held-card-display');
        this.heldCardContent = document.getElementById('held-card-content');
        this.heldCardFloating = document.getElementById('held-card-floating');
        this.heldCardFloatingContent = document.getElementById('held-card-floating-content');
        this.scoreboard = document.getElementById('scoreboard');
        this.scoreTable = document.getElementById('score-table').querySelector('tbody');
        this.standingsList = document.getElementById('standings-list');
        this.gameButtons = document.getElementById('game-buttons');
        this.nextRoundBtn = document.getElementById('next-round-btn');
        this.newGameBtn = document.getElementById('new-game-btn');
        this.leaveGameBtn = document.getElementById('leave-game-btn');
        this.activeRulesBar = document.getElementById('active-rules-bar');
        this.activeRulesList = document.getElementById('active-rules-list');
        this.finalTurnBadge = document.getElementById('final-turn-badge');

        // In-game auth elements
        this.gameUsername = document.getElementById('game-username');
        this.gameLogoutBtn = document.getElementById('game-logout-btn');
        this.authBar = document.getElementById('auth-bar');
    }

    bindEvents() {
        this.createRoomBtn.addEventListener('click', () => { this.playSound('click'); this.createRoom(); });
        this.joinRoomBtn.addEventListener('click', () => { this.playSound('click'); this.joinRoom(); });
        this.startGameBtn.addEventListener('click', () => { this.playSound('success'); this.startGame(); });
        this.leaveRoomBtn.addEventListener('click', () => { this.playSound('click'); this.leaveRoom(); });
        this.deck.addEventListener('click', () => { this.drawFromDeck(); });
        this.discard.addEventListener('click', () => { this.drawFromDiscard(); });
        this.discardBtn.addEventListener('click', () => { this.playSound('card'); this.discardDrawn(); });
        this.skipFlipBtn.addEventListener('click', () => { this.playSound('click'); this.skipFlip(); });
        this.knockEarlyBtn.addEventListener('click', () => { this.playSound('success'); this.knockEarly(); });
        this.nextRoundBtn.addEventListener('click', () => { this.playSound('click'); this.nextRound(); });
        this.newGameBtn.addEventListener('click', () => { this.playSound('click'); this.newGame(); });
        this.addCpuBtn.addEventListener('click', () => { this.playSound('click'); this.showCpuSelect(); });
        this.removeCpuBtn.addEventListener('click', () => { this.playSound('click'); this.removeCpu(); });
        this.cancelCpuBtn.addEventListener('click', () => { this.playSound('click'); this.hideCpuSelect(); });
        this.addSelectedCpusBtn.addEventListener('click', () => { this.playSound('success'); this.addSelectedCpus(); });
        this.muteBtn.addEventListener('click', () => this.toggleSound());
        this.leaveGameBtn.addEventListener('click', () => { this.playSound('click'); this.leaveGame(); });
        this.gameLogoutBtn.addEventListener('click', () => { this.playSound('click'); this.auth?.logout(); });

        // Copy room code to clipboard
        this.copyRoomCodeBtn.addEventListener('click', () => {
            this.playSound('click');
            this.copyRoomCode();
        });

        // Share room link
        this.shareRoomLinkBtn.addEventListener('click', () => {
            this.playSound('click');
            this.shareRoomLink();
        });

        // Enter key handlers
        this.playerNameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.createRoomBtn.click();
        });
        this.roomCodeInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.joinRoomBtn.click();
        });

        // Auto-uppercase room code
        this.roomCodeInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.toUpperCase();
        });

        // Deck stepper controls
        if (this.decksMinus) {
            this.decksMinus.addEventListener('click', () => {
                this.playSound('click');
                this.adjustDeckCount(-1);
            });
        }
        if (this.decksPlus) {
            this.decksPlus.addEventListener('click', () => {
                this.playSound('click');
                this.adjustDeckCount(1);
            });
        }

        // Update preview when color preset changes
        if (this.deckColorPresetSelect) {
            this.deckColorPresetSelect.addEventListener('change', () => {
                this.updateDeckColorPreview();
            });
        }

        // Show combo note when wolfpack + four-of-a-kind are both selected
        const updateWolfpackCombo = () => {
            if (this.wolfpackCheckbox.checked && this.fourOfAKindCheckbox.checked) {
                this.wolfpackComboNote.classList.remove('hidden');
            } else {
                this.wolfpackComboNote.classList.add('hidden');
            }
        };
        this.wolfpackCheckbox.addEventListener('change', updateWolfpackCombo);
        this.fourOfAKindCheckbox.addEventListener('change', updateWolfpackCombo);

        // Toggle scoreboard collapse on mobile
        const scoreboardTitle = this.scoreboard.querySelector('h4');
        if (scoreboardTitle) {
            scoreboardTitle.addEventListener('click', () => {
                if (window.innerWidth <= 700) {
                    this.scoreboard.classList.toggle('collapsed');
                }
            });
        }

        // Rules screen navigation
        if (this.rulesBtn) {
            this.rulesBtn.addEventListener('click', () => {
                this.playSound('click');
                this.showRulesScreen();
            });
        }
        if (this.rulesBackBtn) {
            this.rulesBackBtn.addEventListener('click', () => {
                this.playSound('click');
                this.showLobby();
            });
        }
    }

    showRulesScreen(scrollToSection = null) {
        this.showScreen(this.rulesScreen);
        if (scrollToSection) {
            const section = document.getElementById(scrollToSection);
            if (section) {
                section.scrollIntoView({ behavior: 'smooth' });
            }
        }
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host || 'localhost:8000';
        const wsUrl = `${protocol}//${host}/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('Connected to server');
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };

        this.ws.onclose = () => {
            console.log('Disconnected from server');
            this.showError('Connection lost. Please refresh the page.');
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.showError('Connection error. Please try again.');
        };
    }

    send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            console.error('WebSocket not ready, cannot send:', message.type);
            this.showError('Connection lost. Please refresh.');
        }
    }

    handleMessage(data) {
        console.log('Received:', data);

        switch (data.type) {
            case 'room_created':
                this.playerId = data.player_id;
                this.roomCode = data.room_code;
                this.isHost = true;
                this.showWaitingRoom();
                break;

            case 'room_joined':
                this.playerId = data.player_id;
                this.roomCode = data.room_code;
                this.isHost = false;
                this.showWaitingRoom();
                break;

            case 'player_joined':
                this.updatePlayersList(data.players);
                this.currentPlayers = data.players;
                break;

            case 'cpu_profiles':
                this.allProfiles = data.profiles;
                this.renderCpuSelect();
                break;

            case 'player_left':
                this.updatePlayersList(data.players);
                this.currentPlayers = data.players;
                break;

            case 'game_started':
            case 'round_started':
                // Clear any countdown from previous hole
                this.clearNextHoleCountdown();
                this.nextRoundBtn.classList.remove('waiting');
                // Clear round winner highlights
                this.roundWinnerNames = new Set();
                this.gameState = data.game_state;
                // Deep copy for previousState to avoid reference issues
                this.previousState = JSON.parse(JSON.stringify(data.game_state));
                // Reset all tracking for new round
                this.locallyFlippedCards = new Set();
                this.selectedCards = [];
                this.animatingPositions = new Set();
                this.opponentSwapAnimation = null;
                this.drawPulseAnimation = false;
                // V3_15: Clear discard history for new round
                this.clearDiscardHistory();
                // Cancel any running animations from previous round
                if (window.cardAnimations) {
                    window.cardAnimations.cancelAll();
                }
                this.showGameScreen();
                // V3_02: Animate dealing instead of instant render
                this.runDealAnimation();
                break;

            case 'game_state':
                // State updates are instant, animations are fire-and-forget
                // Exception: Local player's swap animation defers state until complete

                // If local swap animation is running, defer this state update
                if (this.swapAnimationInProgress) {
                    debugLog('STATE', 'Deferring state - swap animation in progress');
                    this.updateSwapAnimation(data.game_state.discard_top);
                    this.pendingGameState = data.game_state;
                    break;
                }

                const oldState = this.gameState;
                const newState = data.game_state;

                debugLog('STATE', 'Received game_state', {
                    phase: newState.phase,
                    currentPlayer: newState.current_player_id?.slice(-4),
                    discardTop: newState.discard_top ? `${newState.discard_top.rank}${newState.discard_top.suit?.[0]}` : 'EMPTY',
                    drawnCard: newState.drawn_card ? `${newState.drawn_card.rank}${newState.drawn_card.suit?.[0]}` : null,
                    drawnBy: newState.drawn_player_id?.slice(-4) || null,
                    hasDrawn: newState.has_drawn_card
                });

                // V3_03: Intercept round_over transition to defer card reveals
                const roundJustEnded = oldState?.phase !== 'round_over' &&
                                       newState.phase === 'round_over';

                if (roundJustEnded && oldState) {
                    // Save pre-reveal state for the reveal animation
                    this.preRevealState = JSON.parse(JSON.stringify(oldState));
                    this.postRevealState = newState;
                    // Update state but DON'T render yet - reveal animation will handle it
                    this.gameState = newState;
                    break;
                }

                // Update state FIRST (always)
                this.gameState = newState;

                // Clear local flip tracking if server confirmed our flips
                if (!newState.waiting_for_initial_flip && oldState?.waiting_for_initial_flip) {
                    this.locallyFlippedCards = new Set();
                    // Stop all initial flip pulse animations
                    if (window.cardAnimations) {
                        window.cardAnimations.stopAllInitialFlipPulses();
                    }
                }

                // Detect and fire animations (non-blocking, errors shouldn't break game)
                try {
                    this.triggerAnimationsForStateChange(oldState, newState);
                } catch (e) {
                    console.error('Animation error:', e);
                }

                // Render immediately with new state
                console.log('[DEBUG] About to renderGame, flags:', {
                    isDrawAnimating: this.isDrawAnimating,
                    localDiscardAnimating: this.localDiscardAnimating,
                    opponentDiscardAnimating: this.opponentDiscardAnimating,
                    opponentSwapAnimation: !!this.opponentSwapAnimation,
                    discardTop: newState.discard_top ? `${newState.discard_top.rank}-${newState.discard_top.suit}` : 'none'
                });
                this.renderGame();
                break;

            case 'your_turn':
                // Clear any stale opponent animation flags since it's now our turn
                this.opponentSwapAnimation = null;
                this.opponentDiscardAnimating = false;
                console.log('[DEBUG] your_turn received - clearing opponent animation flags');
                // Immediately update display to show correct discard pile
                this.renderGame();
                // Brief delay to let animations settle before showing toast
                setTimeout(() => {
                    // Build toast based on available actions
                    const canFlip = this.gameState && this.gameState.flip_as_action;
                    let canKnock = false;
                    if (this.gameState && this.gameState.knock_early) {
                        const myData = this.gameState.players.find(p => p.id === this.playerId);
                        const faceDownCount = myData ? myData.cards.filter(c => !c.face_up).length : 0;
                        canKnock = faceDownCount >= 1 && faceDownCount <= 2;
                    }
                    if (canFlip && canKnock) {
                        this.showToast('Your turn! Draw, flip, or knock', 'your-turn');
                    } else if (canFlip) {
                        this.showToast('Your turn! Draw or flip a card', 'your-turn');
                    } else if (canKnock) {
                        this.showToast('Your turn! Draw or knock', 'your-turn');
                    } else {
                        this.showToast('Your turn! Draw a card', 'your-turn');
                    }
                }, 200);
                break;

            case 'card_drawn':
                this.drawnCard = data.card;
                this.drawnFromDiscard = data.source === 'discard';

                if (data.source === 'deck' && window.drawAnimations) {
                    // Deck draw: use shared animation system (flip at deck, move to hold)
                    // Hide held card during animation - animation callback will show it
                    // Clear any stale opponent animation flags since it's now our turn
                    this.opponentSwapAnimation = null;
                    this.opponentDiscardAnimating = false;
                    this.isDrawAnimating = true;
                    this.hideDrawnCard();
                    window.drawAnimations.animateDrawDeck(data.card, () => {
                        this.isDrawAnimating = false;
                        this.displayHeldCard(data.card, true);
                        this.renderGame();
                    });
                } else if (data.source === 'discard' && window.drawAnimations) {
                    // Discard draw: use shared animation system (lift and move)
                    this.isDrawAnimating = true;
                    this.hideDrawnCard();
                    // Clear any in-progress swap animation to prevent race conditions
                    this.opponentSwapAnimation = null;
                    this.opponentDiscardAnimating = false;
                    window.drawAnimations.animateDrawDiscard(data.card, () => {
                        this.isDrawAnimating = false;
                        this.displayHeldCard(data.card, true);
                        this.renderGame();
                    });
                } else {
                    // Fallback: just show the card
                    this.displayHeldCard(data.card, true);
                    this.renderGame();
                }
                this.showToast('Swap with a card or discard', '', 3000);
                break;

            case 'can_flip':
                this.waitingForFlip = true;
                this.flipIsOptional = data.optional || false;
                if (this.flipIsOptional) {
                    this.showToast('Flip a card or skip', '', 3000);
                } else {
                    this.showToast('Flip a face-down card', '', 3000);
                }
                this.renderGame();
                break;

            case 'round_over':
                // V3_03: Run dramatic reveal before showing scoreboard
                this.runRoundEndReveal(data.scores, data.rankings);
                break;

            case 'game_over':
                this.showScoreboard(data.final_scores, true, data.rankings);
                break;

            case 'game_ended':
                // Host ended the game or player was kicked
                this.ws.close();
                this.showLobby();
                if (data.reason) {
                    this.showError(data.reason);
                }
                break;

            case 'error':
                this.showError(data.message);
                break;
        }
    }

    // Room Actions
    createRoom() {
        const name = this.playerNameInput.value.trim() || 'Player';
        this.connect();
        this.ws.onopen = () => {
            this.send({ type: 'create_room', player_name: name });
        };
    }

    joinRoom() {
        const name = this.playerNameInput.value.trim() || 'Player';
        const code = this.roomCodeInput.value.trim().toUpperCase();

        if (code.length !== 4) {
            this.showError('Please enter a 4-letter room code');
            return;
        }

        this.connect();
        this.ws.onopen = () => {
            this.send({ type: 'join_room', room_code: code, player_name: name });
        };
    }

    leaveRoom() {
        this.send({ type: 'leave_room' });
        this.ws.close();
        this.showLobby();
    }

    copyRoomCode() {
        if (!this.roomCode) return;
        this.copyToClipboard(this.roomCode, this.copyRoomCodeBtn);
    }

    shareRoomLink() {
        if (!this.roomCode) return;

        // Build shareable URL with room code
        const url = new URL(window.location.href);
        url.search = ''; // Clear existing params
        url.hash = '';   // Clear hash
        url.searchParams.set('room', this.roomCode);
        const shareUrl = url.toString();

        this.copyToClipboard(shareUrl, this.shareRoomLinkBtn);
    }

    copyToClipboard(text, feedbackBtn) {
        // Use execCommand which is more reliable across contexts
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();

        let success = false;
        try {
            success = document.execCommand('copy');
        } catch (err) {
            console.error('Copy failed:', err);
        }
        document.body.removeChild(textarea);

        // Show visual feedback
        if (success && feedbackBtn) {
            const originalText = feedbackBtn.textContent;
            feedbackBtn.textContent = '✓';
            setTimeout(() => {
                feedbackBtn.textContent = originalText;
            }, 1500);
        }
    }

    startGame() {
        try {
            const decks = parseInt(this.numDecksInput?.value || '1');
            const rounds = parseInt(this.numRoundsSelect?.value || '9');
            const initial_flips = parseInt(this.initialFlipsSelect?.value || '2');

            // Standard options
            const flip_mode = this.flipModeSelect?.value || 'always';  // "never", "always", or "endgame"
            const knock_penalty = this.knockPenaltyCheckbox?.checked || false;

            // Joker mode (radio buttons)
            const jokerRadio = document.querySelector('input[name="joker-mode"]:checked');
            const joker_mode = jokerRadio ? jokerRadio.value : 'none';
            const use_jokers = joker_mode !== 'none';
            const lucky_swing = joker_mode === 'lucky-swing';
            const eagle_eye = joker_mode === 'eagle-eye';

            // House Rules - Point Modifiers
            const super_kings = this.superKingsCheckbox?.checked || false;
            const ten_penny = this.tenPennyCheckbox?.checked || false;

            // House Rules - Bonuses/Penalties
            const knock_bonus = this.knockBonusCheckbox?.checked || false;
            const underdog_bonus = this.underdogBonusCheckbox?.checked || false;
            const tied_shame = this.tiedShameCheckbox?.checked || false;
            const blackjack = this.blackjackCheckbox?.checked || false;
            const wolfpack = this.wolfpackCheckbox?.checked || false;

            // House Rules - New Variants
            const flip_as_action = this.flipAsActionCheckbox?.checked || false;
            const four_of_a_kind = this.fourOfAKindCheckbox?.checked || false;
            const negative_pairs_keep_value = this.negativePairsCheckbox?.checked || false;
            const one_eyed_jacks = this.oneEyedJacksCheckbox?.checked || false;
            const knock_early = this.knockEarlyCheckbox?.checked || false;

            // Deck colors
            const deck_colors = this.getDeckColors(decks);

            this.send({
                type: 'start_game',
                decks,
                rounds,
                initial_flips,
                flip_mode,
                knock_penalty,
                use_jokers,
                lucky_swing,
                super_kings,
                ten_penny,
                knock_bonus,
                underdog_bonus,
                tied_shame,
                blackjack,
                eagle_eye,
                wolfpack,
                flip_as_action,
                four_of_a_kind,
                negative_pairs_keep_value,
                one_eyed_jacks,
                knock_early,
                deck_colors
            });
        } catch (error) {
            console.error('Error starting game:', error);
            this.showError('Error starting game. Please refresh.');
        }
    }

    showCpuSelect() {
        // Request available profiles from server
        this.selectedCpus = new Set();
        this.send({ type: 'get_cpu_profiles' });
        this.cpuSelectModal.classList.remove('hidden');
    }

    hideCpuSelect() {
        this.cpuSelectModal.classList.add('hidden');
        this.selectedCpus = new Set();
    }

    renderCpuSelect() {
        if (!this.allProfiles) return;

        // Get names of CPUs already in the game
        const usedNames = new Set(
            (this.currentPlayers || [])
                .filter(p => p.is_cpu)
                .map(p => p.name)
        );

        this.cpuProfilesGrid.innerHTML = '';

        this.allProfiles.forEach(profile => {
            const div = document.createElement('div');
            const isUsed = usedNames.has(profile.name);
            const isSelected = this.selectedCpus && this.selectedCpus.has(profile.name);
            div.className = 'profile-card' + (isUsed ? ' unavailable' : '') + (isSelected ? ' selected' : '');

            const avatar = this.getCpuAvatar(profile.name);
            const checkbox = isUsed ? '' : `<div class="profile-checkbox">${isSelected ? '✓' : ''}</div>`;

            div.innerHTML = `
                ${checkbox}
                <div class="profile-avatar">${avatar}</div>
                <div class="profile-name">${profile.name}</div>
                <div class="profile-style">${profile.style}</div>
                ${isUsed ? '<div class="profile-in-game">In Game</div>' : ''}
            `;

            if (!isUsed) {
                div.addEventListener('click', () => this.toggleCpuSelection(profile.name));
            }

            this.cpuProfilesGrid.appendChild(div);
        });

        this.updateAddCpuButton();
    }

    getCpuAvatar(name) {
        const avatars = {
            'Sofia': `<svg viewBox="0 0 40 40"><path d="M8 19 Q8 5 20 5 Q32 5 32 19 L32 29 Q28 31 26 27 L26 19 M8 19 L8 29 Q12 31 14 27 L14 19" fill="#c44d00"/><circle cx="20" cy="19" r="9" fill="#e8b4b8"/><circle cx="17" cy="18" r="1.5" fill="#333"/><circle cx="23" cy="18" r="1.5" fill="#333"/><path d="M17 22 Q20 24 23 22" stroke="#333" fill="none" stroke-width="1.2"/><path d="M11 10 Q15 7 20 9 Q25 7 29 10 Q25 13 20 12 Q15 13 11 10" fill="#c44d00"/></svg>`,
            'Maya': `<svg viewBox="0 0 40 40"><circle cx="20" cy="19" r="9" fill="#d4a574"/><circle cx="17" cy="17" r="1.5" fill="#333"/><circle cx="23" cy="17" r="1.5" fill="#333"/><path d="M16 22 L24 22" stroke="#333" stroke-width="1.5"/><path d="M11 15 Q11 8 20 8 Q29 8 29 15" fill="#5c4033"/><ellipse cx="32" cy="17" rx="4" ry="6" fill="#5c4033"/><circle cx="30" cy="15" r="2" fill="#e91e63"/></svg>`,
            'Priya': `<svg viewBox="0 0 40 40"><circle cx="20" cy="21" r="9" fill="#c4956a"/><path d="M12 15 Q12 8 20 8 Q28 8 28 15" fill="#111"/><path d="M12 14 Q10 16 11 20" stroke="#111" stroke-width="2" fill="none"/><path d="M28 14 Q30 16 29 20" stroke="#111" stroke-width="2" fill="none"/><circle cx="17" cy="20" r="1.5" fill="#333"/><circle cx="23" cy="20" r="1.5" fill="#333"/><path d="M17 25 Q20 27 23 25" stroke="#333" fill="none" stroke-width="1.2"/><circle cx="20" cy="17" r="1" fill="#e74c3c"/></svg>`,
            'Marcus': `<svg viewBox="0 0 40 40"><circle cx="20" cy="21" r="10" fill="#a67c52"/><circle cx="17" cy="19" r="2" fill="#333"/><circle cx="23" cy="19" r="2" fill="#333"/><path d="M16 25 Q20 27 24 25" stroke="#333" fill="none" stroke-width="1.5"/><rect x="10" y="8" width="20" height="6" rx="2" fill="#333"/></svg>`,
            'Kenji': `<svg viewBox="0 0 40 40"><circle cx="20" cy="20" r="10" fill="#f0d5a8"/><circle cx="17" cy="18" r="2" fill="#333"/><circle cx="23" cy="18" r="2" fill="#333"/><path d="M17 23 L23 23" stroke="#333" stroke-width="1.5"/><path d="M10 16 Q10 8 20 8 Q30 8 30 16 L28 14 L26 16 L24 13 L22 16 L20 12 L18 16 L16 13 L14 16 L12 14 Z" fill="#1a1a1a"/></svg>`,
            'Diego': `<svg viewBox="0 0 40 40"><circle cx="20" cy="20" r="10" fill="#c9a86c"/><circle cx="17" cy="18" r="2" fill="#333"/><circle cx="23" cy="18" r="2" fill="#333"/><path d="M15 23 Q20 28 25 23" stroke="#333" fill="none" stroke-width="1.5"/><path d="M10 14 Q15 9 20 12 Q25 9 30 14" stroke="#2c1810" fill="none" stroke-width="3"/><rect x="17" y="26" width="6" height="4" rx="1" fill="#4a3728"/></svg>`,
            'River': `<svg viewBox="0 0 40 40"><circle cx="20" cy="21" r="9" fill="#e0c8a8"/><path d="M10 19 Q10 11 20 11 Q30 11 30 19" fill="#7c5e3c"/><circle cx="17" cy="20" r="1.5" fill="#333"/><circle cx="23" cy="20" r="1.5" fill="#333"/><path d="M17 24 Q20 26 23 24" stroke="#333" fill="none" stroke-width="1.2"/><path d="M6 17 Q6 9 20 9 Q34 9 34 17" stroke="#333" stroke-width="2" fill="none"/><ellipse cx="6" cy="21" rx="4" ry="5" fill="#222"/><ellipse cx="34" cy="21" rx="4" ry="5" fill="#222"/><ellipse cx="6" cy="21" rx="2.5" ry="3.5" fill="#444"/><ellipse cx="34" cy="21" rx="2.5" ry="3.5" fill="#444"/></svg>`,
            'Sage': `<svg viewBox="0 0 40 40"><circle cx="20" cy="26" r="10" fill="#d4b896"/><circle cx="17" cy="24" r="2" fill="#333"/><circle cx="23" cy="24" r="2" fill="#333"/><path d="M17 30 L23 28" stroke="#333" stroke-width="1.5"/><path d="M8 18 L20 1 L32 18 Z" fill="#3a3a80"/><ellipse cx="20" cy="18" rx="14" ry="4" fill="#3a3a80"/><circle cx="16" cy="12" r="1" fill="#ffd700"/><circle cx="24" cy="8" r="1.2" fill="#ffd700"/></svg>`
        };
        return avatars[name] || `<svg viewBox="0 0 40 40"><circle cx="20" cy="16" r="10" fill="#ccc"/><circle cx="17" cy="14" r="2" fill="#333"/><circle cx="23" cy="14" r="2" fill="#333"/></svg>`;
    }

    toggleCpuSelection(profileName) {
        if (!this.selectedCpus) this.selectedCpus = new Set();

        if (this.selectedCpus.has(profileName)) {
            this.selectedCpus.delete(profileName);
        } else {
            this.selectedCpus.add(profileName);
        }
        this.renderCpuSelect();
    }

    updateAddCpuButton() {
        const count = this.selectedCpus ? this.selectedCpus.size : 0;
        this.addSelectedCpusBtn.textContent = count > 0 ? `Add ${count} CPU${count > 1 ? 's' : ''}` : 'Add';
        this.addSelectedCpusBtn.disabled = count === 0;
    }

    addSelectedCpus() {
        if (!this.selectedCpus || this.selectedCpus.size === 0) return;

        this.selectedCpus.forEach(profileName => {
            this.send({ type: 'add_cpu', profile_name: profileName });
        });
        this.hideCpuSelect();
    }

    removeCpu() {
        this.send({ type: 'remove_cpu' });
    }

    // Game Actions
    drawFromDeck() {
        if (!this.isMyTurn() || this.drawnCard || this.gameState.has_drawn_card) {
            if (this.gameState && !this.gameState.waiting_for_initial_flip) {
                this.playSound('reject');
            }
            return;
        }
        if (this.gameState.waiting_for_initial_flip) return;
        // Sound played by draw animation
        this.send({ type: 'draw', source: 'deck' });
    }

    drawFromDiscard() {
        // If holding a card drawn from discard, clicking discard puts it back
        if (this.drawnCard && !this.gameState.can_discard) {
            this.playSound('click');
            this.cancelDraw();
            return;
        }

        if (!this.isMyTurn() || this.drawnCard || this.gameState.has_drawn_card) {
            if (this.gameState && !this.gameState.waiting_for_initial_flip) {
                this.playSound('reject');
            }
            return;
        }
        if (this.gameState.waiting_for_initial_flip) return;
        if (!this.gameState.discard_top) return;
        // Sound played by draw animation
        this.send({ type: 'draw', source: 'discard' });
    }

    discardDrawn() {
        if (!this.drawnCard) return;
        const discardedCard = this.drawnCard;
        this.send({ type: 'discard' });
        this.drawnCard = null;
        this.hideToast();
        this.discardBtn.classList.add('hidden');

        // Capture the actual position of the held card before hiding it
        const heldRect = this.heldCardFloating.getBoundingClientRect();

        // Hide the floating held card immediately (animation will create its own)
        this.heldCardFloating.classList.add('hidden');
        this.heldCardFloating.style.cssText = '';

        // Pre-emptively skip the flip animation - the server may broadcast the new state
        // before our animation completes, and we don't want renderGame() to trigger
        // the flip-in animation (which starts with opacity: 0, causing a flash)
        this.skipNextDiscardFlip = true;
        // Also update lastDiscardKey so renderGame() won't see a "change"
        this.lastDiscardKey = `${discardedCard.rank}-${discardedCard.suit}`;

        // Block renderGame from updating discard during animation (prevents race condition)
        this.localDiscardAnimating = true;

        // Animate held card to discard using anime.js
        if (window.cardAnimations) {
            window.cardAnimations.animateHeldToDiscard(discardedCard, heldRect, () => {
                this.updateDiscardPileDisplay(discardedCard);
                this.pulseDiscardLand();
                this.skipNextDiscardFlip = true;
                this.localDiscardAnimating = false;
            });
        } else {
            // Fallback: just update immediately
            this.updateDiscardPileDisplay(discardedCard);
            this.localDiscardAnimating = false;
        }
    }

    // Update the discard pile display with a card
    // Note: Don't use renderCardContent here - the card may have face_up=false
    // (drawn cards aren't marked face_up until server processes discard)
    updateDiscardPileDisplay(card) {
        this.discard.classList.remove('picked-up', 'disabled');
        this.discard.classList.add('has-card', 'card-front');
        this.discard.classList.remove('red', 'black', 'joker');

        if (card.rank === '★') {
            this.discard.classList.add('joker');
            const jokerIcon = card.suit === 'hearts' ? '🐉' : '👹';
            this.discardContent.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        } else {
            this.discard.classList.add(card.suit === 'hearts' || card.suit === 'diamonds' ? 'red' : 'black');
            // Render directly - discard pile cards are always visible
            this.discardContent.innerHTML = `${card.rank}<br>${this.getSuitSymbol(card.suit)}`;
        }
        this.lastDiscardKey = `${card.rank}-${card.suit}`;
    }

    cancelDraw() {
        if (!this.drawnCard) return;
        const cardToReturn = this.drawnCard;
        const wasFromDiscard = this.drawnFromDiscard;
        this.send({ type: 'cancel_draw' });
        this.drawnCard = null;
        this.hideToast();

        if (wasFromDiscard) {
            // Animate card from deck position back to discard pile
            this.animateDeckToDiscardReturn(cardToReturn);
        } else {
            this.hideDrawnCard();
        }
    }

    // Animate returning a card from deck position to discard pile (for cancel draw from discard)
    animateDeckToDiscardReturn(card) {
        const discardRect = this.discard.getBoundingClientRect();
        const floater = this.heldCardFloating;

        // Add swooping class for smooth transition
        floater.classList.add('swooping');
        floater.style.left = `${discardRect.left}px`;
        floater.style.top = `${discardRect.top}px`;
        floater.style.width = `${discardRect.width}px`;
        floater.style.height = `${discardRect.height}px`;

        this.playSound('card');

        // After swoop completes, hide floater and update discard pile
        setTimeout(() => {
            floater.classList.add('landed');

            setTimeout(() => {
                floater.classList.add('hidden');
                floater.classList.remove('swooping', 'landed');
                floater.style.cssText = '';
                this.updateDiscardPileDisplay(card);
                this.pulseDiscardLand();
            }, 150);
        }, 350);
    }

    swapCard(position) {
        if (!this.drawnCard) return;
        this.send({ type: 'swap', position });
        this.drawnCard = null;
        this.hideDrawnCard();
    }

    // Animate player swapping drawn card with a card in their hand
    // Uses flip-in-place + teleport (no zipping movement)
    animateSwap(position) {
        const cardElements = this.playerCards.querySelectorAll('.card');
        const handCardEl = cardElements[position];
        if (!handCardEl) {
            this.swapCard(position);
            return;
        }

        // Check if card is already face-up
        const myData = this.getMyPlayerData();
        const card = myData?.cards[position];
        const isAlreadyFaceUp = card?.face_up;
        const handRect = handCardEl.getBoundingClientRect();
        const heldRect = this.heldCardFloating?.getBoundingClientRect();

        // Mark animating
        this.swapAnimationInProgress = true;
        this.swapAnimationCardEl = handCardEl;
        this.swapAnimationHandCardEl = handCardEl;

        // Hide originals during animation
        handCardEl.classList.add('swap-out');
        if (this.heldCardFloating) {
            this.heldCardFloating.style.visibility = 'hidden';
        }

        // Store drawn card data before clearing
        const drawnCardData = this.drawnCard;
        this.drawnCard = null;
        this.skipNextDiscardFlip = true;

        // Send swap to server
        this.send({ type: 'swap', position });

        if (isAlreadyFaceUp && card) {
            // Face-up card - we know both cards, animate immediately
            this.swapAnimationContentSet = true;

            if (window.cardAnimations) {
                window.cardAnimations.animateUnifiedSwap(
                    card,               // handCardData - card going to discard
                    drawnCardData,      // heldCardData - drawn card going to hand
                    handRect,           // handRect
                    heldRect,           // heldRect
                    {
                        rotation: 0,
                        wasHandFaceDown: false,
                        onComplete: () => {
                            handCardEl.classList.remove('swap-out');
                            if (this.heldCardFloating) {
                                this.heldCardFloating.style.visibility = '';
                            }
                            this.completeSwapAnimation(null);
                        }
                    }
                );
            } else {
                setTimeout(() => {
                    handCardEl.classList.remove('swap-out');
                    if (this.heldCardFloating) {
                        this.heldCardFloating.style.visibility = '';
                    }
                    this.completeSwapAnimation(null);
                }, 500);
            }
        } else {
            // Face-down card - wait for server to tell us what the card was
            // Store context for updateSwapAnimation to use
            this.swapAnimationContentSet = false;
            this.pendingSwapData = {
                handCardEl,
                handRect,
                heldRect,
                drawnCardData,
                position
            };
        }
    }

    // Update the animated card with actual card content when server responds
    updateSwapAnimation(card) {
        // Skip if we already set the content (face-up card swap)
        if (this.swapAnimationContentSet) return;

        // Safety check
        if (!this.swapAnimationInProgress || !card) {
            return;
        }

        // Now we have the card data - run the unified animation
        this.swapAnimationContentSet = true;

        const data = this.pendingSwapData;
        if (!data) {
            console.error('Swap animation missing pending data');
            this.completeSwapAnimation(null);
            return;
        }

        const { handCardEl, handRect, heldRect, drawnCardData } = data;

        if (window.cardAnimations) {
            window.cardAnimations.animateUnifiedSwap(
                card,               // handCardData - now we know what it was
                drawnCardData,      // heldCardData - drawn card going to hand
                handRect,           // handRect
                heldRect,           // heldRect
                {
                    rotation: 0,
                    wasHandFaceDown: true,
                    onComplete: () => {
                        if (handCardEl) handCardEl.classList.remove('swap-out');
                        if (this.heldCardFloating) {
                            this.heldCardFloating.style.visibility = '';
                        }
                        this.pendingSwapData = null;
                        this.completeSwapAnimation(null);
                    }
                }
            );
        } else {
            // Fallback
            setTimeout(() => {
                if (handCardEl) handCardEl.classList.remove('swap-out');
                if (this.heldCardFloating) {
                    this.heldCardFloating.style.visibility = '';
                }
                this.pendingSwapData = null;
                this.completeSwapAnimation(null);
            }, 500);
        }
    }

    completeSwapAnimation(heldCard) {
        // Guard against double completion
        if (!this.swapAnimationInProgress) return;

        // Hide everything
        this.swapAnimation.classList.add('hidden');
        if (this.swapAnimationCard) {
            this.swapAnimationCard.classList.remove('hidden', 'flipping', 'moving', 'swap-pulse');
        }
        if (heldCard) {
            heldCard.classList.remove('flipping', 'moving');
            heldCard.classList.add('hidden');
        }
        if (this.swapAnimationHandCardEl) {
            this.swapAnimationHandCardEl.classList.remove('swap-out');
        }
        this.discard.classList.remove('swap-to-hand');
        this.swapAnimationInProgress = false;
        this.swapAnimationFront = null;
        this.swapAnimationCard = null;
        this.swapAnimationDiscardRect = null;
        this.swapAnimationHandCardEl = null;
        this.swapAnimationHandRect = null;
        this.swapAnimationContentSet = false;
        this.pendingSwapData = null;
        this.discardBtn.classList.add('hidden');
        this.heldCardFloating.classList.add('hidden');

        if (this.pendingGameState) {
            this.gameState = this.pendingGameState;
            this.pendingGameState = null;
            this.renderGame();
        }
    }

    flipCard(position) {
        this.send({ type: 'flip_card', position });
        this.waitingForFlip = false;
        this.flipIsOptional = false;
    }

    skipFlip() {
        if (!this.flipIsOptional) return;
        this.send({ type: 'skip_flip' });
        this.waitingForFlip = false;
        this.flipIsOptional = false;
        this.hideToast();
    }

    knockEarly() {
        // V3_09: Knock early with confirmation dialog
        if (!this.gameState || !this.gameState.knock_early) return;

        const myData = this.getMyPlayerData();
        if (!myData) return;
        const hiddenCards = myData.cards.filter(c => !c.face_up);
        if (hiddenCards.length === 0 || hiddenCards.length > 2) return;

        this.showKnockConfirmation(hiddenCards.length, () => {
            this.executeKnockEarly();
        });
    }

    showKnockConfirmation(hiddenCount, onConfirm) {
        const modal = document.createElement('div');
        modal.className = 'knock-confirm-modal';
        modal.innerHTML = `
            <div class="knock-confirm-content">
                <div class="knock-confirm-icon">⚡</div>
                <h3>Knock Early?</h3>
                <p>You'll reveal ${hiddenCount} hidden card${hiddenCount > 1 ? 's' : ''} and trigger final turn.</p>
                <p class="knock-warning">This cannot be undone!</p>
                <div class="knock-confirm-buttons">
                    <button class="btn btn-secondary knock-cancel">Cancel</button>
                    <button class="btn btn-primary knock-confirm">Knock!</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        modal.querySelector('.knock-cancel').addEventListener('click', () => {
            this.playSound('click');
            modal.remove();
        });
        modal.querySelector('.knock-confirm').addEventListener('click', () => {
            this.playSound('click');
            modal.remove();
            onConfirm();
        });
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    }

    async executeKnockEarly() {
        this.playSound('knock');

        const myData = this.getMyPlayerData();
        if (!myData) return;
        const hiddenPositions = myData.cards
            .map((card, i) => ({ card, position: i }))
            .filter(({ card }) => !card.face_up)
            .map(({ position }) => position);

        // Rapid sequential flips
        for (const position of hiddenPositions) {
            this.fireLocalFlipAnimation(position, myData.cards[position]);
            this.playSound('flip');
            await this.delay(150);
        }
        await this.delay(300);

        this.showKnockBanner();

        this.send({ type: 'knock_early' });
        this.hideToast();
    }

    showKnockBanner(playerName) {
        const banner = document.createElement('div');
        banner.className = 'knock-banner';
        banner.innerHTML = `<span>${playerName ? playerName + ' knocked!' : 'KNOCK!'}</span>`;
        document.body.appendChild(banner);

        document.body.classList.add('screen-shake');

        setTimeout(() => {
            banner.classList.add('fading');
            document.body.classList.remove('screen-shake');
        }, 800);
        setTimeout(() => {
            banner.remove();
        }, 1100);
    }

    // --- V3_02: Dealing Animation ---

    runDealAnimation() {
        // Respect reduced motion preference
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            this.playSound('shuffle');
            this.renderGame();
            return;
        }

        // Render first so card slot positions exist
        this.renderGame();

        // Hide cards during animation
        this.playerCards.style.visibility = 'hidden';
        this.opponentsRow.style.visibility = 'hidden';

        // Suppress flip prompts until dealing complete
        this.dealAnimationInProgress = true;

        if (window.cardAnimations) {
            window.cardAnimations.animateDealing(
                this.gameState,
                (playerId, cardIdx) => this.getCardSlotRect(playerId, cardIdx),
                () => {
                    // Deal complete - allow flip prompts
                    this.dealAnimationInProgress = false;
                    // Show real cards
                    this.playerCards.style.visibility = 'visible';
                    this.opponentsRow.style.visibility = 'visible';
                    this.renderGame();
                    // Stagger opponent initial flips right after dealing
                    this.animateOpponentInitialFlips();
                }
            );
        } else {
            // Fallback
            this.dealAnimationInProgress = false;
            this.playerCards.style.visibility = 'visible';
            this.opponentsRow.style.visibility = 'visible';
            this.playSound('shuffle');
        }
    }

    animateOpponentInitialFlips() {
        const T = window.TIMING?.initialFlips || {};
        const windowStart = T.windowStart || 500;
        const windowEnd = T.windowEnd || 2500;
        const cardStagger = T.cardStagger || 400;

        const opponents = this.gameState.players.filter(p => p.id !== this.playerId);

        // Collect face-up cards per opponent and convert them to show backs
        for (const player of opponents) {
            const area = this.opponentsRow.querySelector(
                `.opponent-area[data-player-id="${player.id}"]`
            );
            if (!area) continue;

            const cardEls = area.querySelectorAll('.card-grid .card');
            const faceUpCards = [];
            player.cards.forEach((card, idx) => {
                if (card.face_up && cardEls[idx]) {
                    const el = cardEls[idx];
                    faceUpCards.push({ el, card, idx });
                    // Convert to card-back appearance while waiting
                    el.className = 'card card-back';
                    if (this.gameState?.deck_colors) {
                        const deckId = card.deck_id || 0;
                        const color = this.gameState.deck_colors[deckId] || this.gameState.deck_colors[0];
                        if (color) el.classList.add(`back-${color}`);
                    }
                    el.innerHTML = '';
                }
            });

            if (faceUpCards.length > 0) {
                const rotation = this.getElementRotation(area);
                // Each opponent starts at a random time within the window (concurrent, not sequential)
                const startDelay = windowStart + Math.random() * (windowEnd - windowStart);

                setTimeout(() => {
                    faceUpCards.forEach(({ el, card }, i) => {
                        setTimeout(() => {
                            window.cardAnimations.animateOpponentFlip(el, card, rotation);
                        }, i * cardStagger);
                    });
                }, startDelay);
            }
        }
    }

    getCardSlotRect(playerId, cardIdx) {
        if (playerId === this.playerId) {
            const cards = this.playerCards.querySelectorAll('.card');
            return cards[cardIdx]?.getBoundingClientRect() || null;
        } else {
            const area = this.opponentsRow.querySelector(
                `.opponent-area[data-player-id="${playerId}"]`
            );
            if (area) {
                const cards = area.querySelectorAll('.card');
                return cards[cardIdx]?.getBoundingClientRect() || null;
            }
        }
        return null;
    }

    // --- V3_03: Round End Dramatic Reveal ---

    async runRoundEndReveal(scores, rankings) {
        const T = window.TIMING?.reveal || {};
        const oldState = this.preRevealState;
        const newState = this.postRevealState || this.gameState;

        if (!oldState || !newState) {
            // Fallback: show scoreboard immediately
            this.showScoreboard(scores, false, rankings);
            return;
        }

        // First, render the game with the OLD state (pre-reveal) so cards show face-down
        this.gameState = newState;
        // But render with pre-reveal card visuals
        this.revealAnimationInProgress = true;

        // Render game to show current layout (opponents, etc)
        this.renderGame();

        // Compute what needs revealing
        const revealsByPlayer = this.getCardsToReveal(oldState, newState);

        // Get reveal order: knocker first, then clockwise
        const knockerId = newState.finisher_id;
        const revealOrder = this.getRevealOrder(newState.players, knockerId);

        // Initial pause
        this.setStatus('Revealing cards...', 'reveal');
        await this.delay(T.initialPause || 500);

        // Reveal each player's cards
        for (const player of revealOrder) {
            const cardsToFlip = revealsByPlayer.get(player.id) || [];
            if (cardsToFlip.length === 0) continue;

            // Highlight player area
            this.highlightPlayerArea(player.id, true);
            await this.delay(T.highlightDuration || 200);

            // Flip each card with stagger
            for (const { position, card } of cardsToFlip) {
                this.animateRevealFlip(player.id, position, card);
                await this.delay(T.cardStagger || 100);
            }

            // Wait for last flip to complete + pause
            await this.delay(300 + (T.playerPause || 400));

            // Remove highlight
            this.highlightPlayerArea(player.id, false);
        }

        // All revealed - run score tally before showing scoreboard
        this.revealAnimationInProgress = false;
        this.preRevealState = null;
        this.postRevealState = null;
        this.renderGame();

        // V3_07: Animated score tallying
        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            await this.runScoreTally(newState.players, knockerId);
        }

        this.showScoreboard(scores, false, rankings);
    }

    getCardsToReveal(oldState, newState) {
        const reveals = new Map();

        for (const newPlayer of newState.players) {
            const oldPlayer = oldState.players.find(p => p.id === newPlayer.id);
            if (!oldPlayer) continue;

            const cardsToFlip = [];
            for (let i = 0; i < 6; i++) {
                const wasHidden = !oldPlayer.cards[i]?.face_up;
                const nowVisible = newPlayer.cards[i]?.face_up;

                if (wasHidden && nowVisible) {
                    cardsToFlip.push({
                        position: i,
                        card: newPlayer.cards[i]
                    });
                }
            }

            if (cardsToFlip.length > 0) {
                reveals.set(newPlayer.id, cardsToFlip);
            }
        }

        return reveals;
    }

    getRevealOrder(players, knockerId) {
        const knocker = players.find(p => p.id === knockerId);
        const others = players.filter(p => p.id !== knockerId);

        if (knocker) {
            return [knocker, ...others];
        }
        return others;
    }

    highlightPlayerArea(playerId, highlight) {
        if (playerId === this.playerId) {
            this.playerArea.classList.toggle('revealing', highlight);
        } else {
            const area = this.opponentsRow.querySelector(
                `.opponent-area[data-player-id="${playerId}"]`
            );
            if (area) {
                area.classList.toggle('revealing', highlight);
            }
        }
    }

    animateRevealFlip(playerId, position, cardData) {
        if (playerId === this.playerId) {
            // Local player card
            const cards = this.playerCards.querySelectorAll('.card');
            const cardEl = cards[position];
            if (cardEl && window.cardAnimations) {
                window.cardAnimations.animateInitialFlip(cardEl, cardData, () => {
                    // Re-render this card to show revealed state
                    this.renderGame();
                });
            }
        } else {
            // Opponent card
            const area = this.opponentsRow.querySelector(
                `.opponent-area[data-player-id="${playerId}"]`
            );
            if (area) {
                const cards = area.querySelectorAll('.card');
                const cardEl = cards[position];
                if (cardEl && window.cardAnimations) {
                    const rotation = this.getElementRotation(area);
                    window.cardAnimations.animateOpponentFlip(cardEl, cardData, rotation);
                }
            }
        }
        this.playSound('flip');
    }

    // --- V3_07: Animated Score Tallying ---

    async runScoreTally(players, knockerId) {
        const T = window.TIMING?.tally || {};
        await this.delay(T.initialPause || 300);

        const cardValues = this.gameState?.card_values || this.getDefaultCardValues();

        // Order: knocker first, then others
        const ordered = [...players].sort((a, b) => {
            if (a.id === knockerId) return -1;
            if (b.id === knockerId) return 1;
            return 0;
        });

        for (const player of ordered) {
            const cards = this.getCardElements(player.id, 0, 1, 2, 3, 4, 5);
            if (cards.length < 6) continue;

            // Highlight player area
            this.highlightPlayerArea(player.id, true);

            let total = 0;
            const columns = [[0, 3], [1, 4], [2, 5]];

            for (const [topIdx, bottomIdx] of columns) {
                const topData = player.cards[topIdx];
                const bottomData = player.cards[bottomIdx];
                const topCard = cards[topIdx];
                const bottomCard = cards[bottomIdx];
                const isPair = topData?.rank && bottomData?.rank && topData.rank === bottomData.rank;

                if (isPair) {
                    // Just show pair cancel — no individual card values
                    topCard?.classList.add('tallying');
                    bottomCard?.classList.add('tallying');
                    this.showPairCancel(topCard, bottomCard);
                    await this.delay(T.pairCelebration || 400);
                } else {
                    // Show individual card values
                    topCard?.classList.add('tallying');
                    const topValue = cardValues[topData?.rank] ?? 0;
                    const topOverlay = this.showCardValue(topCard, topValue, topValue < 0);
                    await this.delay(T.cardHighlight || 200);

                    bottomCard?.classList.add('tallying');
                    const bottomValue = cardValues[bottomData?.rank] ?? 0;
                    const bottomOverlay = this.showCardValue(bottomCard, bottomValue, bottomValue < 0);
                    await this.delay(T.cardHighlight || 200);

                    total += topValue + bottomValue;
                    this.hideCardValue(topOverlay);
                    this.hideCardValue(bottomOverlay);
                }

                topCard?.classList.remove('tallying');
                bottomCard?.classList.remove('tallying');
                await this.delay(T.columnPause || 150);
            }

            this.highlightPlayerArea(player.id, false);
            await this.delay(T.playerPause || 500);
        }
    }

    showCardValue(cardElement, value, isNegative) {
        if (!cardElement) return null;
        const overlay = document.createElement('div');
        overlay.className = 'card-value-overlay';
        if (isNegative) overlay.classList.add('negative');
        if (value === 0) overlay.classList.add('zero');

        const sign = value > 0 ? '+' : '';
        overlay.textContent = `${sign}${value}`;

        const rect = cardElement.getBoundingClientRect();
        overlay.style.left = `${rect.left + rect.width / 2}px`;
        overlay.style.top = `${rect.top + rect.height / 2}px`;

        document.body.appendChild(overlay);
        // Trigger reflow then animate in
        void overlay.offsetWidth;
        overlay.classList.add('visible');
        return overlay;
    }

    hideCardValue(overlay) {
        if (!overlay) return;
        overlay.classList.remove('visible');
        setTimeout(() => overlay.remove(), 200);
    }

    showPairCancel(card1, card2) {
        if (!card1 || !card2) return;
        const rect1 = card1.getBoundingClientRect();
        const rect2 = card2.getBoundingClientRect();
        const centerX = (rect1.left + rect1.right + rect2.left + rect2.right) / 4;
        const centerY = (rect1.top + rect1.bottom + rect2.top + rect2.bottom) / 4;

        const overlay = document.createElement('div');
        overlay.className = 'pair-cancel-overlay';
        overlay.textContent = 'PAIR! +0';
        overlay.style.left = `${centerX}px`;
        overlay.style.top = `${centerY}px`;
        document.body.appendChild(overlay);

        card1.classList.add('pair-matched');
        card2.classList.add('pair-matched');

        this.playSound('pair');

        setTimeout(() => {
            overlay.remove();
            card1.classList.remove('pair-matched');
            card2.classList.remove('pair-matched');
        }, 600);
    }

    getDefaultCardValues() {
        return {
            'A': 1, '2': -2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
            '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 0, '★': -2
        };
    }

    // Fire-and-forget animation triggers based on state changes
    triggerAnimationsForStateChange(oldState, newState) {
        if (!oldState) return;

        const currentPlayerId = newState.current_player_id;
        const previousPlayerId = oldState.current_player_id;
        const wasOtherPlayer = previousPlayerId && previousPlayerId !== this.playerId;

        // Check for discard pile changes
        const newDiscard = newState.discard_top;
        const oldDiscard = oldState.discard_top;
        const discardChanged = newDiscard && (!oldDiscard ||
            newDiscard.rank !== oldDiscard.rank ||
            newDiscard.suit !== oldDiscard.suit);

        debugLog('DIFFER', 'State diff', {
            discardChanged,
            oldDiscard: oldDiscard ? `${oldDiscard.rank}${oldDiscard.suit?.[0]}` : 'EMPTY',
            newDiscard: newDiscard ? `${newDiscard.rank}${newDiscard.suit?.[0]}` : 'EMPTY',
            turnChanged: previousPlayerId !== currentPlayerId,
            wasOtherPlayer
        });

        // STEP 1: Detect when someone DRAWS (drawn_card goes from null to something)
        const justDrew = !oldState.drawn_card && newState.drawn_card;
        const drawingPlayerId = newState.drawn_player_id;
        const isOtherPlayerDrawing = drawingPlayerId && drawingPlayerId !== this.playerId;

        if (justDrew && isOtherPlayerDrawing) {
            // Detect source: if old discard is gone, they took from discard
            const discardWasTaken = oldDiscard && (!newDiscard ||
                newDiscard.rank !== oldDiscard.rank ||
                newDiscard.suit !== oldDiscard.suit);

            debugLog('DIFFER', 'Other player drew', {
                source: discardWasTaken ? 'discard' : 'deck',
                drawnCard: newState.drawn_card ? `${newState.drawn_card.rank}` : '?'
            });

            // Use shared draw animation system for consistent look
            if (window.drawAnimations) {
                // Set flag to defer held card display until animation completes
                this.drawPulseAnimation = true;

                const drawnCard = newState.drawn_card;
                const onAnimComplete = () => {
                    this.drawPulseAnimation = false;
                    // Show the held card after animation (no popIn - match local player)
                    if (this.gameState?.drawn_card) {
                        this.displayHeldCard(this.gameState.drawn_card, false);
                    }
                };

                if (discardWasTaken) {
                    // Clear any in-progress animations to prevent race conditions
                    this.opponentSwapAnimation = null;
                    this.opponentDiscardAnimating = false;
                    // Set isDrawAnimating to block renderGame from updating discard pile
                    this.isDrawAnimating = true;
                    console.log('[DEBUG] Opponent draw from discard - setting isDrawAnimating=true');
                    window.drawAnimations.animateDrawDiscard(drawnCard, () => {
                        console.log('[DEBUG] Opponent draw from discard complete - clearing isDrawAnimating');
                        this.isDrawAnimating = false;
                        onAnimComplete();
                    });
                } else {
                    // Clear any in-progress animations to prevent race conditions
                    this.opponentSwapAnimation = null;
                    this.opponentDiscardAnimating = false;
                    this.isDrawAnimating = true;
                    console.log('[DEBUG] Opponent draw from deck - setting isDrawAnimating=true');
                    window.drawAnimations.animateDrawDeck(drawnCard, () => {
                        console.log('[DEBUG] Opponent draw from deck complete - clearing isDrawAnimating');
                        this.isDrawAnimating = false;
                        onAnimComplete();
                    });
                }
            }

            // Show CPU action announcement
            const drawingPlayer = newState.players.find(p => p.id === drawingPlayerId);
            if (drawingPlayer?.is_cpu) {
                if (discardWasTaken && oldDiscard) {
                    this.showCpuAction(drawingPlayer.name, 'draw-discard', oldDiscard);
                } else {
                    this.showCpuAction(drawingPlayer.name, 'draw-deck');
                }
            }
        }

        // V3_15: Track discard history
        if (discardChanged && newDiscard) {
            this.trackDiscardHistory(newDiscard);
        }

        // Track if we detected a draw this update - if so, skip STEP 2
        // Drawing from discard changes the discard pile but isn't a "discard" action
        const justDetectedDraw = justDrew && isOtherPlayerDrawing;
        if (justDetectedDraw && discardChanged) {
            console.log('[DEBUG] Skipping STEP 2 - discard change was from draw, not discard action');
        }

        // STEP 2: Detect when someone FINISHES their turn (discard changes, turn advances)
        // Skip if we just detected a draw - the discard change was from REMOVING a card, not adding one
        if (discardChanged && wasOtherPlayer && !justDetectedDraw) {
            // Check if the previous player actually SWAPPED (has a new face-up card)
            // vs just discarding the drawn card (no hand change)
            const oldPlayer = oldState.players.find(p => p.id === previousPlayerId);
            const newPlayer = newState.players.find(p => p.id === previousPlayerId);

            if (oldPlayer && newPlayer) {
                // Find the position that changed
                // Could be: face-down -> face-up (new reveal)
                // Or: different card at same position (replaced visible card)
                // Or: card identity became known (null -> value, indicates swap)
                let swappedPosition = -1;
                let wasFaceUp = false;  // Track if old card was already face-up

                for (let i = 0; i < 6; i++) {
                    const oldCard = oldPlayer.cards[i];
                    const newCard = newPlayer.cards[i];
                    const wasUp = oldCard?.face_up;
                    const isUp = newCard?.face_up;

                    // Case 1: face-down became face-up (needs flip)
                    if (!wasUp && isUp) {
                        swappedPosition = i;
                        wasFaceUp = false;
                        break;
                    }
                    // Case 2: both face-up but different card (no flip needed)
                    if (wasUp && isUp && oldCard.rank && newCard.rank) {
                        if (oldCard.rank !== newCard.rank || oldCard.suit !== newCard.suit) {
                            swappedPosition = i;
                            wasFaceUp = true;  // Face-to-face swap
                            break;
                        }
                    }
                    // Case 3: Card identity became known (opponent's hidden card was swapped)
                    // This handles race conditions where face_up might not be updated yet
                    if (!oldCard?.rank && newCard?.rank) {
                        swappedPosition = i;
                        wasFaceUp = false;
                        break;
                    }
                }

                // Check if opponent's cards are completely unchanged (server might send split updates)
                const cardsIdentical = wasOtherPlayer && JSON.stringify(oldPlayer.cards) === JSON.stringify(newPlayer.cards);

                if (swappedPosition >= 0 && wasOtherPlayer) {
                    // Opponent swapped - animate from the actual position that changed
                    this.fireSwapAnimation(previousPlayerId, newDiscard, swappedPosition, wasFaceUp);
                    // Show CPU swap announcement
                    if (oldPlayer.is_cpu) {
                        this.showCpuAction(oldPlayer.name, 'swap');
                    }
                } else if (swappedPosition < 0 && wasOtherPlayer) {
                    // Opponent drew and discarded without swapping (cards unchanged)
                    this.fireDiscardAnimation(newDiscard, previousPlayerId);
                    // Show CPU discard announcement
                    if (oldPlayer?.is_cpu) {
                        this.showCpuAction(oldPlayer.name, 'discard', newDiscard);
                    }
                }
                // Skip the card-flip-in animation since we just did our own
                this.skipNextDiscardFlip = true;
            }
        }

        // V3_04: Check for new column pairs after any state change
        this.checkForNewPairs(oldState, newState);

        // V3_09: Detect opponent knock (phase transition to final_turn)
        if (oldState.phase !== 'final_turn' && newState.phase === 'final_turn') {
            const knocker = newState.players.find(p => p.id === newState.finisher_id);
            if (knocker && knocker.id !== this.playerId) {
                this.playSound('alert');
                this.showKnockBanner(knocker.name);
            }
            // V3_14: Highlight relevant knock rules
            if (this.gameState?.knock_penalty) {
                this.highlightRule('knock_penalty', '+10 if beaten!');
            }
            if (this.gameState?.knock_bonus) {
                this.highlightRule('knock_bonus', '-5 for going out!');
            }
        }

        // Handle delayed card updates (server sends split updates: discard first, then cards)
        // Check if opponent cards changed even when discard didn't change
        if (!discardChanged && wasOtherPlayer && previousPlayerId) {
            const oldPlayer = oldState.players.find(p => p.id === previousPlayerId);
            const newPlayer = newState.players.find(p => p.id === previousPlayerId);

            if (oldPlayer && newPlayer) {
                // Check for card changes that indicate a swap we missed
                for (let i = 0; i < 6; i++) {
                    const oldCard = oldPlayer.cards[i];
                    const newCard = newPlayer.cards[i];

                    // Card became visible (swap completed in delayed update)
                    if (!oldCard?.face_up && newCard?.face_up) {
                        this.fireSwapAnimation(previousPlayerId, newState.discard_top, i, false);
                        if (oldPlayer.is_cpu) {
                            this.showCpuAction(oldPlayer.name, 'swap');
                        }
                        break;
                    }
                    // Card identity became known
                    if (!oldCard?.rank && newCard?.rank) {
                        this.fireSwapAnimation(previousPlayerId, newState.discard_top, i, false);
                        if (oldPlayer.is_cpu) {
                            this.showCpuAction(oldPlayer.name, 'swap');
                        }
                        break;
                    }
                }
            }
        }
    }

    // --- V3_04: Column Pair Detection ---

    checkForNewPairs(oldState, newState) {
        if (!oldState || !newState) return;

        const columns = [[0, 3], [1, 4], [2, 5]];

        for (const newPlayer of newState.players) {
            const oldPlayer = oldState.players.find(p => p.id === newPlayer.id);
            if (!oldPlayer) continue;

            for (const [top, bottom] of columns) {
                const wasPaired = this.isColumnPaired(oldPlayer.cards, top, bottom);
                const nowPaired = this.isColumnPaired(newPlayer.cards, top, bottom);

                if (!wasPaired && nowPaired) {
                    // New pair formed!
                    setTimeout(() => {
                        this.firePairCelebration(newPlayer.id, top, bottom);
                    }, window.TIMING?.celebration?.pairDelay || 50);
                }
            }
        }
    }

    isColumnPaired(cards, pos1, pos2) {
        const c1 = cards[pos1];
        const c2 = cards[pos2];
        return c1?.face_up && c2?.face_up && c1?.rank && c2?.rank && c1.rank === c2.rank;
    }

    firePairCelebration(playerId, pos1, pos2) {
        const elements = this.getCardElements(playerId, pos1, pos2);
        if (elements.length < 2) return;

        if (window.cardAnimations) {
            window.cardAnimations.celebratePair(elements[0], elements[1]);
        }
    }

    getCardElements(playerId, ...positions) {
        const elements = [];

        if (playerId === this.playerId) {
            const cards = this.playerCards.querySelectorAll('.card');
            for (const pos of positions) {
                if (cards[pos]) elements.push(cards[pos]);
            }
        } else {
            const area = this.opponentsRow.querySelector(
                `.opponent-area[data-player-id="${playerId}"]`
            );
            if (area) {
                const cards = area.querySelectorAll('.card');
                for (const pos of positions) {
                    if (cards[pos]) elements.push(cards[pos]);
                }
            }
        }

        return elements;
    }

    // V3_15: Track discard pile history
    trackDiscardHistory(card) {
        if (!card) return;
        // Avoid duplicates at front
        if (this.discardHistory.length > 0 &&
            this.discardHistory[0].rank === card.rank &&
            this.discardHistory[0].suit === card.suit) return;
        this.discardHistory.unshift({ rank: card.rank, suit: card.suit });
        if (this.discardHistory.length > this.maxDiscardHistory) {
            this.discardHistory = this.discardHistory.slice(0, this.maxDiscardHistory);
        }
        this.updateDiscardDepth();
    }

    updateDiscardDepth() {
        if (!this.discard) return;
        const depth = Math.min(this.discardHistory.length, 3);
        this.discard.dataset.depth = depth;
    }

    clearDiscardHistory() {
        this.discardHistory = [];
        if (this.discard) this.discard.dataset.depth = '0';
    }

    // V3_10: Render persistent pair indicators on all players' cards
    renderPairIndicators() {
        if (!this.gameState) return;
        const columns = [[0, 3], [1, 4], [2, 5]];

        for (const player of this.gameState.players) {
            const cards = this.getCardElements(player.id, 0, 1, 2, 3, 4, 5);
            if (cards.length < 6) continue;

            // Clear previous pair classes
            cards.forEach(c => c.classList.remove('paired', 'pair-top', 'pair-bottom'));

            for (const [top, bottom] of columns) {
                if (this.isColumnPaired(player.cards, top, bottom)) {
                    cards[top]?.classList.add('paired', 'pair-top');
                    cards[bottom]?.classList.add('paired', 'pair-bottom');
                }
            }
        }
    }

    // Flash animation on deck or discard pile to show where opponent drew from
    // Defers held card display until pulse completes for clean sequencing
    pulseDrawPile(source) {
        const T = window.TIMING?.feedback || {};
        const pulseDuration = T.drawPulse || 450;
        const pile = source === 'discard' ? this.discard : this.deck;

        // Set flag to defer held card display
        this.drawPulseAnimation = true;

        pile.classList.remove('draw-pulse');
        void pile.offsetWidth;
        pile.classList.add('draw-pulse');

        // After pulse completes, show the held card
        setTimeout(() => {
            pile.classList.remove('draw-pulse');
            this.drawPulseAnimation = false;

            // Show the held card (no pop-in - match local player behavior)
            if (this.gameState?.drawn_card && this.gameState?.drawn_player_id !== this.playerId) {
                this.displayHeldCard(this.gameState.drawn_card, false);
            }
        }, pulseDuration);
    }

    // Pulse discard pile when a card lands on it
    // Optional callback fires after pulse completes (for sequencing turn indicator update)
    pulseDiscardLand(onComplete = null) {
        // Use anime.js for discard pulse
        if (window.cardAnimations) {
            window.cardAnimations.pulseDiscard();
        }
        // Execute callback after animation
        const T = window.TIMING?.feedback || {};
        const duration = T.discardLand || 375;
        setTimeout(() => {
            if (onComplete) onComplete();
        }, duration);
    }

    // Fire animation for discard without swap (card lands on discard pile face-up)
    // Shows card moving from deck to discard for other players only
    fireDiscardAnimation(discardCard, fromPlayerId = null) {
        // Only show animation for other players - local player already knows what they did
        const isOtherPlayer = fromPlayerId && fromPlayerId !== this.playerId;

        if (isOtherPlayer && discardCard && window.cardAnimations) {
            // Block renderGame from updating discard during animation
            this.opponentDiscardAnimating = true;
            this.skipNextDiscardFlip = true;

            // Update lastDiscardKey so renderGame won't see a "change" and trigger flip animation
            this.lastDiscardKey = `${discardCard.rank}-${discardCard.suit}`;

            // Animate card from hold → discard using anime.js
            window.cardAnimations.animateOpponentDiscard(discardCard, () => {
                this.opponentDiscardAnimating = false;
                this.updateDiscardPileDisplay(discardCard);
                this.pulseDiscardLand();
            });
        }
        // Skip animation entirely for local player
    }

    // Get rotation angle from an element's computed transform
    getElementRotation(element) {
        if (!element) return 0;
        const style = window.getComputedStyle(element);
        const transform = style.transform;
        if (!transform || transform === 'none') return 0;

        // Parse rotation from transform matrix
        const values = transform.split('(')[1]?.split(')')[0]?.split(',');
        if (values && values.length >= 2) {
            const a = parseFloat(values[0]);
            const b = parseFloat(values[1]);
            return Math.round(Math.atan2(b, a) * (180 / Math.PI));
        }
        return 0;
    }

    // Fire a swap animation (non-blocking) - unified arc swap for all players
    fireSwapAnimation(playerId, discardCard, position, wasFaceUp = false) {
        // Track this animation so renderGame can apply swap-out class
        this.opponentSwapAnimation = { playerId, position };

        // Find source position - the actual card that was swapped
        const area = this.opponentsRow.querySelector(`.opponent-area[data-player-id="${playerId}"]`);
        let sourceRect = null;
        let sourceCardEl = null;
        let sourceRotation = 0;

        if (area) {
            const cards = area.querySelectorAll('.card-grid .card');
            if (cards.length > position && position >= 0) {
                sourceCardEl = cards[position];
                sourceRect = sourceCardEl.getBoundingClientRect();
                sourceRotation = this.getElementRotation(area);
            }
        }

        // Get the held card data (what's being swapped IN to the hand)
        const player = this.gameState?.players.find(p => p.id === playerId);
        const newCardInHand = player?.cards[position];

        // Safety check - need valid data for animation
        if (!sourceRect || !discardCard || !newCardInHand) {
            console.warn('fireSwapAnimation: missing data', { sourceRect: !!sourceRect, discardCard: !!discardCard, newCardInHand: !!newCardInHand });
            this.opponentSwapAnimation = null;
            this.opponentDiscardAnimating = false;
            this.renderGame();
            return;
        }

        // Hide the source card during animation
        sourceCardEl.classList.add('swap-out');

        // Use unified swap animation
        if (window.cardAnimations) {
            window.cardAnimations.animateUnifiedSwap(
                discardCard,        // handCardData - card going to discard
                newCardInHand,      // heldCardData - card going to hand
                sourceRect,         // handRect - where the hand card is
                null,               // heldRect - use default holding position
                {
                    rotation: sourceRotation,
                    wasHandFaceDown: !wasFaceUp,
                    onComplete: () => {
                        sourceCardEl.classList.remove('swap-out');
                        this.opponentSwapAnimation = null;
                        this.opponentDiscardAnimating = false;
                        console.log('[DEBUG] Swap animation complete - clearing opponentSwapAnimation and opponentDiscardAnimating');
                        this.renderGame();
                    }
                }
            );
        } else {
            // Fallback
            setTimeout(() => {
                sourceCardEl.classList.remove('swap-out');
                this.opponentSwapAnimation = null;
                this.opponentDiscardAnimating = false;
                console.log('[DEBUG] Swap animation fallback complete - clearing flags');
                this.renderGame();
            }, 500);
        }
    }

    // Fire a flip animation for local player's card (non-blocking)
    fireLocalFlipAnimation(position, cardData) {
        const key = `local-${position}`;
        if (this.animatingPositions.has(key)) return;
        this.animatingPositions.add(key);

        const cardElements = this.playerCards.querySelectorAll('.card');
        const cardEl = cardElements[position];
        if (!cardEl) {
            this.animatingPositions.delete(key);
            return;
        }

        // Use the unified card animation system for consistent flip animation
        if (window.cardAnimations) {
            window.cardAnimations.animateInitialFlip(cardEl, cardData, () => {
                this.animatingPositions.delete(key);
            });
        } else {
            // Fallback if card animations not available
            this.animatingPositions.delete(key);
        }
    }

    // Fire a flip animation for opponent card (non-blocking)
    fireFlipAnimation(playerId, position, cardData) {
        // Skip if already animating this position
        const key = `${playerId}-${position}`;
        if (this.animatingPositions.has(key)) return;
        this.animatingPositions.add(key);

        // Find the card element and parent area (for rotation)
        const opponentAreas = this.opponentsRow.querySelectorAll('.opponent-area');
        let cardEl = null;
        let sourceRotation = 0;

        for (const area of opponentAreas) {
            const nameEl = area.querySelector('h4');
            const player = this.gameState?.players.find(p => p.id === playerId);
            if (nameEl && player && nameEl.textContent.includes(player.name)) {
                const cards = area.querySelectorAll('.card');
                cardEl = cards[position];
                sourceRotation = this.getElementRotation(area);
                break;
            }
        }

        if (!cardEl) {
            this.animatingPositions.delete(key);
            return;
        }

        // Use the unified card animation system for consistent flip animation
        if (window.cardAnimations) {
            window.cardAnimations.animateOpponentFlip(cardEl, cardData, sourceRotation);
        }

        // Clear tracking after animation duration
        setTimeout(() => {
            this.animatingPositions.delete(key);
        }, (window.TIMING?.card?.flip || 400) + 100);
    }

    handleCardClick(position) {
        const myData = this.getMyPlayerData();
        if (!myData) return;

        const card = myData.cards[position];

        // Check for flip-as-action: can flip face-down card instead of drawing
        const canFlipAsAction = this.gameState.flip_as_action &&
                                this.isMyTurn() &&
                                !this.drawnCard &&
                                !this.gameState.has_drawn_card &&
                                !card.face_up &&
                                !this.gameState.waiting_for_initial_flip;
        if (canFlipAsAction) {
            this.playSound('flip');
            this.fireLocalFlipAnimation(position, card);
            this.send({ type: 'flip_as_action', position });
            this.hideToast();
            return;
        }

        // Check if action is allowed - if not, play reject sound
        const canAct = this.gameState.waiting_for_initial_flip ||
                       this.drawnCard ||
                       this.waitingForFlip;
        if (!canAct) {
            this.playSound('reject');
            return;
        }

        // Initial flip phase
        if (this.gameState.waiting_for_initial_flip) {
            if (card.face_up) return;
            // Use Set to prevent duplicates - check both tracking mechanisms
            if (this.locallyFlippedCards.has(position)) return;
            if (this.selectedCards.includes(position)) return;

            const requiredFlips = this.gameState.initial_flips || 2;

            // Track locally and animate immediately
            this.locallyFlippedCards.add(position);
            this.selectedCards.push(position);

            // Fire flip animation (non-blocking)
            this.fireLocalFlipAnimation(position, card);

            // Re-render to show flipped state
            this.renderGame();

            // Use Set to ensure unique positions when sending to server
            const uniquePositions = [...new Set(this.selectedCards)];
            if (uniquePositions.length === requiredFlips) {
                this.send({ type: 'flip_initial', positions: uniquePositions });
                this.selectedCards = [];
                // Note: locallyFlippedCards is cleared when server confirms (in game_state handler)
                this.hideToast();
            } else {
                const remaining = requiredFlips - uniquePositions.length;
                this.showToast(`Select ${remaining} more card${remaining > 1 ? 's' : ''} to flip`, '', 5000);
            }
            return;
        }

        // Swap with drawn card
        if (this.drawnCard) {
            this.animateSwap(position);
            this.hideToast();
            return;
        }

        // Flip after discarding from deck (flip_on_discard variant)
        if (this.waitingForFlip && !card.face_up) {
            // Animate immediately, then send to server
            this.fireLocalFlipAnimation(position, card);
            this.flipCard(position);
            this.hideToast();
            return;
        }
    }

    nextRound() {
        this.clearNextHoleCountdown();
        this.send({ type: 'next_round' });
        this.gameButtons.classList.add('hidden');
        this.nextRoundBtn.classList.remove('waiting');
    }

    newGame() {
        this.leaveRoom();
    }

    leaveGame() {
        if (this.isHost) {
            // Host ending game affects everyone
            if (confirm('End game for all players?')) {
                this.send({ type: 'end_game' });
            }
        } else {
            // Regular player just leaves
            if (confirm('Leave this game?')) {
                this.send({ type: 'leave_game' });
                this.ws.close();
                this.showLobby();
            }
        }
    }

    // UI Helpers
    showScreen(screen) {
        this.lobbyScreen.classList.remove('active');
        this.waitingScreen.classList.remove('active');
        this.gameScreen.classList.remove('active');
        if (this.rulesScreen) {
            this.rulesScreen.classList.remove('active');
        }
        screen.classList.add('active');

        // Handle auth bar visibility - hide global bar during game, show in-game controls instead
        const isGameScreen = screen === this.gameScreen;
        const user = this.auth?.user;

        if (isGameScreen && user) {
            // Hide global auth bar, show in-game auth controls
            this.authBar?.classList.add('hidden');
            this.gameUsername.textContent = user.username;
            this.gameUsername.classList.remove('hidden');
            this.gameLogoutBtn.classList.remove('hidden');
        } else {
            // Show global auth bar (if logged in), hide in-game auth controls
            if (user) {
                this.authBar?.classList.remove('hidden');
            }
            this.gameUsername.classList.add('hidden');
            this.gameLogoutBtn.classList.add('hidden');
        }
    }

    showLobby() {
        this.showScreen(this.lobbyScreen);
        this.lobbyError.textContent = '';
        this.roomCode = null;
        this.playerId = null;
        this.isHost = false;
        this.gameState = null;
        this.previousState = null;
    }

    showWaitingRoom() {
        this.showScreen(this.waitingScreen);
        this.displayRoomCode.textContent = this.roomCode;

        if (this.isHost) {
            this.hostSettings.classList.remove('hidden');
            this.cpuControlsSection.classList.remove('hidden');
            this.waitingMessage.classList.add('hidden');
            // Initialize deck color preview
            this.updateDeckColorPreview();
        } else {
            this.hostSettings.classList.add('hidden');
            this.cpuControlsSection.classList.add('hidden');
            this.waitingMessage.classList.remove('hidden');
        }
    }

    showGameScreen() {
        this.showScreen(this.gameScreen);
        this.gameButtons.classList.add('hidden');
        this.drawnCard = null;
        this.selectedCards = [];
        this.waitingForFlip = false;
        this.previousState = null;
        // Update leave button text based on role
        this.leaveGameBtn.textContent = this.isHost ? 'End Game' : 'Leave';
        // Update active rules bar
        this.updateActiveRulesBar();
    }

    updateActiveRulesBar() {
        if (!this.gameState) {
            this.activeRulesBar.classList.add('hidden');
            return;
        }

        const rules = this.gameState.active_rules || [];
        // V3_14: Add data-rule attributes for contextual highlighting
        const renderTag = (rule) => {
            const key = this.getRuleKey(rule);
            return `<span class="rule-tag" data-rule="${key}">${rule}</span>`;
        };

        if (rules.length === 0) {
            this.activeRulesList.innerHTML = '<span class="rule-tag standard">Standard</span>';
        } else if (rules.length <= 2) {
            this.activeRulesList.innerHTML = rules.map(renderTag).join('');
        } else {
            const displayed = rules.slice(0, 2);
            const hidden = rules.slice(2);
            const moreCount = hidden.length;
            const tooltip = hidden.join(', ');

            this.activeRulesList.innerHTML = displayed.map(renderTag).join('') +
                `<span class="rule-tag rule-more" title="${tooltip}">+${moreCount} more</span>`;
        }
        this.activeRulesBar.classList.remove('hidden');
    }

    // V3_14: Map display names to rule keys
    getRuleKey(ruleName) {
        const mapping = {
            'Speed Golf': 'flip_mode', 'Endgame Flip': 'flip_mode',
            'Knock Penalty': 'knock_penalty', 'Knock Bonus': 'knock_bonus',
            'Super Kings': 'super_kings', 'Ten Penny': 'ten_penny',
            'Lucky Swing': 'lucky_swing', 'Eagle Eye': 'eagle_eye',
            'Underdog': 'underdog_bonus', 'Tied Shame': 'tied_shame',
            'Blackjack': 'blackjack', 'Wolfpack': 'wolfpack',
            'Flip Action': 'flip_as_action', '4 of a Kind': 'four_of_a_kind',
            'Negative Pairs': 'negative_pairs_keep_value',
            'One-Eyed Jacks': 'one_eyed_jacks', 'Knock Early': 'knock_early',
        };
        return mapping[ruleName] || ruleName.toLowerCase().replace(/\s+/g, '_');
    }

    // V3_14: Contextual rule highlighting
    highlightRule(ruleKey, message, duration = 3000) {
        const ruleTag = this.activeRulesList?.querySelector(`[data-rule="${ruleKey}"]`);
        if (!ruleTag) return;

        ruleTag.classList.add('rule-highlighted');
        const messageEl = document.createElement('span');
        messageEl.className = 'rule-message';
        messageEl.textContent = message;
        ruleTag.appendChild(messageEl);

        setTimeout(() => {
            ruleTag.classList.remove('rule-highlighted');
            messageEl.remove();
        }, duration);
    }

    showError(message) {
        this.lobbyError.textContent = message;
        this.playSound('reject');
        console.error('Game error:', message);
    }

    updatePlayersList(players) {
        this.playersList.innerHTML = '';
        players.forEach(player => {
            const li = document.createElement('li');
            let badges = '';
            if (player.is_host) badges += '<span class="host-badge">HOST</span>';
            if (player.is_cpu) badges += '<span class="cpu-badge">CPU</span>';

            li.innerHTML = `
                <span>${player.name}</span>
                <span>${badges}</span>
            `;
            if (player.id === this.playerId) {
                li.style.background = 'rgba(244, 164, 96, 0.3)';
            }
            this.playersList.appendChild(li);

            if (player.id === this.playerId && player.is_host) {
                this.isHost = true;
                this.hostSettings.classList.remove('hidden');
                this.cpuControlsSection.classList.remove('hidden');
                this.waitingMessage.classList.add('hidden');
            }
        });

        // Auto-select 2 decks when reaching 4+ players (host only)
        const prevCount = this.currentPlayers ? this.currentPlayers.length : 0;
        if (this.isHost && prevCount < 4 && players.length >= 4) {
            if (this.numDecksInput) this.numDecksInput.value = '2';
            if (this.numDecksDisplay) this.numDecksDisplay.textContent = '2';
            this.updateDeckColorPreview();
        }

        // Update deck recommendation visibility
        this.updateDeckRecommendation(players.length);
    }

    updateDeckRecommendation(playerCount) {
        if (!this.isHost || !this.deckRecommendation) return;

        const decks = parseInt(this.numDecksInput?.value || '1');
        // Show recommendation if 4+ players and only 1 deck selected
        if (playerCount >= 4 && decks < 2) {
            this.deckRecommendation.classList.remove('hidden');
        } else {
            this.deckRecommendation.classList.add('hidden');
        }
    }

    adjustDeckCount(delta) {
        if (!this.numDecksInput) return;

        let current = parseInt(this.numDecksInput.value) || 1;
        let newValue = Math.max(1, Math.min(3, current + delta));

        this.numDecksInput.value = newValue;
        if (this.numDecksDisplay) {
            this.numDecksDisplay.textContent = newValue;
        }

        // Update related UI
        const playerCount = this.currentPlayers ? this.currentPlayers.length : 0;
        this.updateDeckRecommendation(playerCount);
        this.updateDeckColorPreview();
    }

    getDeckColors(numDecks) {
        const multiColorPresets = {
            classic: ['red', 'blue', 'gold'],
            ninja: ['green', 'purple', 'orange'],
            ocean: ['blue', 'teal', 'cyan'],
            forest: ['green', 'gold', 'brown'],
            sunset: ['orange', 'red', 'purple'],
            berry: ['purple', 'pink', 'red'],
            neon: ['pink', 'cyan', 'green'],
            royal: ['purple', 'gold', 'red'],
            earth: ['brown', 'green', 'gold']
        };

        const singleColorPresets = {
            'all-red': 'red',
            'all-blue': 'blue',
            'all-green': 'green',
            'all-gold': 'gold',
            'all-purple': 'purple',
            'all-teal': 'teal',
            'all-pink': 'pink',
            'all-slate': 'slate'
        };

        const preset = this.deckColorPresetSelect?.value || 'classic';

        if (singleColorPresets[preset]) {
            const color = singleColorPresets[preset];
            return Array(numDecks).fill(color);
        }

        const colors = multiColorPresets[preset] || multiColorPresets.classic;
        return colors.slice(0, numDecks);
    }

    updateDeckColorPreview() {
        if (!this.deckColorPreview) return;

        const numDecks = parseInt(this.numDecksInput?.value || '1');
        const colors = this.getDeckColors(numDecks);

        this.deckColorPreview.innerHTML = '';

        colors.forEach(color => {
            const card = document.createElement('div');
            card.className = `preview-card deck-${color}`;
            this.deckColorPreview.appendChild(card);
        });
    }

    isMyTurn() {
        return this.gameState && this.gameState.current_player_id === this.playerId;
    }

    // Visual check: don't show "my turn" indicators until opponent swap animation completes
    isVisuallyMyTurn() {
        if (this.opponentSwapAnimation) return false;
        return this.isMyTurn();
    }

    getMyPlayerData() {
        if (!this.gameState) return null;
        return this.gameState.players.find(p => p.id === this.playerId);
    }

    setStatus(message, type = '') {
        this.statusMessage.textContent = message;
        this.statusMessage.className = 'status-message' + (type ? ' ' + type : '');
    }

    // Show CPU action announcement in status bar
    showCpuAction(playerName, action, card = null) {
        const suitSymbol = card ? this.getSuitSymbol(card.suit) : '';
        const messages = {
            'draw-deck': `${playerName} draws from deck`,
            'draw-discard': card ? `${playerName} takes ${card.rank}${suitSymbol}` : `${playerName} takes from discard`,
            'swap': `${playerName} swaps a card`,
            'discard': card ? `${playerName} discards ${card.rank}${suitSymbol}` : `${playerName} discards`,
        };
        const message = messages[action];
        if (message) {
            this.setStatus(message, 'cpu-action');
        }
    }

    // Update CPU considering visual state on discard pile and opponent area
    updateCpuConsideringState() {
        if (!this.gameState || !this.discard) return;

        const currentPlayer = this.gameState.players.find(p => p.id === this.gameState.current_player_id);
        const isCpuTurn = currentPlayer && currentPlayer.is_cpu;
        const hasNotDrawn = !this.gameState.has_drawn_card;
        const isOtherTurn = currentPlayer && currentPlayer.id !== this.playerId;

        if (isCpuTurn && hasNotDrawn) {
            this.discard.classList.add('cpu-considering');
            if (window.cardAnimations) {
                window.cardAnimations.startCpuThinking(this.discard);
            }
        } else {
            this.discard.classList.remove('cpu-considering');
            if (window.cardAnimations) {
                window.cardAnimations.stopCpuThinking(this.discard);
            }
        }

        // V3_06: Update thinking indicator and opponent area glow
        this.opponentsRow.querySelectorAll('.opponent-area').forEach(area => {
            const playerId = area.dataset.playerId;
            const isThisPlayer = playerId === this.gameState.current_player_id;
            const player = this.gameState.players.find(p => p.id === playerId);
            const isCpu = player?.is_cpu;

            // Thinking indicator visibility
            const indicator = area.querySelector('.thinking-indicator');
            if (indicator) {
                indicator.classList.toggle('hidden', !(isCpu && isThisPlayer && hasNotDrawn));
            }

            // Opponent area thinking glow (anime.js)
            if (isOtherTurn && isThisPlayer && hasNotDrawn && window.cardAnimations) {
                window.cardAnimations.startOpponentThinking(area);
            } else if (window.cardAnimations) {
                window.cardAnimations.stopOpponentThinking(area);
            }
        });
    }

    showToast(message, type = '', duration = 2500) {
        // For compatibility - just set the status message
        this.setStatus(message, type);
    }

    hideToast() {
        // Restore default status based on game state
        this.updateStatusFromGameState();
    }

    updateStatusFromGameState() {
        if (!this.gameState) {
            this.setStatus('');
            this.finalTurnBadge.classList.add('hidden');
            return;
        }

        // Check for round/game over states
        if (this.gameState.phase === 'round_over') {
            this.setStatus('Hole Complete!', 'round-over');
            this.finalTurnBadge.classList.add('hidden');
            return;
        }
        if (this.gameState.phase === 'game_over') {
            this.setStatus('Game Over!', 'game-over');
            this.finalTurnBadge.classList.add('hidden');
            return;
        }

        const isFinalTurn = this.gameState.phase === 'final_turn';
        const currentPlayer = this.gameState.players.find(p => p.id === this.gameState.current_player_id);

        // Show/hide final turn badge
        if (isFinalTurn) {
            this.updateFinalTurnDisplay();
        } else {
            this.finalTurnBadge.classList.add('hidden');
            this.gameScreen.classList.remove('final-turn-active');
            this.finalTurnAnnounced = false;
            this.clearKnockerMark();
        }

        if (currentPlayer && currentPlayer.id !== this.playerId) {
            this.setStatus(`${currentPlayer.name}'s turn`, 'opponent-turn');
        } else if (this.isMyTurn()) {
            if (!this.drawnCard && !this.gameState.has_drawn_card) {
                // Build status message based on available actions
                let options = ['draw'];
                if (this.gameState.flip_as_action) options.push('flip');
                // Check knock early eligibility
                const myData = this.gameState.players.find(p => p.id === this.playerId);
                const faceDownCount = myData ? myData.cards.filter(c => !c.face_up).length : 0;
                if (this.gameState.knock_early && faceDownCount >= 1 && faceDownCount <= 2) {
                    options.push('knock');
                }
                if (options.length === 1) {
                    this.setStatus('Your turn - draw a card', 'your-turn');
                } else {
                    this.setStatus(`Your turn - ${options.join('/')}`, 'your-turn');
                }
            } else {
                this.setStatus('Your turn - draw a card', 'your-turn');
            }
        } else {
            this.setStatus('');
        }
    }

    // --- V3_05: Final Turn Urgency ---

    updateFinalTurnDisplay() {
        const finisherId = this.gameState?.finisher_id;

        // Toggle game area class for border pulse
        this.gameScreen.classList.add('final-turn-active');

        // Calculate remaining turns
        const remaining = this.countRemainingTurns();

        // Update badge content
        const remainingEl = this.finalTurnBadge.querySelector('.final-turn-remaining');
        if (remainingEl) {
            remainingEl.textContent = remaining === 1 ? '1 turn left' : `${remaining} turns left`;
        }

        // Show badge
        this.finalTurnBadge.classList.remove('hidden');

        // Mark knocker
        this.markKnocker(finisherId);

        // Play alert sound on first appearance
        if (!this.finalTurnAnnounced) {
            this.playSound('alert');
            this.finalTurnAnnounced = true;
        }
    }

    countRemainingTurns() {
        if (!this.gameState || this.gameState.phase !== 'final_turn') return 0;

        const finisherId = this.gameState.finisher_id;
        const players = this.gameState.players;
        const currentIdx = players.findIndex(p => p.id === this.gameState.current_player_id);
        const finisherIdx = players.findIndex(p => p.id === finisherId);

        if (currentIdx === -1 || finisherIdx === -1) return 0;

        let count = 0;
        let idx = currentIdx;
        while (idx !== finisherIdx) {
            count++;
            idx = (idx + 1) % players.length;
        }

        return count;
    }

    markKnocker(knockerId) {
        this.clearKnockerMark();
        if (!knockerId) return;

        if (knockerId === this.playerId) {
            this.playerArea.classList.add('is-knocker');
            const badge = document.createElement('div');
            badge.className = 'knocker-badge';
            badge.textContent = 'OUT';
            this.playerArea.appendChild(badge);
        } else {
            const area = this.opponentsRow.querySelector(
                `.opponent-area[data-player-id="${knockerId}"]`
            );
            if (area) {
                area.classList.add('is-knocker');
                const badge = document.createElement('div');
                badge.className = 'knocker-badge';
                badge.textContent = 'OUT';
                area.appendChild(badge);
            }
        }
    }

    clearKnockerMark() {
        document.querySelectorAll('.is-knocker').forEach(el => {
            el.classList.remove('is-knocker');
        });
        document.querySelectorAll('.knocker-badge').forEach(el => {
            el.remove();
        });
    }

    showDrawnCard() {
        // Show drawn card floating over the draw pile (deck), regardless of source
        const card = this.drawnCard;
        this.displayHeldCard(card, true);
    }

    // Display held card floating above and between deck and discard - for any player
    // isLocalPlayerHolding: true if this is the local player's card (shows discard button, pulse glow)
    displayHeldCard(card, isLocalPlayerHolding) {
        if (!card) {
            this.hideDrawnCard();
            return;
        }

        // Set up the floating held card display
        this.heldCardFloating.className = 'card card-front held-card-floating';
        // Clear any inline styles left over from swoop animations
        this.heldCardFloating.style.cssText = '';

        // Position centered above and between deck and discard
        const deckRect = this.deck.getBoundingClientRect();
        const discardRect = this.discard.getBoundingClientRect();

        // Calculate center point between deck and discard
        const centerX = (deckRect.left + deckRect.right + discardRect.left + discardRect.right) / 4;
        const cardWidth = deckRect.width;
        const cardHeight = deckRect.height;

        // Position card centered, overlapping both piles (lower than before)
        const overlapOffset = cardHeight * 0.35; // More overlap = lower position
        const cardLeft = centerX - cardWidth / 2;
        const cardTop = deckRect.top - overlapOffset;
        this.heldCardFloating.style.left = `${cardLeft}px`;
        this.heldCardFloating.style.top = `${cardTop}px`;
        this.heldCardFloating.style.width = `${cardWidth}px`;
        this.heldCardFloating.style.height = `${cardHeight}px`;

        // Position discard button attached to right side of held card
        const scaledWidth = cardWidth * 1.15; // Account for scale transform
        const scaledHeight = cardHeight * 1.15;
        const buttonLeft = cardLeft + scaledWidth / 2 + cardWidth / 2; // Right edge of scaled card (no gap)
        const buttonTop = cardTop + (scaledHeight - cardHeight) / 2 + cardHeight * 0.3; // Vertically centered on card
        this.discardBtn.style.left = `${buttonLeft}px`;
        this.discardBtn.style.top = `${buttonTop}px`;

        if (card.rank === '★') {
            this.heldCardFloating.classList.add('joker');
            const jokerIcon = card.suit === 'hearts' ? '🐉' : '👹';
            this.heldCardFloatingContent.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        } else {
            if (this.isRedSuit(card.suit)) {
                this.heldCardFloating.classList.add('red');
            } else {
                this.heldCardFloating.classList.add('black');
            }
            this.heldCardFloatingContent.innerHTML = `${card.rank}<br>${this.getSuitSymbol(card.suit)}`;
        }

        // Show the floating card
        this.heldCardFloating.classList.remove('hidden');

        // Add pulse glow if it's local player's turn to act on the card
        if (isLocalPlayerHolding) {
            this.heldCardFloating.classList.add('your-turn-pulse');
            this.discardBtn.classList.remove('hidden');
        } else {
            this.heldCardFloating.classList.remove('your-turn-pulse');
            this.discardBtn.classList.add('hidden');
        }
    }

    // Display a face-down held card (for when opponent draws from deck)
    displayHeldCardFaceDown() {
        // Set up as face-down card with deck color (use deck_top_deck_id for the color)
        let className = 'card card-back held-card-floating';
        if (this.gameState?.deck_colors) {
            const deckId = this.gameState.deck_top_deck_id || 0;
            const color = this.gameState.deck_colors[deckId] || this.gameState.deck_colors[0];
            if (color) className += ` back-${color}`;
        }
        this.heldCardFloating.className = className;
        this.heldCardFloating.style.cssText = '';

        // Position centered above and between deck and discard
        const deckRect = this.deck.getBoundingClientRect();
        const discardRect = this.discard.getBoundingClientRect();
        const centerX = (deckRect.left + deckRect.right + discardRect.left + discardRect.right) / 4;
        const cardWidth = deckRect.width;
        const cardHeight = deckRect.height;
        const overlapOffset = cardHeight * 0.35;
        const cardLeft = centerX - cardWidth / 2;
        const cardTop = deckRect.top - overlapOffset;

        this.heldCardFloating.style.left = `${cardLeft}px`;
        this.heldCardFloating.style.top = `${cardTop}px`;
        this.heldCardFloating.style.width = `${cardWidth}px`;
        this.heldCardFloating.style.height = `${cardHeight}px`;

        this.heldCardFloatingContent.innerHTML = '';
        this.heldCardFloating.classList.remove('hidden');
        this.heldCardFloating.classList.remove('your-turn-pulse');
        this.discardBtn.classList.add('hidden');

    }

    hideDrawnCard() {
        // Hide the floating held card
        this.heldCardFloating.classList.add('hidden');
        this.heldCardFloating.classList.remove('your-turn-pulse');
        // Clear any inline styles from animations
        this.heldCardFloating.style.cssText = '';
        this.discardBtn.classList.add('hidden');
        // Clear button positioning
        this.discardBtn.style.left = '';
        this.discardBtn.style.top = '';
    }

    isRedSuit(suit) {
        return suit === 'hearts' || suit === 'diamonds';
    }

    calculateShowingScore(cards) {
        if (!cards || cards.length !== 6) return 0;

        // Use card values from server (includes house rules) or defaults
        const cardValues = this.gameState?.card_values || {
            'A': 1, '2': -2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
            '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 0, '★': -2
        };

        const getCardValue = (card) => {
            if (!card.face_up) return 0;
            return cardValues[card.rank] ?? 0;
        };

        // Check for column pairs (cards in same column cancel out if matching)
        let total = 0;
        for (let col = 0; col < 3; col++) {
            const topCard = cards[col];
            const bottomCard = cards[col + 3];

            const topUp = topCard.face_up;
            const bottomUp = bottomCard.face_up;

            // If both face up and matching rank, they cancel (score 0)
            if (topUp && bottomUp && topCard.rank === bottomCard.rank) {
                // Matching pair = 0 points for both
                continue;
            }

            // Otherwise add individual values
            total += getCardValue(topCard);
            total += getCardValue(bottomCard);
        }

        return total;
    }

    getSuitSymbol(suit) {
        const symbols = {
            hearts: '♥',
            diamonds: '♦',
            clubs: '♣',
            spades: '♠'
        };
        return symbols[suit] || '';
    }

    renderCardContent(card) {
        if (!card || !card.face_up) return '';
        // Handle locally-flipped cards where rank/suit aren't known yet
        if (!card.rank || !card.suit) {
            return '';
        }
        // Jokers - use suit to determine icon (hearts = dragon, spades = oni)
        if (card.rank === '★') {
            const jokerIcon = card.suit === 'hearts' ? '🐉' : '👹';
            return `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        }
        return `${card.rank}<br>${this.getSuitSymbol(card.suit)}`;
    }

    renderGame() {
        if (!this.gameState) return;

        // Update CPU considering visual state
        this.updateCpuConsideringState();

        // Update header
        this.currentRoundSpan.textContent = this.gameState.current_round;
        this.totalRoundsSpan.textContent = this.gameState.total_rounds;

        // Show/hide final turn badge with enhanced urgency
        const isFinalTurn = this.gameState.phase === 'final_turn';
        if (isFinalTurn) {
            this.updateFinalTurnDisplay();
        } else {
            this.finalTurnBadge.classList.add('hidden');
            this.gameScreen.classList.remove('final-turn-active');
            this.finalTurnAnnounced = false;
            this.clearKnockerMark();
        }

        // Toggle not-my-turn class to disable hover effects when it's not player's turn
        // Use visual check so turn indicators sync with discard land animation
        const isVisuallyMyTurn = this.isVisuallyMyTurn();
        this.gameScreen.classList.toggle('not-my-turn', !isVisuallyMyTurn);

        // V3_08: Toggle can-swap class for card hover preview when holding a drawn card
        this.playerArea.classList.toggle('can-swap', !!this.drawnCard && this.isMyTurn());

        // Highlight player area when it's their turn (matching opponent-area.current-turn)
        const isActivePlaying = this.gameState.phase !== 'round_over' && this.gameState.phase !== 'game_over';
        this.playerArea.classList.toggle('current-turn', isVisuallyMyTurn && isActivePlaying);

        // Update status message (handled by specific actions, but set default here)
        // During opponent swap animation, show the animating player (not the new current player)
        const displayedPlayerId = this.opponentSwapAnimation
            ? this.opponentSwapAnimation.playerId
            : this.gameState.current_player_id;
        const displayedPlayer = this.gameState.players.find(p => p.id === displayedPlayerId);
        if (displayedPlayer && displayedPlayerId !== this.playerId) {
            this.setStatus(`${displayedPlayer.name}'s turn`);
        }

        // Update player header (name + score like opponents)
        const me = this.gameState.players.find(p => p.id === this.playerId);
        if (me) {
            // Calculate visible score from face-up cards
            const showingScore = this.calculateShowingScore(me.cards);
            this.yourScore.textContent = showingScore;

            // Check if player won the round
            const isRoundWinner = this.roundWinnerNames.has(me.name);
            this.playerArea.classList.toggle('round-winner', isRoundWinner);

            // Update player name in header (truncate if needed)
            const displayName = me.name.length > 12 ? me.name.substring(0, 11) + '…' : me.name;
            const checkmark = me.all_face_up ? ' ✓' : '';
            // Update player name span with crown if winner
            const playerNameSpan = this.playerHeader.querySelector('.player-name');
            const crownHtml = isRoundWinner ? '<span class="winner-crown">👑</span>' : '';
            playerNameSpan.innerHTML = crownHtml + displayName + checkmark;

            // Dealer chip on player area
            const isDealer = this.playerId === this.gameState.dealer_id;
            let dealerChip = this.playerArea.querySelector('.dealer-chip');
            if (isDealer && !dealerChip) {
                dealerChip = document.createElement('div');
                dealerChip.className = 'dealer-chip';
                dealerChip.textContent = 'D';
                this.playerArea.appendChild(dealerChip);
            } else if (!isDealer && dealerChip) {
                dealerChip.remove();
            }
        }

        // Update discard pile
        // Check if ANY player is holding a card (local or remote/CPU)
        const anyPlayerHolding = this.drawnCard || this.gameState.drawn_card;

        debugLog('RENDER', 'Discard pile', {
            anyPlayerHolding: !!anyPlayerHolding,
            localDrawn: this.drawnCard ? `${this.drawnCard.rank}` : null,
            serverDrawn: this.gameState.drawn_card ? `${this.gameState.drawn_card.rank}` : null,
            discardTop: this.gameState.discard_top ? `${this.gameState.discard_top.rank}${this.gameState.discard_top.suit?.[0]}` : 'EMPTY'
        });

        if (anyPlayerHolding) {
            // Someone is holding a drawn card - show discard pile as greyed/disabled
            // If drawn from discard, show what's underneath (new discard_top or empty)
            // If drawn from deck, show current discard_top greyed
            this.discard.classList.add('picked-up');
            this.discard.classList.remove('holding');

            if (this.gameState.discard_top) {
                const discardCard = this.gameState.discard_top;
                this.discard.classList.add('has-card', 'card-front');
                this.discard.classList.remove('card-back', 'red', 'black', 'joker');

                if (discardCard.rank === '★') {
                    this.discard.classList.add('joker');
                } else if (this.isRedSuit(discardCard.suit)) {
                    this.discard.classList.add('red');
                } else {
                    this.discard.classList.add('black');
                }
                this.discardContent.innerHTML = this.renderCardContent(discardCard);
            } else {
                // No card underneath - show empty
                this.discard.classList.remove('has-card', 'card-front', 'red', 'black', 'joker');
                this.discardContent.innerHTML = '';
            }
        } else {
            // Not holding - show normal discard pile
            this.discard.classList.remove('picked-up');

            // Skip discard update during any discard-related animation - animation handles the visual
            const skipReason = this.localDiscardAnimating ? 'localDiscardAnimating' :
                              this.opponentSwapAnimation ? 'opponentSwapAnimation' :
                              this.opponentDiscardAnimating ? 'opponentDiscardAnimating' :
                              this.isDrawAnimating ? 'isDrawAnimating' : null;

            if (skipReason) {
                console.log('[DEBUG] Skipping discard update, reason:', skipReason,
                           'discard_top:', this.gameState.discard_top ?
                           `${this.gameState.discard_top.rank}-${this.gameState.discard_top.suit}` : 'none');
            }

            if (this.localDiscardAnimating) {
                // Don't update discard content; animation will call updateDiscardPileDisplay
            } else if (this.opponentSwapAnimation) {
                // Don't update discard content; animation overlay shows the swap
            } else if (this.opponentDiscardAnimating) {
                // Don't update discard content; opponent discard animation in progress
            } else if (this.isDrawAnimating) {
                // Don't update discard content; draw animation in progress
            } else if (this.gameState.discard_top) {
                const discardCard = this.gameState.discard_top;
                const cardKey = `${discardCard.rank}-${discardCard.suit}`;

                // Only animate discard flip during active gameplay, not at round/game end
                const isActivePlay = this.gameState.phase !== 'round_over' &&
                                     this.gameState.phase !== 'game_over';
                const shouldAnimate = isActivePlay && this.lastDiscardKey &&
                                      this.lastDiscardKey !== cardKey && !this.skipNextDiscardFlip;

                this.skipNextDiscardFlip = false;
                this.lastDiscardKey = cardKey;

                console.log('[DEBUG] Actually updating discard pile content to:', cardKey);

                // Set card content and styling FIRST (before any animation)
                this.discard.classList.add('has-card', 'card-front');
                this.discard.classList.remove('card-back', 'red', 'black', 'joker', 'holding');

                if (discardCard.rank === '★') {
                    this.discard.classList.add('joker');
                } else if (this.isRedSuit(discardCard.suit)) {
                    this.discard.classList.add('red');
                } else {
                    this.discard.classList.add('black');
                }
                this.discardContent.innerHTML = this.renderCardContent(discardCard);

                // THEN animate if needed (content is already set, so no blank flash)
                if (shouldAnimate) {
                    // Remove any existing animation first to allow re-trigger
                    this.discard.classList.remove('card-flip-in');
                    void this.discard.offsetWidth; // Force reflow
                    this.discard.classList.add('card-flip-in');
                    const flipInDuration = window.TIMING?.feedback?.cardFlipIn || 560;
                    setTimeout(() => this.discard.classList.remove('card-flip-in'), flipInDuration);
                }
            } else {
                this.discard.classList.remove('has-card', 'card-front', 'red', 'black', 'joker', 'holding');
                this.discardContent.innerHTML = '';
                this.lastDiscardKey = null;
            }
            this.discardBtn.classList.add('hidden');
        }

        // Show held card for ANY player who has drawn (consistent visual regardless of whose turn)
        // Local player uses this.drawnCard, others use gameState.drawn_card
        // Skip for opponents during draw pulse animation (pulse callback will show it)
        // Skip for local player during draw animation (animation callback will show it)
        if (this.drawnCard && !this.isDrawAnimating) {
            // Local player is holding - show with pulse and discard button
            this.displayHeldCard(this.drawnCard, true);
        } else if (this.gameState.drawn_card && this.gameState.drawn_player_id) {
            // Another player is holding - show without pulse/button
            // But defer display during draw pulse animation for clean sequencing
            // Also skip for local player during their draw animation
            const isLocalPlayer = this.gameState.drawn_player_id === this.playerId;
            const skipForLocalAnim = isLocalPlayer && this.isDrawAnimating;
            if (!this.drawPulseAnimation && !skipForLocalAnim) {
                this.displayHeldCard(this.gameState.drawn_card, isLocalPlayer);
            }
        } else {
            // No one holding a card
            this.hideDrawnCard();
        }

        // Update deck/discard clickability and visual state
        // Use visual check so indicators sync with opponent swap animation
        const hasDrawn = this.drawnCard || this.gameState.has_drawn_card;
        const isRoundActive = this.gameState.phase !== 'round_over' && this.gameState.phase !== 'game_over';
        const canDraw = isRoundActive && this.isVisuallyMyTurn() && !hasDrawn && !this.gameState.waiting_for_initial_flip;

        // Pulse the deck area when it's player's turn to draw
        const wasTurnToDraw = this.deckArea.classList.contains('your-turn-to-draw');
        this.deckArea.classList.toggle('your-turn-to-draw', canDraw);

        // Use anime.js for turn pulse animation
        if (canDraw && !wasTurnToDraw && window.cardAnimations) {
            window.cardAnimations.startTurnPulse(this.deckArea);
        } else if (!canDraw && wasTurnToDraw && window.cardAnimations) {
            window.cardAnimations.stopTurnPulse(this.deckArea);
        }

        this.deck.classList.toggle('clickable', canDraw);
        // Show disabled on deck when any player has drawn (consistent dimmed look)
        this.deck.classList.toggle('disabled', hasDrawn);

        // Apply deck color based on top card's deck_id
        if (this.gameState.deck_colors && this.gameState.deck_colors.length > 0) {
            const deckId = this.gameState.deck_top_deck_id || 0;
            const deckColor = this.gameState.deck_colors[deckId] || this.gameState.deck_colors[0];
            // Remove any existing back-* classes
            this.deck.className = this.deck.className.replace(/\bback-\w+\b/g, '').trim();
            this.deck.classList.add(`back-${deckColor}`);
        }

        this.discard.classList.toggle('clickable', canDraw && this.gameState.discard_top);
        // Disabled state handled by picked-up class when anyone is holding

        // Render opponents in a single row
        const opponents = this.gameState.players.filter(p => p.id !== this.playerId);

        this.opponentsRow.innerHTML = '';

        // Don't highlight current player during round/game over
        const isPlaying = this.gameState.phase !== 'round_over' && this.gameState.phase !== 'game_over';

        // During opponent swap animation, keep highlighting the player who just acted
        // (turn indicator changes after the discard lands, not before)
        const displayedCurrentPlayer = this.opponentSwapAnimation
            ? this.opponentSwapAnimation.playerId
            : this.gameState.current_player_id;

        opponents.forEach((player) => {
            const div = document.createElement('div');
            div.className = 'opponent-area';
            div.dataset.playerId = player.id;
            if (isPlaying && player.id === displayedCurrentPlayer) {
                div.classList.add('current-turn');
            }

            const isRoundWinner = this.roundWinnerNames.has(player.name);
            if (isRoundWinner) {
                div.classList.add('round-winner');
            }

            // Dealer chip
            const isDealer = player.id === this.gameState.dealer_id;
            const dealerChipHtml = isDealer ? '<div class="dealer-chip">D</div>' : '';

            const displayName = player.name.length > 12 ? player.name.substring(0, 11) + '…' : player.name;
            const showingScore = this.calculateShowingScore(player.cards);
            const crownHtml = isRoundWinner ? '<span class="winner-crown">👑</span>' : '';

            // V3_06: Add thinking indicator for CPU opponents
            const isCpuThinking = player.is_cpu && isPlaying &&
                player.id === displayedCurrentPlayer && !newState?.has_drawn_card;
            const thinkingHtml = player.is_cpu
                ? `<span class="thinking-indicator${isCpuThinking ? '' : ' hidden'}">🤔</span>`
                : '';

            div.innerHTML = `
                ${dealerChipHtml}
                <h4>${thinkingHtml}<span class="opponent-name">${crownHtml}${displayName}${player.all_face_up ? ' ✓' : ''}</span><span class="opponent-showing">${showingScore}</span></h4>
                <div class="card-grid">
                    ${player.cards.map(card => this.renderCard(card, false, false)).join('')}
                </div>
            `;

            this.opponentsRow.appendChild(div);
        });

        // Render player's cards
        const myData = this.getMyPlayerData();
        if (myData) {
            this.playerCards.innerHTML = '';

            myData.cards.forEach((card, index) => {
                // Check if this card was locally flipped (immediate feedback)
                const isLocallyFlipped = this.locallyFlippedCards.has(index);

                // Create a display card that shows face-up if locally flipped
                const displayCard = isLocallyFlipped
                    ? { ...card, face_up: true }
                    : card;

                // Check if clickable during initial flip
                const isInitialFlipClickable = this.gameState.waiting_for_initial_flip && !card.face_up && !isLocallyFlipped;

                const isClickable = (
                    isInitialFlipClickable ||
                    (this.drawnCard) ||
                    (this.waitingForFlip && !card.face_up)
                );
                const isSelected = this.selectedCards.includes(index);

                const cardEl = document.createElement('div');
                cardEl.innerHTML = this.renderCard(displayCard, isClickable, isSelected);

                // Add pulse animation during initial flip phase
                if (isInitialFlipClickable) {
                    cardEl.firstChild.classList.add('initial-flip-pulse');
                    cardEl.firstChild.dataset.position = index;
                    // Use anime.js for initial flip pulse
                    if (window.cardAnimations) {
                        window.cardAnimations.startInitialFlipPulse(cardEl.firstChild);
                    }
                }

                cardEl.firstChild.addEventListener('click', () => this.handleCardClick(index));
                // V3_13: Bind tooltip events for face-up cards
                this.bindCardTooltipEvents(cardEl.firstChild, displayCard);
                this.playerCards.appendChild(cardEl.firstChild);
            });
        }

        // V3_10: Update persistent pair indicators
        this.renderPairIndicators();

        // Show flip prompt for initial flip
        // Show flip prompt during initial flip phase (but not during deal animation)
        if (this.gameState.waiting_for_initial_flip && !this.dealAnimationInProgress) {
            const requiredFlips = this.gameState.initial_flips || 2;
            const flippedCount = this.locallyFlippedCards.size;
            const remaining = requiredFlips - flippedCount;
            if (remaining > 0) {
                this.setStatus(`Select ${remaining} card${remaining > 1 ? 's' : ''} to flip`, 'your-turn');
            }
        }

        // Disable discard button if can't discard (must_swap_discard rule)
        if (this.drawnCard && !this.gameState.can_discard) {
            this.discardBtn.disabled = true;
            this.discardBtn.classList.add('disabled');
        } else {
            this.discardBtn.disabled = false;
            this.discardBtn.classList.remove('disabled');
        }

        // Show/hide skip flip button (only when flip is optional in endgame mode)
        if (this.waitingForFlip && this.flipIsOptional) {
            this.skipFlipBtn.classList.remove('hidden');
        } else {
            this.skipFlipBtn.classList.add('hidden');
        }

        // Show/hide knock early button (when knock_early rule is enabled)
        // Conditions: rule enabled, my turn, no drawn card, have 1-2 face-down cards
        const canKnockEarly = this.gameState.knock_early &&
                              this.isMyTurn() &&
                              !this.drawnCard &&
                              !this.gameState.has_drawn_card &&
                              !this.gameState.waiting_for_initial_flip;
        if (canKnockEarly) {
            // Count face-down cards for current player
            const myData = this.gameState.players.find(p => p.id === this.playerId);
            const faceDownCount = myData ? myData.cards.filter(c => !c.face_up).length : 0;
            if (faceDownCount >= 1 && faceDownCount <= 2) {
                this.knockEarlyBtn.classList.remove('hidden');
            } else {
                this.knockEarlyBtn.classList.add('hidden');
            }
        } else {
            this.knockEarlyBtn.classList.add('hidden');
        }

        // Update scoreboard panel
        this.updateScorePanel();

        // Initialize anime.js hover listeners on newly created cards
        if (window.cardAnimations) {
            window.cardAnimations.initHoverListeners(this.playerCards);
            window.cardAnimations.initHoverListeners(this.opponentsRow);
        }
    }

    updateScorePanel() {
        if (!this.gameState) return;

        // Update standings (left panel)
        this.updateStandings();

        // Skip score table update during round_over/game_over - showScoreboard handles these
        if (this.gameState.phase === 'round_over' || this.gameState.phase === 'game_over') {
            return;
        }

        // Update score table (right panel)
        this.scoreTable.innerHTML = '';

        this.gameState.players.forEach(player => {
            const tr = document.createElement('tr');

            // Highlight current player (but not during round/game over)
            const isPlaying = this.gameState.phase !== 'round_over' && this.gameState.phase !== 'game_over';
            if (isPlaying && player.id === this.gameState.current_player_id) {
                tr.classList.add('current-player');
            }

            // Truncate long names
            const displayName = player.name.length > 12
                ? player.name.substring(0, 11) + '…'
                : player.name;

            const roundScore = player.score !== null ? player.score : '-';
            const roundsWon = player.rounds_won || 0;

            tr.innerHTML = `
                <td>${displayName}</td>
                <td>${roundScore}</td>
                <td>${player.total_score}</td>
                <td>${roundsWon}</td>
            `;
            this.scoreTable.appendChild(tr);
        });
    }

    updateStandings() {
        if (!this.gameState || !this.standingsList) return;

        // Sort by total points (lowest wins) - top 4
        const byPoints = [...this.gameState.players].sort((a, b) => a.total_score - b.total_score).slice(0, 4);
        // Sort by holes won (most wins) - top 4
        const byHoles = [...this.gameState.players].sort((a, b) => b.rounds_won - a.rounds_won).slice(0, 4);

        // Build points ranking
        let pointsRank = 0;
        let prevPoints = null;
        const pointsHtml = byPoints.map((p, i) => {
            if (p.total_score !== prevPoints) {
                pointsRank = i;
                prevPoints = p.total_score;
            }
            const medal = pointsRank === 0 ? '🥇' : pointsRank === 1 ? '🥈' : pointsRank === 2 ? '🥉' : '4.';
            const name = p.name.length > 8 ? p.name.substring(0, 7) + '…' : p.name;
            return `<div class="rank-row ${pointsRank === 0 ? 'leader' : ''}"><span class="rank-pos">${medal}</span><span class="rank-name">${name}</span><span class="rank-val">${p.total_score} pts</span></div>`;
        }).join('');

        // Build holes won ranking
        let holesRank = 0;
        let prevHoles = null;
        const holesHtml = byHoles.map((p, i) => {
            if (p.rounds_won !== prevHoles) {
                holesRank = i;
                prevHoles = p.rounds_won;
            }
            const medal = p.rounds_won === 0 ? '-' :
                          holesRank === 0 ? '🥇' : holesRank === 1 ? '🥈' : holesRank === 2 ? '🥉' : '4.';
            const name = p.name.length > 8 ? p.name.substring(0, 7) + '…' : p.name;
            return `<div class="rank-row ${holesRank === 0 && p.rounds_won > 0 ? 'leader' : ''}"><span class="rank-pos">${medal}</span><span class="rank-name">${name}</span><span class="rank-val">${p.rounds_won} wins</span></div>`;
        }).join('');

        this.standingsList.innerHTML = `
            <div class="standings-section">
                <div class="standings-title">By Score</div>
                ${pointsHtml}
            </div>
            <div class="standings-section">
                <div class="standings-title">By Holes</div>
                ${holesHtml}
            </div>
        `;
    }

    renderCard(card, clickable, selected) {
        let classes = 'card';
        let content = '';

        if (card.face_up) {
            classes += ' card-front';
            if (card.rank === '★') {
                classes += ' joker';
            } else if (this.isRedSuit(card.suit)) {
                classes += ' red';
            } else {
                classes += ' black';
            }
            content = this.renderCardContent(card);
        } else {
            classes += ' card-back';
            // Apply deck color based on card's deck_id
            if (this.gameState?.deck_colors) {
                const deckId = card.deck_id || 0;
                const color = this.gameState.deck_colors[deckId] || this.gameState.deck_colors[0];
                if (color) classes += ` back-${color}`;
            }
        }

        if (clickable) classes += ' clickable';
        if (selected) classes += ' selected';

        return `<div class="${classes}">${content}</div>`;
    }

    showScoreboard(scores, isFinal, rankings) {
        this.scoreTable.innerHTML = '';

        // Clear the final turn badge and status message
        this.finalTurnBadge.classList.add('hidden');
        if (isFinal) {
            this.setStatus('Game Over!');
        } else {
            this.setStatus('Hole complete');
        }

        // Find round winner(s) - lowest round score (not total)
        const roundScores = scores.map(s => s.score);
        const minRoundScore = Math.min(...roundScores);
        this.roundWinnerNames = new Set(
            scores.filter(s => s.score === minRoundScore).map(s => s.name)
        );

        // Re-render to show winner highlights
        this.renderGame();

        const minScore = Math.min(...scores.map(s => s.total || s.score || 0));

        scores.forEach(score => {
            const tr = document.createElement('tr');
            const total = score.total !== undefined ? score.total : score.score;
            const roundScore = score.score !== undefined ? score.score : '-';
            const roundsWon = score.rounds_won || 0;

            // Truncate long names
            const displayName = score.name.length > 12
                ? score.name.substring(0, 11) + '…'
                : score.name;

            if (total === minScore) {
                tr.classList.add('winner');
            }

            tr.innerHTML = `
                <td>${displayName}</td>
                <td>${roundScore}</td>
                <td>${total}</td>
                <td>${roundsWon}</td>
            `;
            this.scoreTable.appendChild(tr);
        });

        // Show rankings announcement only for final results
        const existingAnnouncement = document.getElementById('rankings-announcement');
        if (existingAnnouncement) existingAnnouncement.remove();

        if (isFinal) {
            // Show big final results modal instead of side panel stuff
            this.showFinalResultsModal(rankings, scores);
            return;
        }

        // Show game buttons
        this.gameButtons.classList.remove('hidden');
        this.newGameBtn.classList.add('hidden');
        this.nextRoundBtn.classList.remove('hidden');

        // Start countdown for next hole
        this.startNextHoleCountdown();
    }

    startNextHoleCountdown() {
        // Clear any existing countdown
        if (this.nextHoleCountdownInterval) {
            clearInterval(this.nextHoleCountdownInterval);
        }

        const COUNTDOWN_SECONDS = 15;
        let remaining = COUNTDOWN_SECONDS;

        const updateButton = () => {
            if (this.isHost) {
                this.nextRoundBtn.textContent = `Next Hole (${remaining}s)`;
                this.nextRoundBtn.disabled = false;
            } else {
                this.nextRoundBtn.textContent = `Next hole in ${remaining}s...`;
                this.nextRoundBtn.disabled = true;
                this.nextRoundBtn.classList.add('waiting');
            }
        };

        updateButton();

        this.nextHoleCountdownInterval = setInterval(() => {
            remaining--;

            if (remaining <= 0) {
                clearInterval(this.nextHoleCountdownInterval);
                this.nextHoleCountdownInterval = null;

                // Auto-advance if host
                if (this.isHost) {
                    this.nextRound();
                } else {
                    this.nextRoundBtn.textContent = 'Waiting for host...';
                }
            } else {
                updateButton();
            }
        }, 1000);
    }

    clearNextHoleCountdown() {
        if (this.nextHoleCountdownInterval) {
            clearInterval(this.nextHoleCountdownInterval);
            this.nextHoleCountdownInterval = null;
        }
    }

    showRankingsAnnouncement(rankings, isFinal) {
        // Remove existing announcement if any
        const existing = document.getElementById('rankings-announcement');
        if (existing) existing.remove();
        const existingVictory = document.getElementById('double-victory-banner');
        if (existingVictory) existingVictory.remove();

        if (!rankings) return;

        const announcement = document.createElement('div');
        announcement.id = 'rankings-announcement';
        announcement.className = 'rankings-announcement';

        const title = isFinal ? 'Final Results' : 'Current Standings';

        // Check for double victory (same player leads both categories) - only at game end
        const pointsLeader = rankings.by_points[0];
        const holesLeader = rankings.by_holes_won[0];
        const isDoubleVictory = isFinal && pointsLeader && holesLeader &&
            pointsLeader.name === holesLeader.name &&
            holesLeader.rounds_won > 0;

        // Build points ranking (lowest wins) with tie handling
        let pointsRank = 0;
        let prevPoints = null;
        const pointsHtml = rankings.by_points.map((p, i) => {
            if (p.total !== prevPoints) {
                pointsRank = i;
                prevPoints = p.total;
            }
            const medal = pointsRank === 0 ? '🥇' : pointsRank === 1 ? '🥈' : pointsRank === 2 ? '🥉' : `${pointsRank + 1}.`;
            const name = p.name.length > 12 ? p.name.substring(0, 11) + '…' : p.name;
            return `<div class="rank-row ${pointsRank === 0 ? 'leader' : ''}"><span class="rank-pos">${medal}</span><span class="rank-name">${name}</span><span class="rank-val">${p.total} pts</span></div>`;
        }).join('');

        // Build holes won ranking (most wins) with tie handling
        let holesRank = 0;
        let prevHoles = null;
        const holesHtml = rankings.by_holes_won.map((p, i) => {
            if (p.rounds_won !== prevHoles) {
                holesRank = i;
                prevHoles = p.rounds_won;
            }
            // No medal for 0 wins
            const medal = p.rounds_won === 0 ? '-' :
                          holesRank === 0 ? '🥇' : holesRank === 1 ? '🥈' : holesRank === 2 ? '🥉' : `${holesRank + 1}.`;
            const name = p.name.length > 12 ? p.name.substring(0, 11) + '…' : p.name;
            return `<div class="rank-row ${holesRank === 0 && p.rounds_won > 0 ? 'leader' : ''}"><span class="rank-pos">${medal}</span><span class="rank-name">${name}</span><span class="rank-val">${p.rounds_won} wins</span></div>`;
        }).join('');

        // If double victory, show banner above the left panel (standings)
        if (isDoubleVictory) {
            const victoryBanner = document.createElement('div');
            victoryBanner.id = 'double-victory-banner';
            victoryBanner.className = 'double-victory';
            victoryBanner.textContent = `DOUBLE VICTORY! ${pointsLeader.name}`;
            const standingsPanel = document.getElementById('standings-panel');
            if (standingsPanel) {
                standingsPanel.insertBefore(victoryBanner, standingsPanel.firstChild);
            }
        }

        announcement.innerHTML = `
            <h3>${title}</h3>
            <div class="rankings-columns">
                <div class="ranking-section">
                    <h4>Points (Low Wins)</h4>
                    ${pointsHtml}
                </div>
                <div class="ranking-section">
                    <h4>Holes Won</h4>
                    ${holesHtml}
                </div>
            </div>
        `;

        // Insert before the scoreboard
        this.scoreboard.insertBefore(announcement, this.scoreboard.firstChild);
    }

    showFinalResultsModal(rankings, scores) {
        // Hide side panels
        const standingsPanel = document.getElementById('standings-panel');
        const scoreboard = document.getElementById('scoreboard');
        if (standingsPanel) standingsPanel.classList.add('hidden');
        if (scoreboard) scoreboard.classList.add('hidden');

        // Remove existing modal if any
        const existing = document.getElementById('final-results-modal');
        if (existing) existing.remove();

        // Determine winners
        const pointsLeader = rankings.by_points[0];
        const holesLeader = rankings.by_holes_won[0];
        const isDoubleVictory = pointsLeader && holesLeader &&
            pointsLeader.name === holesLeader.name &&
            holesLeader.rounds_won > 0;

        // Build points ranking
        let pointsRank = 0;
        let prevPoints = null;
        const pointsHtml = rankings.by_points.map((p, i) => {
            if (p.total !== prevPoints) {
                pointsRank = i;
                prevPoints = p.total;
            }
            const medal = pointsRank === 0 ? '🥇' : pointsRank === 1 ? '🥈' : pointsRank === 2 ? '🥉' : `${pointsRank + 1}.`;
            return `<div class="final-rank-row ${pointsRank === 0 ? 'winner' : ''}"><span class="rank-pos">${medal}</span><span class="rank-name">${p.name}</span><span class="rank-val">${p.total} pts</span></div>`;
        }).join('');

        // Build holes ranking
        let holesRank = 0;
        let prevHoles = null;
        const holesHtml = rankings.by_holes_won.map((p, i) => {
            if (p.rounds_won !== prevHoles) {
                holesRank = i;
                prevHoles = p.rounds_won;
            }
            const medal = p.rounds_won === 0 ? '-' :
                          holesRank === 0 ? '🥇' : holesRank === 1 ? '🥈' : holesRank === 2 ? '🥉' : `${holesRank + 1}.`;
            return `<div class="final-rank-row ${holesRank === 0 && p.rounds_won > 0 ? 'winner' : ''}"><span class="rank-pos">${medal}</span><span class="rank-name">${p.name}</span><span class="rank-val">${p.rounds_won} wins</span></div>`;
        }).join('');

        // Build share text
        const shareText = this.buildShareText(rankings, isDoubleVictory);

        // Create modal
        const modal = document.createElement('div');
        modal.id = 'final-results-modal';
        modal.className = 'final-results-modal';
        modal.innerHTML = `
            <div class="final-results-content">
                <h2>🏌️ Final Results</h2>
                ${isDoubleVictory ? `<div class="double-victory-banner">🏆 DOUBLE VICTORY: ${pointsLeader.name} 🏆</div>` : ''}
                <div class="final-rankings">
                    <div class="final-ranking-section">
                        <h3>By Points (Low Wins)</h3>
                        ${pointsHtml}
                    </div>
                    <div class="final-ranking-section">
                        <h3>By Holes Won</h3>
                        ${holesHtml}
                    </div>
                </div>
                <div class="final-actions">
                    <button class="btn btn-primary" id="share-results-btn">📋 Copy Results</button>
                    <button class="btn btn-secondary" id="close-results-btn">New Game</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Bind button events
        document.getElementById('share-results-btn').addEventListener('click', () => {
            navigator.clipboard.writeText(shareText).then(() => {
                const btn = document.getElementById('share-results-btn');
                btn.textContent = '✓ Copied!';
                const copyDelay = window.TIMING?.feedback?.copyConfirm || 2000;
                setTimeout(() => btn.textContent = '📋 Copy Results', copyDelay);
            });
        });

        document.getElementById('close-results-btn').addEventListener('click', () => {
            modal.remove();
            this.leaveRoom();
        });
    }

    buildShareText(rankings, isDoubleVictory) {
        let text = '🏌️ Golf Card Game Results\n';
        text += '═══════════════════════\n\n';

        if (isDoubleVictory) {
            text += `🏆 DOUBLE VICTORY: ${rankings.by_points[0].name}!\n\n`;
        }

        text += '📊 By Points (Low Wins):\n';
        rankings.by_points.forEach((p, i) => {
            const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}.`;
            text += `${medal} ${p.name}: ${p.total} pts\n`;
        });

        text += '\n⛳ By Holes Won:\n';
        rankings.by_holes_won.forEach((p, i) => {
            const medal = p.rounds_won === 0 ? '-' : i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}.`;
            text += `${medal} ${p.name}: ${p.rounds_won} wins\n`;
        });

        text += '\nPlayed at golf.game';
        return text;
    }
}

// Initialize game when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.game = new GolfGame();
    window.auth = new AuthManager(window.game);
});


// ===========================================
// AUTH MANAGER
// ===========================================

class AuthManager {
    constructor(game) {
        this.game = game;
        this.token = localStorage.getItem('authToken');
        this.user = JSON.parse(localStorage.getItem('authUser') || 'null');

        this.initElements();
        this.bindEvents();
        this.updateUI();
    }

    initElements() {
        this.authBar = document.getElementById('auth-bar');
        this.authUsername = document.getElementById('auth-username');
        this.logoutBtn = document.getElementById('auth-logout-btn');
        this.authButtons = document.getElementById('auth-buttons');
        this.loginBtn = document.getElementById('login-btn');
        this.signupBtn = document.getElementById('signup-btn');
        this.modal = document.getElementById('auth-modal');
        this.modalClose = document.getElementById('auth-modal-close');
        this.loginFormContainer = document.getElementById('login-form-container');
        this.loginForm = document.getElementById('login-form');
        this.loginUsername = document.getElementById('login-username');
        this.loginPassword = document.getElementById('login-password');
        this.loginError = document.getElementById('login-error');
        this.signupFormContainer = document.getElementById('signup-form-container');
        this.signupForm = document.getElementById('signup-form');
        this.signupUsername = document.getElementById('signup-username');
        this.signupEmail = document.getElementById('signup-email');
        this.signupPassword = document.getElementById('signup-password');
        this.signupError = document.getElementById('signup-error');
        this.showSignupLink = document.getElementById('show-signup');
        this.showLoginLink = document.getElementById('show-login');
    }

    bindEvents() {
        this.loginBtn?.addEventListener('click', () => this.showModal('login'));
        this.signupBtn?.addEventListener('click', () => this.showModal('signup'));
        this.modalClose?.addEventListener('click', () => this.hideModal());
        this.modal?.addEventListener('click', (e) => {
            if (e.target === this.modal) this.hideModal();
        });
        this.showSignupLink?.addEventListener('click', (e) => {
            e.preventDefault();
            this.showForm('signup');
        });
        this.showLoginLink?.addEventListener('click', (e) => {
            e.preventDefault();
            this.showForm('login');
        });
        this.loginForm?.addEventListener('submit', (e) => this.handleLogin(e));
        this.signupForm?.addEventListener('submit', (e) => this.handleSignup(e));
        this.logoutBtn?.addEventListener('click', () => this.logout());
    }

    showModal(form = 'login') {
        this.modal.classList.remove('hidden');
        this.showForm(form);
        this.clearErrors();
    }

    hideModal() {
        this.modal.classList.add('hidden');
        this.clearForms();
    }

    showForm(form) {
        if (form === 'login') {
            this.loginFormContainer.classList.remove('hidden');
            this.signupFormContainer.classList.add('hidden');
            this.loginUsername.focus();
        } else {
            this.loginFormContainer.classList.add('hidden');
            this.signupFormContainer.classList.remove('hidden');
            this.signupUsername.focus();
        }
    }

    clearForms() {
        this.loginForm.reset();
        this.signupForm.reset();
        this.clearErrors();
    }

    clearErrors() {
        this.loginError.textContent = '';
        this.signupError.textContent = '';
    }

    async handleLogin(e) {
        e.preventDefault();
        this.clearErrors();

        const username = this.loginUsername.value.trim();
        const password = this.loginPassword.value;

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            const data = await response.json();

            if (!response.ok) {
                this.loginError.textContent = data.detail || 'Login failed';
                return;
            }

            this.setAuth(data.token, data.user);
            this.hideModal();

            if (data.user.username && this.game.playerNameInput) {
                this.game.playerNameInput.value = data.user.username;
            }
        } catch (err) {
            this.loginError.textContent = 'Connection error';
        }
    }

    async handleSignup(e) {
        e.preventDefault();
        this.clearErrors();

        const username = this.signupUsername.value.trim();
        const email = this.signupEmail.value.trim() || null;
        const password = this.signupPassword.value;

        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, email, password }),
            });

            const data = await response.json();

            if (!response.ok) {
                this.signupError.textContent = data.detail || 'Signup failed';
                return;
            }

            this.setAuth(data.token, data.user);
            this.hideModal();

            if (data.user.username && this.game.playerNameInput) {
                this.game.playerNameInput.value = data.user.username;
            }
        } catch (err) {
            this.signupError.textContent = 'Connection error';
        }
    }

    setAuth(token, user) {
        this.token = token;
        this.user = user;
        localStorage.setItem('authToken', token);
        localStorage.setItem('authUser', JSON.stringify(user));
        this.updateUI();
    }

    logout() {
        this.token = null;
        this.user = null;
        localStorage.removeItem('authToken');
        localStorage.removeItem('authUser');
        this.updateUI();
    }

    updateUI() {
        if (this.user) {
            this.authBar?.classList.remove('hidden');
            this.authButtons?.classList.add('hidden');
            if (this.authUsername) {
                this.authUsername.textContent = this.user.username;
            }
            if (this.game.playerNameInput && !this.game.playerNameInput.value) {
                this.game.playerNameInput.value = this.user.username;
            }
        } else {
            this.authBar?.classList.add('hidden');
            this.authButtons?.classList.remove('hidden');
        }
    }
}
