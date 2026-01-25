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
        this.playersList = document.getElementById('players-list');
        this.hostSettings = document.getElementById('host-settings');
        this.waitingMessage = document.getElementById('waiting-message');
        this.numDecksSelect = document.getElementById('num-decks');
        this.deckRecommendation = document.getElementById('deck-recommendation');
        this.numRoundsSelect = document.getElementById('num-rounds');
        this.initialFlipsSelect = document.getElementById('initial-flips');
        this.flipOnDiscardCheckbox = document.getElementById('flip-on-discard');
        this.knockPenaltyCheckbox = document.getElementById('knock-penalty');
        this.jokerModeSelect = document.getElementById('joker-mode');
        // House Rules - Point Modifiers
        this.superKingsCheckbox = document.getElementById('super-kings');
        this.luckySevensCheckbox = document.getElementById('lucky-sevens');
        this.tenPennyCheckbox = document.getElementById('ten-penny');
        // House Rules - Bonuses/Penalties
        this.knockBonusCheckbox = document.getElementById('knock-bonus');
        this.underdogBonusCheckbox = document.getElementById('underdog-bonus');
        this.tiedShameCheckbox = document.getElementById('tied-shame');
        this.blackjackCheckbox = document.getElementById('blackjack');
        // House Rules - Gameplay Twists
        this.queensWildCheckbox = document.getElementById('queens-wild');
        this.fourOfAKindCheckbox = document.getElementById('four-of-a-kind');
        this.eagleEyeCheckbox = document.getElementById('eagle-eye');
        this.eagleEyeLabel = document.getElementById('eagle-eye-label');
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
        this.deckCountSpan = document.getElementById('deck-count');
        this.muteBtn = document.getElementById('mute-btn');
        this.opponentsRow = document.getElementById('opponents-row');
        this.deck = document.getElementById('deck');
        this.discard = document.getElementById('discard');
        this.discardContent = document.getElementById('discard-content');
        this.drawnCardArea = document.getElementById('drawn-card-area');
        this.drawnCardEl = document.getElementById('drawn-card');
        this.discardBtn = document.getElementById('discard-btn');
        this.playerCards = document.getElementById('player-cards');
        this.flipPrompt = document.getElementById('flip-prompt');
        this.toast = document.getElementById('toast');
        this.scoreboard = document.getElementById('scoreboard');
        this.scoreTable = document.getElementById('score-table').querySelector('tbody');
        this.gameButtons = document.getElementById('game-buttons');
        this.nextRoundBtn = document.getElementById('next-round-btn');
        this.newGameBtn = document.getElementById('new-game-btn');
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

        // Eagle Eye only works with Standard Jokers (need 2 to pair them)
        const updateEagleEyeVisibility = () => {
            const isStandardJokers = this.jokerModeSelect.value === 'standard';
            if (isStandardJokers) {
                this.eagleEyeLabel.classList.remove('hidden');
            } else {
                this.eagleEyeLabel.classList.add('hidden');
                this.eagleEyeCheckbox.checked = false;
            }
        };
        this.jokerModeSelect.addEventListener('change', updateEagleEyeVisibility);
        // Check initial state
        updateEagleEyeVisibility();

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
                this.gameState = data.game_state;
                this.playSound('shuffle');
                this.showGameScreen();
                this.renderGame();
                break;

            case 'game_state':
                this.gameState = data.game_state;
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

    startGame() {
        const decks = parseInt(this.numDecksSelect.value);
        const rounds = parseInt(this.numRoundsSelect.value);
        const initial_flips = parseInt(this.initialFlipsSelect.value);

        // Standard options
        const flip_on_discard = this.flipOnDiscardCheckbox.checked;
        const knock_penalty = this.knockPenaltyCheckbox.checked;

        // Joker mode
        const joker_mode = this.jokerModeSelect.value;
        const use_jokers = joker_mode !== 'none';
        const lucky_swing = joker_mode === 'lucky-swing';

        // House Rules - Point Modifiers
        const super_kings = this.superKingsCheckbox.checked;
        const lucky_sevens = this.luckySevensCheckbox.checked;
        const ten_penny = this.tenPennyCheckbox.checked;

        // House Rules - Bonuses/Penalties
        const knock_bonus = this.knockBonusCheckbox.checked;
        const underdog_bonus = this.underdogBonusCheckbox.checked;
        const tied_shame = this.tiedShameCheckbox.checked;
        const blackjack = this.blackjackCheckbox.checked;

        // House Rules - Gameplay Twists
        const queens_wild = this.queensWildCheckbox.checked;
        const four_of_a_kind = this.fourOfAKindCheckbox.checked;
        const eagle_eye = this.eagleEyeCheckbox.checked;

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
            lucky_sevens,
            ten_penny,
            knock_bonus,
            underdog_bonus,
            tied_shame,
            blackjack,
            queens_wild,
            four_of_a_kind,
            eagle_eye
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

    flipCard(position) {
        this.send({ type: 'flip_card', position });
        this.waitingForFlip = false;
    }

    handleCardClick(position) {
        const myData = this.getMyPlayerData();
        if (!myData) return;

        const card = myData.cards[position];

        // Initial flip phase
        if (this.gameState.waiting_for_initial_flip) {
            if (card.face_up) return;

            this.playSound('card');
            const requiredFlips = this.gameState.initial_flips || 2;

            if (this.selectedCards.includes(position)) {
                this.selectedCards = this.selectedCards.filter(p => p !== position);
            } else {
                this.selectedCards.push(position);
            }

            if (this.selectedCards.length === requiredFlips) {
                this.send({ type: 'flip_initial', positions: this.selectedCards });
                this.selectedCards = [];
                this.hideToast();
            } else {
                const remaining = requiredFlips - this.selectedCards.length;
                this.showToast(`Select ${remaining} more card${remaining > 1 ? 's' : ''} to flip`, '', 5000);
            }
            this.renderGame();
            return;
        }

        // Swap with drawn card
        if (this.drawnCard) {
            this.swapCard(position);
            this.hideToast();
            return;
        }

        // Flip after discarding from deck
        if (this.waitingForFlip && !card.face_up) {
            this.flipCard(position);
            this.hideToast();
            return;
        }
    }

    nextRound() {
        this.send({ type: 'next_round' });
        this.gameButtons.classList.add('hidden');
    }

    newGame() {
        this.leaveRoom();
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

    showToast(message, type = '', duration = 2500) {
        this.toast.textContent = message;
        this.toast.className = 'toast' + (type ? ' ' + type : '');

        clearTimeout(this.toastTimeout);
        this.toastTimeout = setTimeout(() => {
            this.toast.classList.add('hidden');
        }, duration);
    }

    hideToast() {
        this.toast.classList.add('hidden');
        clearTimeout(this.toastTimeout);
    }

    showDrawnCard() {
        this.drawnCardArea.classList.remove('hidden');
        // Drawn card is always revealed to the player, so render directly
        const card = this.drawnCard;
        this.drawnCardEl.className = 'card card-front';

        // Handle jokers specially
        if (card.rank === '★') {
            this.drawnCardEl.innerHTML = '★<br>JOKER';
            this.drawnCardEl.classList.add('joker');
        } else {
            this.drawnCardEl.innerHTML = `${card.rank}<br>${this.getSuitSymbol(card.suit)}`;
            if (this.isRedSuit(card.suit)) {
                this.drawnCardEl.classList.add('red');
            } else {
                this.drawnCardEl.classList.add('black');
            }
        }
    }

    hideDrawnCard() {
        this.drawnCardArea.classList.add('hidden');
    }

    isRedSuit(suit) {
        return suit === 'hearts' || suit === 'diamonds';
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
        // Jokers show star symbol without suit
        if (card.rank === '★') {
            return '★<br>JOKER';
        }
        return `${card.rank}<br>${this.getSuitSymbol(card.suit)}`;
    }

    renderGame() {
        if (!this.gameState) return;

        // Update header
        this.currentRoundSpan.textContent = this.gameState.current_round;
        this.totalRoundsSpan.textContent = this.gameState.total_rounds;
        this.deckCountSpan.textContent = this.gameState.deck_remaining;

        // Update discard pile
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
            this.discard.classList.remove('has-card', 'card-front', 'red', 'black', 'joker');
            this.discardContent.innerHTML = '';
        }

        // Update deck/discard clickability and visual state
        const hasDrawn = this.drawnCard || this.gameState.has_drawn_card;
        const canDraw = this.isMyTurn() && !hasDrawn && !this.gameState.waiting_for_initial_flip;

        this.deck.classList.toggle('clickable', canDraw);
        this.deck.classList.toggle('disabled', hasDrawn);

        this.discard.classList.toggle('clickable', canDraw && this.gameState.discard_top);
        this.discard.classList.toggle('disabled', hasDrawn);

        // Render opponents in a single row
        const opponents = this.gameState.players.filter(p => p.id !== this.playerId);

        this.opponentsRow.innerHTML = '';

        opponents.forEach((player) => {
            const div = document.createElement('div');
            div.className = 'opponent-area';
            if (player.id === this.gameState.current_player_id) {
                div.classList.add('current-turn');
            }

            const displayName = player.name.length > 8 ? player.name.substring(0, 7) + '…' : player.name;

            div.innerHTML = `
                <h4>${displayName}${player.all_face_up ? ' ✓' : ''}</h4>
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
                const isClickable = (
                    (this.gameState.waiting_for_initial_flip && !card.face_up) ||
                    (this.drawnCard) ||
                    (this.waitingForFlip && !card.face_up)
                );
                const isSelected = this.selectedCards.includes(index);

                const cardEl = document.createElement('div');
                cardEl.innerHTML = this.renderCard(card, isClickable, isSelected);
                cardEl.firstChild.addEventListener('click', () => this.handleCardClick(index));
                this.playerCards.appendChild(cardEl.firstChild);
            });
        }

        // Show flip prompt for initial flip
        if (this.gameState.waiting_for_initial_flip) {
            const requiredFlips = this.gameState.initial_flips || 2;
            const remaining = requiredFlips - this.selectedCards.length;
            if (remaining > 0) {
                this.flipPrompt.textContent = `Select ${remaining} card${remaining > 1 ? 's' : ''} to flip`;
                this.flipPrompt.classList.remove('hidden');
            } else {
                this.flipPrompt.classList.add('hidden');
            }
        } else {
            this.flipPrompt.classList.add('hidden');
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

        this.scoreTable.innerHTML = '';

        this.gameState.players.forEach(player => {
            const tr = document.createElement('tr');

            // Highlight current player
            if (player.id === this.gameState.current_player_id) {
                tr.classList.add('current-player');
            }

            // Truncate long names
            const displayName = player.name.length > 10
                ? player.name.substring(0, 9) + '…'
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

        const minScore = Math.min(...scores.map(s => s.total || s.score || 0));

        scores.forEach(score => {
            const tr = document.createElement('tr');
            const total = score.total !== undefined ? score.total : score.score;
            const roundScore = score.score !== undefined ? score.score : '-';
            const roundsWon = score.rounds_won || 0;

            // Truncate long names
            const displayName = score.name.length > 10
                ? score.name.substring(0, 9) + '…'
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

        // Show rankings announcement
        this.showRankingsAnnouncement(rankings, isFinal);

        // Show game buttons
        this.gameButtons.classList.remove('hidden');

        if (isFinal) {
            this.nextRoundBtn.classList.add('hidden');
            this.newGameBtn.classList.remove('hidden');
        } else if (this.isHost) {
            this.nextRoundBtn.classList.remove('hidden');
            this.newGameBtn.classList.add('hidden');
        } else {
            this.nextRoundBtn.classList.add('hidden');
            this.newGameBtn.classList.add('hidden');
        }
    }

    showRankingsAnnouncement(rankings, isFinal) {
        // Remove existing announcement if any
        const existing = document.getElementById('rankings-announcement');
        if (existing) existing.remove();

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
            const name = p.name.length > 8 ? p.name.substring(0, 7) + '…' : p.name;
            return `<div class="rank-row ${pointsRank === 0 ? 'leader' : ''}"><span class="rank-pos">${medal}</span><span class="rank-name">${name}</span><span class="rank-val">${p.total}pt</span></div>`;
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
            const name = p.name.length > 8 ? p.name.substring(0, 7) + '…' : p.name;
            return `<div class="rank-row ${holesRank === 0 && p.rounds_won > 0 ? 'leader' : ''}"><span class="rank-pos">${medal}</span><span class="rank-name">${name}</span><span class="rank-val">${p.rounds_won}W</span></div>`;
        }).join('');

        const doubleVictoryHtml = isDoubleVictory
            ? `<div class="double-victory">DOUBLE VICTORY! ${pointsLeader.name}</div>`
            : '';

        announcement.innerHTML = `
            <h3>${title}</h3>
            ${doubleVictoryHtml}
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
}

// Initialize game when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.game = new GolfGame();
});
