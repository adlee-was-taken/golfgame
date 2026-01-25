// Golf Card Game - Client Application

class GolfGame {
    constructor() {
        this.ws = null;
        this.playerId = null;
        this.roomCode = null;
        this.isHost = false;
        this.gameState = null;
        this.drawnCard = null;
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
        this.pendingGameState = null;

        // Track cards we've locally flipped (for immediate feedback during selection)
        this.locallyFlippedCards = new Set();

        // Animation lock - prevent overlapping animations on same elements
        this.animatingPositions = new Set();

        // Track round winners for visual highlight
        this.roundWinnerNames = new Set();

        this.initElements();
        this.initAudio();
        this.bindEvents();
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
            oscillator.frequency.setValueAtTime(800, ctx.currentTime);
            oscillator.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.08);
            gainNode.gain.setValueAtTime(0.08, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.08);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.08);
        } else if (type === 'success') {
            oscillator.frequency.setValueAtTime(400, ctx.currentTime);
            oscillator.frequency.setValueAtTime(600, ctx.currentTime + 0.1);
            gainNode.gain.setValueAtTime(0.1, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.2);
        } else if (type === 'flip') {
            // Sharp quick click for card flips
            oscillator.type = 'square';
            oscillator.frequency.setValueAtTime(1800, ctx.currentTime);
            oscillator.frequency.exponentialRampToValueAtTime(600, ctx.currentTime + 0.02);
            gainNode.gain.setValueAtTime(0.12, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.025);
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.025);
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
        this.playersList = document.getElementById('players-list');
        this.hostSettings = document.getElementById('host-settings');
        this.waitingMessage = document.getElementById('waiting-message');
        this.numDecksSelect = document.getElementById('num-decks');
        this.deckRecommendation = document.getElementById('deck-recommendation');
        this.numRoundsSelect = document.getElementById('num-rounds');
        this.initialFlipsSelect = document.getElementById('initial-flips');
        this.flipOnDiscardCheckbox = document.getElementById('flip-on-discard');
        this.knockPenaltyCheckbox = document.getElementById('knock-penalty');
        // House Rules - Point Modifiers
        this.superKingsCheckbox = document.getElementById('super-kings');
        this.tenPennyCheckbox = document.getElementById('ten-penny');
        // House Rules - Bonuses/Penalties
        this.knockBonusCheckbox = document.getElementById('knock-bonus');
        this.underdogBonusCheckbox = document.getElementById('underdog-bonus');
        this.tiedShameCheckbox = document.getElementById('tied-shame');
        this.blackjackCheckbox = document.getElementById('blackjack');
        this.wolfpackCheckbox = document.getElementById('wolfpack');
        this.startGameBtn = document.getElementById('start-game-btn');
        this.leaveRoomBtn = document.getElementById('leave-room-btn');
        this.addCpuBtn = document.getElementById('add-cpu-btn');
        this.removeCpuBtn = document.getElementById('remove-cpu-btn');
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
        this.deck = document.getElementById('deck');
        this.discard = document.getElementById('discard');
        this.discardContent = document.getElementById('discard-content');
        this.discardBtn = document.getElementById('discard-btn');
        this.playerCards = document.getElementById('player-cards');
        this.playerArea = this.playerCards.closest('.player-area');
        this.swapAnimation = document.getElementById('swap-animation');
        this.swapCardFromHand = document.getElementById('swap-card-from-hand');
        this.scoreboard = document.getElementById('scoreboard');
        this.scoreTable = document.getElementById('score-table').querySelector('tbody');
        this.standingsList = document.getElementById('standings-list');
        this.gameButtons = document.getElementById('game-buttons');
        this.nextRoundBtn = document.getElementById('next-round-btn');
        this.newGameBtn = document.getElementById('new-game-btn');
        this.leaveGameBtn = document.getElementById('leave-game-btn');
        this.activeRulesBar = document.getElementById('active-rules-bar');
        this.activeRulesList = document.getElementById('active-rules-list');
    }

    bindEvents() {
        this.createRoomBtn.addEventListener('click', () => { this.playSound('click'); this.createRoom(); });
        this.joinRoomBtn.addEventListener('click', () => { this.playSound('click'); this.joinRoom(); });
        this.startGameBtn.addEventListener('click', () => { this.playSound('success'); this.startGame(); });
        this.leaveRoomBtn.addEventListener('click', () => { this.playSound('click'); this.leaveRoom(); });
        this.deck.addEventListener('click', () => { this.playSound('card'); this.drawFromDeck(); });
        this.discard.addEventListener('click', () => { this.playSound('card'); this.drawFromDiscard(); });
        this.discardBtn.addEventListener('click', () => { this.playSound('card'); this.discardDrawn(); });
        this.nextRoundBtn.addEventListener('click', () => { this.playSound('click'); this.nextRound(); });
        this.newGameBtn.addEventListener('click', () => { this.playSound('click'); this.newGame(); });
        this.addCpuBtn.addEventListener('click', () => { this.playSound('click'); this.showCpuSelect(); });
        this.removeCpuBtn.addEventListener('click', () => { this.playSound('click'); this.removeCpu(); });
        this.cancelCpuBtn.addEventListener('click', () => { this.playSound('click'); this.hideCpuSelect(); });
        this.addSelectedCpusBtn.addEventListener('click', () => { this.playSound('success'); this.addSelectedCpus(); });
        this.muteBtn.addEventListener('click', () => this.toggleSound());
        this.leaveGameBtn.addEventListener('click', () => { this.playSound('click'); this.leaveGame(); });

        // Copy room code to clipboard
        this.copyRoomCodeBtn.addEventListener('click', () => {
            this.playSound('click');
            this.copyRoomCode();
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

        // Update deck recommendation when deck selection changes
        this.numDecksSelect.addEventListener('change', () => {
            const playerCount = this.currentPlayers ? this.currentPlayers.length : 0;
            this.updateDeckRecommendation(playerCount);
        });

        // Toggle scoreboard collapse on mobile
        const scoreboardTitle = this.scoreboard.querySelector('h4');
        if (scoreboardTitle) {
            scoreboardTitle.addEventListener('click', () => {
                if (window.innerWidth <= 700) {
                    this.scoreboard.classList.toggle('collapsed');
                }
            });
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
                // Reset tracking for new round
                this.locallyFlippedCards = new Set();
                this.animatingPositions = new Set();
                this.playSound('shuffle');
                this.showGameScreen();
                this.renderGame();
                break;

            case 'game_state':
                // State updates are instant, animations are fire-and-forget
                // Exception: Local player's swap animation defers state until complete

                // If local swap animation is running, defer this state update
                if (this.swapAnimationInProgress) {
                    this.updateSwapAnimation(data.game_state.discard_top);
                    this.pendingGameState = data.game_state;
                    break;
                }

                const oldState = this.gameState;
                const newState = data.game_state;

                // Update state FIRST (always)
                this.gameState = newState;

                // Clear local flip tracking if server confirmed our flips
                if (!newState.waiting_for_initial_flip && oldState?.waiting_for_initial_flip) {
                    this.locallyFlippedCards = new Set();
                }

                // Detect and fire animations (non-blocking, errors shouldn't break game)
                try {
                    this.triggerAnimationsForStateChange(oldState, newState);
                } catch (e) {
                    console.error('Animation error:', e);
                }

                // Render immediately with new state
                this.renderGame();
                break;

            case 'your_turn':
                this.showToast('Your turn! Draw a card', 'your-turn');
                break;

            case 'card_drawn':
                this.drawnCard = data.card;
                this.showDrawnCard();
                this.showToast('Swap with a card or discard', '', 3000);
                break;

            case 'can_flip':
                this.waitingForFlip = true;
                this.showToast('Flip a face-down card', '', 3000);
                this.renderGame();
                break;

            case 'round_over':
                this.showScoreboard(data.scores, false, data.rankings);
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

        navigator.clipboard.writeText(this.roomCode).then(() => {
            // Show brief visual feedback
            const originalText = this.copyRoomCodeBtn.textContent;
            this.copyRoomCodeBtn.textContent = '✓';
            setTimeout(() => {
                this.copyRoomCodeBtn.textContent = originalText;
            }, 1500);
        }).catch(err => {
            console.error('Failed to copy room code:', err);
            // Fallback: select the text for manual copy
            const range = document.createRange();
            range.selectNode(this.displayRoomCode);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
        });
    }

    startGame() {
        const decks = parseInt(this.numDecksSelect.value);
        const rounds = parseInt(this.numRoundsSelect.value);
        const initial_flips = parseInt(this.initialFlipsSelect.value);

        // Standard options
        const flip_on_discard = this.flipOnDiscardCheckbox.checked;
        const knock_penalty = this.knockPenaltyCheckbox.checked;

        // Joker mode (radio buttons)
        const joker_mode = document.querySelector('input[name="joker-mode"]:checked').value;
        const use_jokers = joker_mode !== 'none';
        const lucky_swing = joker_mode === 'lucky-swing';
        const eagle_eye = joker_mode === 'eagle-eye';

        // House Rules - Point Modifiers
        const super_kings = this.superKingsCheckbox.checked;
        const ten_penny = this.tenPennyCheckbox.checked;

        // House Rules - Bonuses/Penalties
        const knock_bonus = this.knockBonusCheckbox.checked;
        const underdog_bonus = this.underdogBonusCheckbox.checked;
        const tied_shame = this.tiedShameCheckbox.checked;
        const blackjack = this.blackjackCheckbox.checked;
        const wolfpack = this.wolfpackCheckbox.checked;

        this.send({
            type: 'start_game',
            decks,
            rounds,
            initial_flips,
            flip_on_discard,
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
            wolfpack
        });
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
        if (!this.isMyTurn() || this.drawnCard || this.gameState.has_drawn_card) return;
        if (this.gameState.waiting_for_initial_flip) return;
        this.send({ type: 'draw', source: 'deck' });
    }

    drawFromDiscard() {
        if (!this.isMyTurn() || this.drawnCard || this.gameState.has_drawn_card) return;
        if (this.gameState.waiting_for_initial_flip) return;
        if (!this.gameState.discard_top) return;
        this.send({ type: 'draw', source: 'discard' });
    }

    discardDrawn() {
        if (!this.drawnCard) return;
        this.send({ type: 'discard' });
        this.drawnCard = null;
        this.hideDrawnCard();
        this.hideToast();
    }

    swapCard(position) {
        if (!this.drawnCard) return;
        this.send({ type: 'swap', position });
        this.drawnCard = null;
        this.hideDrawnCard();
    }

    // Animate player swapping drawn card with a card in their hand
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

        // Get positions
        const handRect = handCardEl.getBoundingClientRect();
        const discardRect = this.discard.getBoundingClientRect();

        // Set up the animated card at hand position
        const swapCard = this.swapCardFromHand;
        const swapCardFront = swapCard.querySelector('.swap-card-front');
        const swapCardInner = swapCard.querySelector('.swap-card-inner');

        // Position at the hand card location
        swapCard.style.left = handRect.left + 'px';
        swapCard.style.top = handRect.top + 'px';
        swapCard.style.width = handRect.width + 'px';
        swapCard.style.height = handRect.height + 'px';

        // Reset state
        swapCard.classList.remove('flipping', 'moving');
        swapCardFront.innerHTML = '';
        swapCardFront.className = 'swap-card-front';

        if (isAlreadyFaceUp && card) {
            // FACE-UP CARD: Show card content immediately, then slide to discard
            if (card.rank === '★') {
                swapCardFront.classList.add('joker');
                const jokerIcon = card.suit === 'hearts' ? '🐉' : '👹';
                swapCardFront.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
            } else {
                swapCardFront.classList.add(card.suit === 'hearts' || card.suit === 'diamonds' ? 'red' : 'black');
                const suitSymbol = { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' }[card.suit];
                swapCardFront.innerHTML = `${card.rank}<br>${suitSymbol}`;
            }
            swapCard.classList.add('flipping'); // Show front immediately

            // Hide the actual hand card and discard
            handCardEl.classList.add('swap-out');
            this.discard.classList.add('swap-to-hand');
            this.swapAnimation.classList.remove('hidden');

            // Mark animating
            this.swapAnimationInProgress = true;
            this.swapAnimationCardEl = handCardEl;
            this.swapAnimationContentSet = true;

            // Send swap
            this.send({ type: 'swap', position });
            this.drawnCard = null;

            // Slide to discard
            setTimeout(() => {
                swapCard.classList.add('moving');
                swapCard.style.left = discardRect.left + 'px';
                swapCard.style.top = discardRect.top + 'px';
            }, 50);

            // Complete
            setTimeout(() => {
                this.swapAnimation.classList.add('hidden');
                swapCard.classList.remove('flipping', 'moving');
                handCardEl.classList.remove('swap-out');
                this.discard.classList.remove('swap-to-hand');
                this.swapAnimationInProgress = false;
                this.hideDrawnCard();

                if (this.pendingGameState) {
                    this.gameState = this.pendingGameState;
                    this.pendingGameState = null;
                    this.renderGame();
                }
            }, 500);
        } else {
            // FACE-DOWN CARD: Just slide card-back to discard (no flip mid-air)
            // The new card will appear instantly when state updates

            // Don't use overlay for face-down - just send swap and let state handle it
            // This avoids the clunky "flip to empty front" issue
            this.swapAnimationInProgress = true;
            this.swapAnimationCardEl = handCardEl;
            this.swapAnimationContentSet = false;

            // Send swap
            this.send({ type: 'swap', position });
            this.drawnCard = null;

            // Brief visual feedback - hide drawn card area
            this.discard.classList.add('swap-to-hand');
            handCardEl.classList.add('swap-out');

            // Short timeout then let state update handle it
            setTimeout(() => {
                this.discard.classList.remove('swap-to-hand');
                handCardEl.classList.remove('swap-out');
                this.swapAnimationInProgress = false;
                this.hideDrawnCard();

                if (this.pendingGameState) {
                    this.gameState = this.pendingGameState;
                    this.pendingGameState = null;
                    this.renderGame();
                }
            }, 300);
        }
    }

    // Update the animated card with actual card content when server responds
    updateSwapAnimation(card) {
        if (!this.swapAnimationFront || !card) return;

        // Skip if we already set the content (face-up card swap)
        if (this.swapAnimationContentSet) return;

        // Set card color class
        this.swapAnimationFront.className = 'swap-card-front';
        if (card.rank === '★') {
            this.swapAnimationFront.classList.add('joker');
            const jokerIcon = card.suit === 'hearts' ? '🐉' : '👹';
            this.swapAnimationFront.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        } else {
            if (card.suit === 'hearts' || card.suit === 'diamonds') {
                this.swapAnimationFront.classList.add('red');
            } else {
                this.swapAnimationFront.classList.add('black');
            }
            this.swapAnimationFront.innerHTML = `${card.rank}<br>${this.getSuitSymbol(card.suit)}`;
        }
    }

    flipCard(position) {
        this.send({ type: 'flip_card', position });
        this.waitingForFlip = false;
    }

    // Fire-and-forget animation triggers based on state changes
    triggerAnimationsForStateChange(oldState, newState) {
        if (!oldState) return;

        // Check for discard pile changes
        const newDiscard = newState.discard_top;
        const oldDiscard = oldState.discard_top;
        const discardChanged = newDiscard && (!oldDiscard ||
            newDiscard.rank !== oldDiscard.rank ||
            newDiscard.suit !== oldDiscard.suit);

        const previousPlayerId = oldState.current_player_id;
        const wasOtherPlayer = previousPlayerId && previousPlayerId !== this.playerId;

        if (discardChanged && wasOtherPlayer) {
            // Check if the previous player actually SWAPPED (has a new face-up card)
            // vs just discarding the drawn card (no hand change)
            const oldPlayer = oldState.players.find(p => p.id === previousPlayerId);
            const newPlayer = newState.players.find(p => p.id === previousPlayerId);

            if (oldPlayer && newPlayer) {
                // Find the position that changed
                // Could be: face-down -> face-up (new reveal)
                // Or: different card at same position (replaced visible card)
                let swappedPosition = -1;
                for (let i = 0; i < 6; i++) {
                    const oldCard = oldPlayer.cards[i];
                    const newCard = newPlayer.cards[i];
                    const wasUp = oldCard?.face_up;
                    const isUp = newCard?.face_up;

                    // Case 1: face-down became face-up
                    if (!wasUp && isUp) {
                        swappedPosition = i;
                        break;
                    }
                    // Case 2: both face-up but different card (rank or suit changed)
                    if (wasUp && isUp && oldCard.rank && newCard.rank) {
                        if (oldCard.rank !== newCard.rank || oldCard.suit !== newCard.suit) {
                            swappedPosition = i;
                            break;
                        }
                    }
                }

                if (swappedPosition >= 0) {
                    // Player swapped - animate from the actual position that changed
                    this.fireSwapAnimation(previousPlayerId, newDiscard, swappedPosition);
                } else {
                    // Player drew and discarded without swapping
                    // Animate card going from deck area to discard
                    this.fireDiscardAnimation(newDiscard);
                }
            }
        }

        // Note: We don't separately animate card flips for swaps anymore
        // The swap animation handles showing the card at the correct position
    }

    // Fire animation for discard without swap (card goes deck -> discard)
    fireDiscardAnimation(discardCard) {
        const deckRect = this.deck.getBoundingClientRect();
        const discardRect = this.discard.getBoundingClientRect();
        const swapCard = this.swapCardFromHand;
        const swapCardFront = swapCard.querySelector('.swap-card-front');

        // Start at deck position
        swapCard.style.left = deckRect.left + 'px';
        swapCard.style.top = deckRect.top + 'px';
        swapCard.style.width = deckRect.width + 'px';
        swapCard.style.height = deckRect.height + 'px';
        swapCard.classList.remove('flipping', 'moving');

        // Set card content
        swapCardFront.className = 'swap-card-front';
        if (discardCard.rank === '★') {
            swapCardFront.classList.add('joker');
            const jokerIcon = discardCard.suit === 'hearts' ? '🐉' : '👹';
            swapCardFront.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        } else {
            swapCardFront.classList.add(discardCard.suit === 'hearts' || discardCard.suit === 'diamonds' ? 'red' : 'black');
            swapCardFront.innerHTML = `${discardCard.rank}<br>${this.getSuitSymbol(discardCard.suit)}`;
        }

        this.swapAnimation.classList.remove('hidden');

        // Flip to reveal card
        setTimeout(() => {
            swapCard.classList.add('flipping');
            this.playSound('flip');
        }, 50);

        // Move to discard
        setTimeout(() => {
            swapCard.classList.add('moving');
            swapCard.style.left = discardRect.left + 'px';
            swapCard.style.top = discardRect.top + 'px';
        }, 400);

        // Complete
        setTimeout(() => {
            this.swapAnimation.classList.add('hidden');
            swapCard.classList.remove('flipping', 'moving');
        }, 800);
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

    // Fire a swap animation (non-blocking)
    fireSwapAnimation(playerId, discardCard, position) {

        // Find source position - the actual card that was swapped
        const opponentAreas = this.opponentsRow.querySelectorAll('.opponent-area');
        let sourceRect = null;
        let sourceCardEl = null;
        let sourceRotation = 0;

        for (const area of opponentAreas) {
            const nameEl = area.querySelector('h4');
            const player = this.gameState?.players.find(p => p.id === playerId);
            if (nameEl && player && nameEl.textContent.includes(player.name)) {
                const cards = area.querySelectorAll('.card');
                if (cards.length > position && position >= 0) {
                    sourceCardEl = cards[position];
                    sourceRect = sourceCardEl.getBoundingClientRect();
                    // Get rotation from the opponent area (parent has the arch rotation)
                    sourceRotation = this.getElementRotation(area);
                }
                break;
            }
        }

        if (!sourceRect) {
            const discardRect = this.discard.getBoundingClientRect();
            sourceRect = { left: discardRect.left, top: discardRect.top - 100, width: discardRect.width, height: discardRect.height };
        }

        const discardRect = this.discard.getBoundingClientRect();
        const swapCard = this.swapCardFromHand;
        const swapCardFront = swapCard.querySelector('.swap-card-front');
        const swapCardInner = swapCard.querySelector('.swap-card-inner');

        swapCard.style.left = sourceRect.left + 'px';
        swapCard.style.top = sourceRect.top + 'px';
        swapCard.style.width = sourceRect.width + 'px';
        swapCard.style.height = sourceRect.height + 'px';
        swapCard.classList.remove('flipping', 'moving');

        // Apply source rotation to match the arch layout
        swapCard.style.transform = `rotate(${sourceRotation}deg)`;

        // Set card content
        swapCardFront.className = 'swap-card-front';
        if (discardCard.rank === '★') {
            swapCardFront.classList.add('joker');
            const jokerIcon = discardCard.suit === 'hearts' ? '🐉' : '👹';
            swapCardFront.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        } else {
            swapCardFront.classList.add(discardCard.suit === 'hearts' || discardCard.suit === 'diamonds' ? 'red' : 'black');
            swapCardFront.innerHTML = `${discardCard.rank}<br>${this.getSuitSymbol(discardCard.suit)}`;
        }

        if (sourceCardEl) sourceCardEl.classList.add('swap-out');
        this.swapAnimation.classList.remove('hidden');

        // Timing: flip takes ~400ms, then move takes ~400ms
        setTimeout(() => {
            swapCard.classList.add('flipping');
            this.playSound('flip');
        }, 50);
        setTimeout(() => {
            // Start move AFTER flip completes - also animate rotation back to 0
            swapCard.classList.add('moving');
            swapCard.style.left = discardRect.left + 'px';
            swapCard.style.top = discardRect.top + 'px';
            swapCard.style.transform = 'rotate(0deg)';
        }, 500);
        setTimeout(() => {
            this.swapAnimation.classList.add('hidden');
            swapCard.classList.remove('flipping', 'moving');
            swapCard.style.transform = '';
            if (sourceCardEl) sourceCardEl.classList.remove('swap-out');
        }, 1000);
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

        const cardRect = cardEl.getBoundingClientRect();
        const swapCard = this.swapCardFromHand;
        const swapCardFront = swapCard.querySelector('.swap-card-front');

        swapCard.style.left = cardRect.left + 'px';
        swapCard.style.top = cardRect.top + 'px';
        swapCard.style.width = cardRect.width + 'px';
        swapCard.style.height = cardRect.height + 'px';
        swapCard.classList.remove('flipping', 'moving');

        // Set card content
        swapCardFront.className = 'swap-card-front';
        if (cardData.rank === '★') {
            swapCardFront.classList.add('joker');
            const jokerIcon = cardData.suit === 'hearts' ? '🐉' : '👹';
            swapCardFront.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        } else {
            swapCardFront.classList.add(cardData.suit === 'hearts' || cardData.suit === 'diamonds' ? 'red' : 'black');
            const suitSymbol = { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' }[cardData.suit];
            swapCardFront.innerHTML = `${cardData.rank}<br>${suitSymbol}`;
        }

        cardEl.classList.add('swap-out');
        this.swapAnimation.classList.remove('hidden');

        setTimeout(() => {
            swapCard.classList.add('flipping');
            this.playSound('flip');
        }, 50);

        setTimeout(() => {
            this.swapAnimation.classList.add('hidden');
            swapCard.classList.remove('flipping');
            cardEl.classList.remove('swap-out');
            this.animatingPositions.delete(key);
        }, 450);
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

        const cardRect = cardEl.getBoundingClientRect();
        const swapCard = this.swapCardFromHand;
        const swapCardFront = swapCard.querySelector('.swap-card-front');

        swapCard.style.left = cardRect.left + 'px';
        swapCard.style.top = cardRect.top + 'px';
        swapCard.style.width = cardRect.width + 'px';
        swapCard.style.height = cardRect.height + 'px';
        swapCard.classList.remove('flipping', 'moving');

        // Apply rotation to match the arch layout
        swapCard.style.transform = `rotate(${sourceRotation}deg)`;

        // Set card content
        swapCardFront.className = 'swap-card-front';
        if (cardData.rank === '★') {
            swapCardFront.classList.add('joker');
            const jokerIcon = cardData.suit === 'hearts' ? '🐉' : '👹';
            swapCardFront.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        } else {
            swapCardFront.classList.add(cardData.suit === 'hearts' || cardData.suit === 'diamonds' ? 'red' : 'black');
            const suitSymbol = { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' }[cardData.suit];
            swapCardFront.innerHTML = `${cardData.rank}<br>${suitSymbol}`;
        }

        cardEl.classList.add('swap-out');
        this.swapAnimation.classList.remove('hidden');

        setTimeout(() => {
            swapCard.classList.add('flipping');
            this.playSound('flip');
        }, 50);

        setTimeout(() => {
            this.swapAnimation.classList.add('hidden');
            swapCard.classList.remove('flipping');
            swapCard.style.transform = '';
            cardEl.classList.remove('swap-out');
            this.animatingPositions.delete(key);
        }, 450);
    }

    handleCardClick(position) {
        const myData = this.getMyPlayerData();
        if (!myData) return;

        const card = myData.cards[position];

        // Initial flip phase
        if (this.gameState.waiting_for_initial_flip) {
            if (card.face_up) return;
            if (this.locallyFlippedCards.has(position)) return;

            const requiredFlips = this.gameState.initial_flips || 2;

            // Track locally and animate immediately
            this.locallyFlippedCards.add(position);
            this.selectedCards.push(position);

            // Fire flip animation (non-blocking)
            this.fireLocalFlipAnimation(position, card);

            // Re-render to show flipped state
            this.renderGame();

            if (this.selectedCards.length === requiredFlips) {
                this.send({ type: 'flip_initial', positions: this.selectedCards });
                this.selectedCards = [];
                this.hideToast();
            } else {
                const remaining = requiredFlips - this.selectedCards.length;
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
        screen.classList.add('active');
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
            this.waitingMessage.classList.add('hidden');
        } else {
            this.hostSettings.classList.add('hidden');
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
        if (rules.length === 0) {
            // Show "Standard Rules" when no variants selected
            this.activeRulesList.innerHTML = '<span class="rule-tag standard">Standard</span>';
        } else {
            this.activeRulesList.innerHTML = rules
                .map(rule => `<span class="rule-tag">${rule}</span>`)
                .join('');
        }
        this.activeRulesBar.classList.remove('hidden');
    }

    showError(message) {
        this.lobbyError.textContent = message;
    }

    updatePlayersList(players) {
        this.playersList.innerHTML = '';
        players.forEach(player => {
            const li = document.createElement('li');
            let badges = '';
            if (player.is_host) badges += '<span class="host-badge">HOST</span>';
            if (player.is_cpu) badges += '<span class="cpu-badge">CPU</span>';

            let nameDisplay = player.name;
            if (player.style) {
                nameDisplay += ` <span class="cpu-style">(${player.style})</span>`;
            }

            li.innerHTML = `
                <span>${nameDisplay}</span>
                <span>${badges}</span>
            `;
            if (player.id === this.playerId) {
                li.style.background = 'rgba(244, 164, 96, 0.3)';
            }
            this.playersList.appendChild(li);

            if (player.id === this.playerId && player.is_host) {
                this.isHost = true;
                this.hostSettings.classList.remove('hidden');
                this.waitingMessage.classList.add('hidden');
            }
        });

        // Auto-select 2 decks when reaching 4+ players (host only)
        const prevCount = this.currentPlayers ? this.currentPlayers.length : 0;
        if (this.isHost && prevCount < 4 && players.length >= 4) {
            this.numDecksSelect.value = '2';
        }

        // Update deck recommendation visibility
        this.updateDeckRecommendation(players.length);
    }

    updateDeckRecommendation(playerCount) {
        if (!this.isHost || !this.deckRecommendation) return;

        const decks = parseInt(this.numDecksSelect.value);
        // Show recommendation if 4+ players and only 1 deck selected
        if (playerCount >= 4 && decks < 2) {
            this.deckRecommendation.classList.remove('hidden');
        } else {
            this.deckRecommendation.classList.add('hidden');
        }
    }

    isMyTurn() {
        return this.gameState && this.gameState.current_player_id === this.playerId;
    }

    getMyPlayerData() {
        if (!this.gameState) return null;
        return this.gameState.players.find(p => p.id === this.playerId);
    }

    setStatus(message, type = '') {
        this.statusMessage.textContent = message;
        this.statusMessage.className = 'status-message' + (type ? ' ' + type : '');
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
            return;
        }

        const isFinalTurn = this.gameState.phase === 'final_turn';
        const currentPlayer = this.gameState.players.find(p => p.id === this.gameState.current_player_id);

        if (currentPlayer && currentPlayer.id !== this.playerId) {
            const prefix = isFinalTurn ? '⚡ Final turn: ' : '';
            this.setStatus(`${prefix}${currentPlayer.name}'s turn`);
        } else if (this.isMyTurn()) {
            const message = isFinalTurn
                ? '⚡ Final turn! Draw a card'
                : 'Your turn - draw a card';
            this.setStatus(message, 'your-turn');
        } else {
            this.setStatus('');
        }
    }

    showDrawnCard() {
        // Show drawn card in the discard pile position, highlighted
        const card = this.drawnCard;

        this.discard.className = 'card card-front holding';
        if (card.rank === '★') {
            this.discard.classList.add('joker');
        } else if (this.isRedSuit(card.suit)) {
            this.discard.classList.add('red');
        } else {
            this.discard.classList.add('black');
        }

        // Render card directly without checking face_up (drawn card is always visible to drawer)
        if (card.rank === '★') {
            const jokerIcon = card.suit === 'hearts' ? '🐉' : '👹';
            this.discardContent.innerHTML = `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        } else {
            this.discardContent.innerHTML = `${card.rank}<br>${this.getSuitSymbol(card.suit)}`;
        }
        this.discardBtn.classList.remove('hidden');
    }

    hideDrawnCard() {
        // Restore discard pile to show actual top card (handled by renderGame)
        this.discard.classList.remove('holding');
        this.discardBtn.classList.add('hidden');
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
        // Jokers - use suit to determine icon (hearts = dragon, spades = oni)
        if (card.rank === '★') {
            const jokerIcon = card.suit === 'hearts' ? '🐉' : '👹';
            return `<span class="joker-icon">${jokerIcon}</span><span class="joker-label">Joker</span>`;
        }
        return `${card.rank}<br>${this.getSuitSymbol(card.suit)}`;
    }

    renderGame() {
        if (!this.gameState) return;

        // Update header
        this.currentRoundSpan.textContent = this.gameState.current_round;
        this.totalRoundsSpan.textContent = this.gameState.total_rounds;

        // Update status message (handled by specific actions, but set default here)
        const currentPlayer = this.gameState.players.find(p => p.id === this.gameState.current_player_id);
        if (currentPlayer && currentPlayer.id !== this.playerId) {
            this.setStatus(`${currentPlayer.name}'s turn`);
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
            const crownEmoji = isRoundWinner ? ' 👑' : '';
            // Set text content before the score span
            this.playerHeader.childNodes[0].textContent = displayName + checkmark + crownEmoji;
        }

        // Update discard pile (skip if holding a drawn card)
        if (!this.drawnCard) {
            if (this.gameState.discard_top) {
                const discardCard = this.gameState.discard_top;
                const cardKey = `${discardCard.rank}-${discardCard.suit}`;

                // Animate if discard changed
                if (this.lastDiscardKey && this.lastDiscardKey !== cardKey) {
                    this.discard.classList.add('card-flip-in');
                    setTimeout(() => this.discard.classList.remove('card-flip-in'), 400);
                }
                this.lastDiscardKey = cardKey;

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
            } else {
                this.discard.classList.remove('has-card', 'card-front', 'red', 'black', 'joker', 'holding');
                this.discardContent.innerHTML = '';
                this.lastDiscardKey = null;
            }
            this.discardBtn.classList.add('hidden');
        }

        // Update deck/discard clickability and visual state
        const hasDrawn = this.drawnCard || this.gameState.has_drawn_card;
        const canDraw = this.isMyTurn() && !hasDrawn && !this.gameState.waiting_for_initial_flip;

        this.deck.classList.toggle('clickable', canDraw);
        this.deck.classList.toggle('disabled', hasDrawn);

        this.discard.classList.toggle('clickable', canDraw && this.gameState.discard_top);
        // Don't show disabled state when we're holding a drawn card (it's displayed in discard position)
        this.discard.classList.toggle('disabled', hasDrawn && !this.drawnCard);

        // Render opponents in a single row
        const opponents = this.gameState.players.filter(p => p.id !== this.playerId);

        this.opponentsRow.innerHTML = '';

        opponents.forEach((player) => {
            const div = document.createElement('div');
            div.className = 'opponent-area';
            if (player.id === this.gameState.current_player_id) {
                div.classList.add('current-turn');
            }

            const isRoundWinner = this.roundWinnerNames.has(player.name);
            if (isRoundWinner) {
                div.classList.add('round-winner');
            }

            const displayName = player.name.length > 12 ? player.name.substring(0, 11) + '…' : player.name;
            const showingScore = this.calculateShowingScore(player.cards);
            const crownEmoji = isRoundWinner ? ' 👑' : '';

            div.innerHTML = `
                <h4>${displayName}${player.all_face_up ? ' ✓' : ''}${crownEmoji}<span class="opponent-showing">${showingScore}</span></h4>
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

                const isClickable = (
                    (this.gameState.waiting_for_initial_flip && !card.face_up && !isLocallyFlipped) ||
                    (this.drawnCard) ||
                    (this.waitingForFlip && !card.face_up)
                );
                const isSelected = this.selectedCards.includes(index);

                const cardEl = document.createElement('div');
                cardEl.innerHTML = this.renderCard(displayCard, isClickable, isSelected);
                cardEl.firstChild.addEventListener('click', () => this.handleCardClick(index));
                this.playerCards.appendChild(cardEl.firstChild);
            });
        }

        // Show flip prompt for initial flip
        // Show flip prompt during initial flip phase
        if (this.gameState.waiting_for_initial_flip) {
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

        // Update scoreboard panel
        this.updateScorePanel();
    }

    updateScorePanel() {
        if (!this.gameState) return;

        // Update standings (left panel)
        this.updateStandings();

        // Update score table (right panel)
        this.scoreTable.innerHTML = '';

        this.gameState.players.forEach(player => {
            const tr = document.createElement('tr');

            // Highlight current player
            if (player.id === this.gameState.current_player_id) {
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
        }

        if (clickable) classes += ' clickable';
        if (selected) classes += ' selected';

        return `<div class="${classes}">${content}</div>`;
    }

    showScoreboard(scores, isFinal, rankings) {
        this.scoreTable.innerHTML = '';

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
                setTimeout(() => btn.textContent = '📋 Copy Results', 2000);
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
});
