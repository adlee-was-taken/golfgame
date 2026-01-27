// Golf Card Game - Replay Viewer

class ReplayViewer {
    constructor() {
        this.frames = [];
        this.metadata = null;
        this.currentFrame = 0;
        this.isPlaying = false;
        this.playbackSpeed = 1.0;
        this.playInterval = null;
        this.gameId = null;
        this.shareCode = null;

        this.initElements();
        this.bindEvents();
    }

    initElements() {
        this.replayScreen = document.getElementById('replay-screen');
        this.replayTitle = document.getElementById('replay-title');
        this.replayMeta = document.getElementById('replay-meta');
        this.replayBoard = document.getElementById('replay-board');
        this.eventDescription = document.getElementById('replay-event-description');
        this.controlsContainer = document.getElementById('replay-controls');
        this.frameCounter = document.getElementById('replay-frame-counter');
        this.timelineSlider = document.getElementById('replay-timeline');
        this.speedSelect = document.getElementById('replay-speed');

        // Control buttons
        this.btnStart = document.getElementById('replay-btn-start');
        this.btnPrev = document.getElementById('replay-btn-prev');
        this.btnPlay = document.getElementById('replay-btn-play');
        this.btnNext = document.getElementById('replay-btn-next');
        this.btnEnd = document.getElementById('replay-btn-end');

        // Action buttons
        this.btnShare = document.getElementById('replay-btn-share');
        this.btnExport = document.getElementById('replay-btn-export');
        this.btnBack = document.getElementById('replay-btn-back');
    }

    bindEvents() {
        if (this.btnStart) this.btnStart.onclick = () => this.goToFrame(0);
        if (this.btnEnd) this.btnEnd.onclick = () => this.goToFrame(this.frames.length - 1);
        if (this.btnPrev) this.btnPrev.onclick = () => this.prevFrame();
        if (this.btnNext) this.btnNext.onclick = () => this.nextFrame();
        if (this.btnPlay) this.btnPlay.onclick = () => this.togglePlay();

        if (this.timelineSlider) {
            this.timelineSlider.oninput = (e) => {
                this.goToFrame(parseInt(e.target.value));
            };
        }

        if (this.speedSelect) {
            this.speedSelect.onchange = (e) => {
                this.playbackSpeed = parseFloat(e.target.value);
                if (this.isPlaying) {
                    this.stopPlayback();
                    this.startPlayback();
                }
            };
        }

        if (this.btnShare) {
            this.btnShare.onclick = () => this.showShareDialog();
        }

        if (this.btnExport) {
            this.btnExport.onclick = () => this.exportGame();
        }

        if (this.btnBack) {
            this.btnBack.onclick = () => this.hide();
        }

        // Keyboard controls
        document.addEventListener('keydown', (e) => {
            if (!this.replayScreen || !this.replayScreen.classList.contains('active')) return;

            switch (e.key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    this.prevFrame();
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    this.nextFrame();
                    break;
                case ' ':
                    e.preventDefault();
                    this.togglePlay();
                    break;
                case 'Home':
                    e.preventDefault();
                    this.goToFrame(0);
                    break;
                case 'End':
                    e.preventDefault();
                    this.goToFrame(this.frames.length - 1);
                    break;
            }
        });
    }

    async loadReplay(gameId) {
        this.gameId = gameId;
        this.shareCode = null;

        try {
            const token = localStorage.getItem('authToken');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

            const response = await fetch(`/api/replay/game/${gameId}`, { headers });
            if (!response.ok) {
                throw new Error('Failed to load replay');
            }

            const data = await response.json();
            this.frames = data.frames;
            this.metadata = data.metadata;
            this.currentFrame = 0;

            this.show();
            this.render();
            this.updateControls();
        } catch (error) {
            console.error('Failed to load replay:', error);
            this.showError('Failed to load replay. You may not have permission to view this game.');
        }
    }

    async loadSharedReplay(shareCode) {
        this.shareCode = shareCode;
        this.gameId = null;

        try {
            const response = await fetch(`/api/replay/shared/${shareCode}`);
            if (!response.ok) {
                throw new Error('Replay not found or expired');
            }

            const data = await response.json();
            this.frames = data.frames;
            this.metadata = data.metadata;
            this.gameId = data.game_id;
            this.currentFrame = 0;

            // Update title with share info
            if (data.title) {
                this.replayTitle.textContent = data.title;
            }

            this.show();
            this.render();
            this.updateControls();
        } catch (error) {
            console.error('Failed to load shared replay:', error);
            this.showError('Replay not found or has expired.');
        }
    }

    show() {
        // Hide other screens
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        this.replayScreen.classList.add('active');

        // Update title
        if (!this.shareCode && this.metadata) {
            this.replayTitle.textContent = 'Game Replay';
        }

        // Update meta
        if (this.metadata) {
            const players = this.metadata.players.join(' vs ');
            const duration = this.formatDuration(this.metadata.duration);
            const rounds = `${this.metadata.total_rounds} hole${this.metadata.total_rounds > 1 ? 's' : ''}`;
            this.replayMeta.innerHTML = `<span>${players}</span> | <span>${rounds}</span> | <span>${duration}</span>`;
        }
    }

    hide() {
        this.stopPlayback();
        this.replayScreen.classList.remove('active');

        // Return to lobby
        document.getElementById('lobby-screen').classList.add('active');
    }

    render() {
        if (!this.frames.length) return;

        const frame = this.frames[this.currentFrame];
        const state = frame.state;

        this.renderBoard(state);
        this.renderEventInfo(frame);
        this.updateTimeline();
    }

    renderBoard(state) {
        const currentPlayerId = state.current_player_id;

        // Build HTML for all players
        let html = '<div class="replay-players">';

        state.players.forEach((player, idx) => {
            const isCurrent = player.id === currentPlayerId;
            html += `
                <div class="replay-player ${isCurrent ? 'is-current' : ''}">
                    <div class="replay-player-header">
                        <span class="replay-player-name">${this.escapeHtml(player.name)}</span>
                        <span class="replay-player-score">Score: ${player.score} | Total: ${player.total_score}</span>
                    </div>
                    <div class="replay-player-cards">
                        ${this.renderPlayerCards(player.cards)}
                    </div>
                </div>
            `;
        });

        html += '</div>';

        // Center area (deck and discard)
        html += `
            <div class="replay-center">
                <div class="replay-deck">
                    <div class="card card-back">
                        <span class="deck-count">${state.deck_remaining}</span>
                    </div>
                </div>
                <div class="replay-discard">
                    ${state.discard_top ? this.renderCard(state.discard_top, true) : '<div class="card card-empty"></div>'}
                </div>
                ${state.drawn_card ? `
                    <div class="replay-drawn">
                        <span class="drawn-label">Drawn:</span>
                        ${this.renderCard(state.drawn_card, true)}
                    </div>
                ` : ''}
            </div>
        `;

        // Game info
        html += `
            <div class="replay-info">
                <span>Round ${state.current_round} / ${state.total_rounds}</span>
                <span>Phase: ${this.formatPhase(state.phase)}</span>
            </div>
        `;

        this.replayBoard.innerHTML = html;
    }

    renderPlayerCards(cards) {
        let html = '<div class="replay-cards-grid">';

        // Render as 2 rows x 3 columns
        for (let row = 0; row < 2; row++) {
            html += '<div class="replay-cards-row">';
            for (let col = 0; col < 3; col++) {
                const idx = row * 3 + col;
                const card = cards[idx];
                if (card) {
                    html += this.renderCard(card, card.face_up);
                } else {
                    html += '<div class="card card-empty"></div>';
                }
            }
            html += '</div>';
        }

        html += '</div>';
        return html;
    }

    renderCard(card, revealed = false) {
        if (!revealed || !card.face_up) {
            return '<div class="card card-back"></div>';
        }

        const suit = card.suit;
        const rank = card.rank;
        const isRed = suit === 'hearts' || suit === 'diamonds';
        const suitSymbol = { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' }[suit] || '';

        return `
            <div class="card ${isRed ? 'card-red' : 'card-black'}">
                <span class="card-rank">${rank}</span>
                <span class="card-suit">${suitSymbol}</span>
            </div>
        `;
    }

    renderEventInfo(frame) {
        const descriptions = {
            'game_created': 'Game created',
            'player_joined': `${frame.event_data?.player_name || 'Player'} joined`,
            'player_left': `Player left the game`,
            'game_started': 'Game started',
            'round_started': `Round ${frame.event_data?.round || ''} started`,
            'initial_flip': `${this.getPlayerName(frame.player_id)} revealed initial cards`,
            'card_drawn': `${this.getPlayerName(frame.player_id)} drew from ${frame.event_data?.source || 'deck'}`,
            'card_swapped': `${this.getPlayerName(frame.player_id)} swapped a card`,
            'card_discarded': `${this.getPlayerName(frame.player_id)} discarded`,
            'card_flipped': `${this.getPlayerName(frame.player_id)} flipped a card`,
            'flip_skipped': `${this.getPlayerName(frame.player_id)} skipped flip`,
            'knock_early': `${this.getPlayerName(frame.player_id)} knocked early!`,
            'round_ended': `Round ended`,
            'game_ended': `Game over! ${this.metadata?.winner || 'Winner'} wins!`,
        };

        const desc = descriptions[frame.event_type] || frame.event_type;
        const time = this.formatTimestamp(frame.timestamp);

        this.eventDescription.innerHTML = `
            <span class="event-time">${time}</span>
            <span class="event-text">${desc}</span>
        `;
    }

    getPlayerName(playerId) {
        if (!playerId || !this.frames.length) return 'Player';

        const currentState = this.frames[this.currentFrame]?.state;
        if (!currentState) return 'Player';

        const player = currentState.players.find(p => p.id === playerId);
        return player?.name || 'Player';
    }

    updateControls() {
        if (this.timelineSlider) {
            this.timelineSlider.max = Math.max(0, this.frames.length - 1);
            this.timelineSlider.value = this.currentFrame;
        }

        // Show/hide share button based on whether we own the game
        if (this.btnShare) {
            this.btnShare.style.display = this.gameId && localStorage.getItem('authToken') ? '' : 'none';
        }
    }

    updateTimeline() {
        if (this.timelineSlider) {
            this.timelineSlider.value = this.currentFrame;
        }

        if (this.frameCounter) {
            this.frameCounter.textContent = `${this.currentFrame + 1} / ${this.frames.length}`;
        }
    }

    goToFrame(index) {
        this.currentFrame = Math.max(0, Math.min(index, this.frames.length - 1));
        this.render();
    }

    nextFrame() {
        if (this.currentFrame < this.frames.length - 1) {
            this.currentFrame++;
            this.render();
        } else if (this.isPlaying) {
            this.togglePlay(); // Stop at end
        }
    }

    prevFrame() {
        if (this.currentFrame > 0) {
            this.currentFrame--;
            this.render();
        }
    }

    togglePlay() {
        this.isPlaying = !this.isPlaying;

        if (this.btnPlay) {
            this.btnPlay.textContent = this.isPlaying ? '⏸' : '▶';
        }

        if (this.isPlaying) {
            this.startPlayback();
        } else {
            this.stopPlayback();
        }
    }

    startPlayback() {
        const baseInterval = 1000; // 1 second between frames
        this.playInterval = setInterval(() => {
            this.nextFrame();
        }, baseInterval / this.playbackSpeed);
    }

    stopPlayback() {
        if (this.playInterval) {
            clearInterval(this.playInterval);
            this.playInterval = null;
        }
    }

    async showShareDialog() {
        if (!this.gameId) return;

        const modal = document.createElement('div');
        modal.className = 'modal active';
        modal.id = 'share-modal';
        modal.innerHTML = `
            <div class="modal-content">
                <h3>Share This Game</h3>

                <div class="form-group">
                    <label for="share-title">Title (optional)</label>
                    <input type="text" id="share-title" placeholder="Epic comeback win!">
                </div>

                <div class="form-group">
                    <label for="share-expiry">Expires in</label>
                    <select id="share-expiry">
                        <option value="">Never</option>
                        <option value="7">7 days</option>
                        <option value="30">30 days</option>
                        <option value="90">90 days</option>
                    </select>
                </div>

                <div id="share-result" class="hidden">
                    <p>Share this link:</p>
                    <div class="share-link-container">
                        <input type="text" id="share-link" readonly>
                        <button class="btn btn-small" id="share-copy-btn">Copy</button>
                    </div>
                </div>

                <div class="modal-actions">
                    <button class="btn btn-primary" id="share-generate-btn">Generate Link</button>
                    <button class="btn btn-secondary" id="share-cancel-btn">Cancel</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const generateBtn = modal.querySelector('#share-generate-btn');
        const cancelBtn = modal.querySelector('#share-cancel-btn');
        const copyBtn = modal.querySelector('#share-copy-btn');

        cancelBtn.onclick = () => modal.remove();

        generateBtn.onclick = async () => {
            const title = modal.querySelector('#share-title').value || null;
            const expiry = modal.querySelector('#share-expiry').value || null;

            try {
                const token = localStorage.getItem('authToken');
                const response = await fetch(`/api/replay/game/${this.gameId}/share`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        title,
                        expires_days: expiry ? parseInt(expiry) : null,
                    }),
                });

                if (!response.ok) {
                    throw new Error('Failed to create share link');
                }

                const data = await response.json();
                const fullUrl = `${window.location.origin}/replay/${data.share_code}`;

                modal.querySelector('#share-link').value = fullUrl;
                modal.querySelector('#share-result').classList.remove('hidden');
                generateBtn.classList.add('hidden');
            } catch (error) {
                console.error('Failed to create share link:', error);
                alert('Failed to create share link');
            }
        };

        copyBtn.onclick = () => {
            const input = modal.querySelector('#share-link');
            input.select();
            document.execCommand('copy');
            copyBtn.textContent = 'Copied!';
            setTimeout(() => copyBtn.textContent = 'Copy', 2000);
        };
    }

    async exportGame() {
        if (!this.gameId) return;

        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch(`/api/replay/game/${this.gameId}/export`, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
            });

            if (!response.ok) {
                throw new Error('Failed to export game');
            }

            const data = await response.json();

            // Download as JSON file
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `golf-game-${this.gameId.substring(0, 8)}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Failed to export game:', error);
            alert('Failed to export game');
        }
    }

    showError(message) {
        this.show();
        this.replayBoard.innerHTML = `
            <div class="replay-error">
                <p>${this.escapeHtml(message)}</p>
                <button class="btn btn-primary" onclick="replayViewer.hide()">Back to Lobby</button>
            </div>
        `;
    }

    formatDuration(seconds) {
        if (!seconds) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    formatTimestamp(seconds) {
        return this.formatDuration(seconds);
    }

    formatPhase(phase) {
        const phases = {
            'waiting': 'Waiting',
            'initial_flip': 'Initial Flip',
            'playing': 'Playing',
            'final_turn': 'Final Turn',
            'round_over': 'Round Over',
            'game_over': 'Game Over',
        };
        return phases[phase] || phase;
    }

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

// Global instance
const replayViewer = new ReplayViewer();

// Check URL for replay links
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;

    // Handle /replay/{share_code} URLs
    if (path.startsWith('/replay/')) {
        const shareCode = path.substring(8);
        if (shareCode) {
            replayViewer.loadSharedReplay(shareCode);
        }
    }
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ReplayViewer, replayViewer };
}
