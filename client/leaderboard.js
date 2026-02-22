/**
 * Leaderboard component for Golf game.
 * Handles leaderboard display, metric switching, and player stats modal.
 */

class LeaderboardComponent {
    constructor() {
        this.currentMetric = 'wins';
        this.cache = new Map();
        this.cacheTimeout = 60000; // 1 minute cache

        this.elements = {
            screen: document.getElementById('leaderboard-screen'),
            backBtn: document.getElementById('leaderboard-back-btn'),
            openBtn: document.getElementById('leaderboard-btn'),
            tabs: document.getElementById('leaderboard-tabs'),
            content: document.getElementById('leaderboard-content'),
            statsModal: document.getElementById('player-stats-modal'),
            statsContent: document.getElementById('player-stats-content'),
            statsClose: document.getElementById('player-stats-close'),
        };

        this.metricLabels = {
            wins: 'Total Wins',
            win_rate: 'Win Rate',
            avg_score: 'Avg Score',
            knockouts: 'Knockouts',
            streak: 'Best Streak',
            rating: 'Rating',
        };

        this.metricFormats = {
            wins: (v) => v.toLocaleString(),
            win_rate: (v) => `${v.toFixed(1)}%`,
            avg_score: (v) => v.toFixed(1),
            knockouts: (v) => v.toLocaleString(),
            streak: (v) => v.toLocaleString(),
            rating: (v) => Math.round(v).toLocaleString(),
        };

        this.init();
    }

    init() {
        // Open leaderboard
        this.elements.openBtn?.addEventListener('click', () => this.show());

        // Back button
        this.elements.backBtn?.addEventListener('click', () => this.hide());

        // Tab switching
        this.elements.tabs?.addEventListener('click', (e) => {
            if (e.target.classList.contains('leaderboard-tab')) {
                this.switchMetric(e.target.dataset.metric);
            }
        });

        // Close player stats modal
        this.elements.statsClose?.addEventListener('click', () => this.closePlayerStats());
        this.elements.statsModal?.addEventListener('click', (e) => {
            if (e.target === this.elements.statsModal) {
                this.closePlayerStats();
            }
        });

        // Handle clicks on player names
        this.elements.content?.addEventListener('click', (e) => {
            const playerLink = e.target.closest('.player-link');
            if (playerLink) {
                const userId = playerLink.dataset.userId;
                if (userId) {
                    this.showPlayerStats(userId);
                }
            }
        });
    }

    show() {
        // Hide other screens, show leaderboard
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        this.elements.screen.classList.add('active');
        this.loadLeaderboard(this.currentMetric);
    }

    hide() {
        this.elements.screen.classList.remove('active');
        document.getElementById('lobby-screen').classList.add('active');
    }

    switchMetric(metric) {
        if (metric === this.currentMetric) return;

        this.currentMetric = metric;

        // Update tab styling
        this.elements.tabs.querySelectorAll('.leaderboard-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.metric === metric);
        });

        this.loadLeaderboard(metric);
    }

    async loadLeaderboard(metric) {
        // Check cache
        const cacheKey = `leaderboard_${metric}`;
        const cached = this.cache.get(cacheKey);
        if (cached && Date.now() - cached.time < this.cacheTimeout) {
            this.renderLeaderboard(cached.data, metric);
            return;
        }

        // Show loading
        this.elements.content.innerHTML = '<div class="leaderboard-loading">Loading...</div>';

        try {
            const response = await fetch(`/api/stats/leaderboard?metric=${metric}&limit=50`);
            if (!response.ok) throw new Error('Failed to load leaderboard');

            const data = await response.json();

            // Cache the result
            this.cache.set(cacheKey, { data, time: Date.now() });

            this.renderLeaderboard(data, metric);
        } catch (error) {
            console.error('Error loading leaderboard:', error);
            this.elements.content.innerHTML = `
                <div class="leaderboard-empty">
                    <p>Failed to load leaderboard</p>
                    <button class="btn btn-small btn-secondary" onclick="leaderboard.loadLeaderboard('${metric}')">Retry</button>
                </div>
            `;
        }
    }

    renderLeaderboard(data, metric) {
        const entries = data.entries || [];

        if (entries.length === 0) {
            this.elements.content.innerHTML = `
                <div class="leaderboard-empty">
                    <p>No players on the leaderboard yet.</p>
                    <p>Play 5+ games to appear here!</p>
                </div>
            `;
            return;
        }

        const formatValue = this.metricFormats[metric] || (v => v);
        const currentUserId = this.getCurrentUserId();

        let html = `
            <table class="leaderboard-table">
                <thead>
                    <tr>
                        <th class="rank-col">#</th>
                        <th class="username-col">Player</th>
                        <th class="value-col">${this.metricLabels[metric]}</th>
                        <th class="games-col">Games</th>
                    </tr>
                </thead>
                <tbody>
        `;

        entries.forEach(entry => {
            const isMe = entry.user_id === currentUserId;
            const medal = this.getMedal(entry.rank);

            html += `
                <tr class="${isMe ? 'my-row' : ''}">
                    <td class="rank-col">${medal || entry.rank}</td>
                    <td class="username-col">
                        <span class="player-link" data-user-id="${entry.user_id}">
                            ${this.escapeHtml(entry.username)}${isMe ? ' (you)' : ''}
                        </span>
                    </td>
                    <td class="value-col">${formatValue(entry.value)}</td>
                    <td class="games-col">${entry.games_played}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        this.elements.content.innerHTML = html;
    }

    getMedal(rank) {
        switch (rank) {
            case 1: return '<span class="medal">&#x1F947;</span>';
            case 2: return '<span class="medal">&#x1F948;</span>';
            case 3: return '<span class="medal">&#x1F949;</span>';
            default: return null;
        }
    }

    async showPlayerStats(userId) {
        this.elements.statsModal.classList.remove('hidden');
        this.elements.statsContent.innerHTML = '<div class="leaderboard-loading">Loading...</div>';

        try {
            const [statsRes, achievementsRes] = await Promise.all([
                fetch(`/api/stats/players/${userId}`),
                fetch(`/api/stats/players/${userId}/achievements`),
            ]);

            if (!statsRes.ok) throw new Error('Failed to load player stats');

            const stats = await statsRes.json();
            const achievements = achievementsRes.ok ? await achievementsRes.json() : { achievements: [] };

            this.renderPlayerStats(stats, achievements.achievements || []);
        } catch (error) {
            console.error('Error loading player stats:', error);
            this.elements.statsContent.innerHTML = `
                <div class="leaderboard-empty">
                    <p>Failed to load player stats</p>
                </div>
            `;
        }
    }

    renderPlayerStats(stats, achievements) {
        const currentUserId = this.getCurrentUserId();
        const isMe = stats.user_id === currentUserId;

        let html = `
            <div class="player-stats-header">
                <h3>${this.escapeHtml(stats.username)}${isMe ? ' (you)' : ''}</h3>
                ${stats.games_played >= 5 ? '<p class="rank-badge">Ranked Player</p>' : '<p class="rank-badge">Unranked (needs 5+ games)</p>'}
            </div>

            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-value">${stats.games_won}</div>
                    <div class="stat-label">Wins</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.win_rate.toFixed(1)}%</div>
                    <div class="stat-label">Win Rate</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.games_played}</div>
                    <div class="stat-label">Games</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.avg_score.toFixed(1)}</div>
                    <div class="stat-label">Avg Score</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.best_round_score ?? '-'}</div>
                    <div class="stat-label">Best Round</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.knockouts}</div>
                    <div class="stat-label">Knockouts</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.best_win_streak}</div>
                    <div class="stat-label">Best Streak</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.rounds_played}</div>
                    <div class="stat-label">Rounds</div>
                </div>
            </div>
        `;

        // Achievements section
        if (achievements.length > 0) {
            html += `
                <div class="achievements-section">
                    <h4>Achievements (${achievements.length})</h4>
                    <div class="achievements-grid">
            `;

            achievements.forEach(a => {
                html += `
                    <div class="achievement-badge" title="${this.escapeHtml(a.description)}">
                        <span class="icon">${a.icon}</span>
                        <span class="name">${this.escapeHtml(a.name)}</span>
                    </div>
                `;
            });

            html += '</div></div>';
        }

        this.elements.statsContent.innerHTML = html;
    }

    closePlayerStats() {
        this.elements.statsModal.classList.add('hidden');
    }

    getCurrentUserId() {
        // Get user ID from auth state if available
        if (window.authState && window.authState.user) {
            return window.authState.user.id;
        }
        return null;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Public method to clear cache (e.g., after game ends)
    clearCache() {
        this.cache.clear();
    }
}

// Initialize global leaderboard instance
const leaderboard = new LeaderboardComponent();
