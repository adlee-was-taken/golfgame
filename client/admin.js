/**
 * Golf Admin Dashboard
 * JavaScript for admin interface functionality
 */

// State
let authToken = null;
let currentUser = null;
let currentPanel = 'dashboard';
let selectedUserId = null;

// Pagination state
let usersPage = 0;
let auditPage = 0;
const PAGE_SIZE = 20;

// =============================================================================
// API Functions
// =============================================================================

async function apiRequest(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }

    const response = await fetch(endpoint, {
        ...options,
        headers,
    });

    if (response.status === 401) {
        // Unauthorized - clear auth and show login
        logout();
        throw new Error('Session expired. Please login again.');
    }

    if (response.status === 403) {
        throw new Error('Admin access required');
    }

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || 'Request failed');
    }

    return data;
}

// Auth API
async function login(username, password) {
    const data = await apiRequest('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
    });
    return data;
}

// Admin API
async function getStats() {
    return apiRequest('/api/admin/stats');
}

async function getUsers(query = '', offset = 0, includeBanned = true) {
    const params = new URLSearchParams({
        query,
        offset,
        limit: PAGE_SIZE,
        include_banned: includeBanned,
    });
    return apiRequest(`/api/admin/users?${params}`);
}

async function getUser(userId) {
    return apiRequest(`/api/admin/users/${userId}`);
}

async function getUserBanHistory(userId) {
    return apiRequest(`/api/admin/users/${userId}/ban-history`);
}

async function banUser(userId, reason, durationDays) {
    return apiRequest(`/api/admin/users/${userId}/ban`, {
        method: 'POST',
        body: JSON.stringify({
            reason,
            duration_days: durationDays || null,
        }),
    });
}

async function unbanUser(userId) {
    return apiRequest(`/api/admin/users/${userId}/unban`, {
        method: 'POST',
    });
}

async function forcePasswordReset(userId) {
    return apiRequest(`/api/admin/users/${userId}/force-password-reset`, {
        method: 'POST',
    });
}

async function changeUserRole(userId, role) {
    return apiRequest(`/api/admin/users/${userId}/role`, {
        method: 'PUT',
        body: JSON.stringify({ role }),
    });
}

async function impersonateUser(userId) {
    return apiRequest(`/api/admin/users/${userId}/impersonate`, {
        method: 'POST',
    });
}

async function getGames() {
    return apiRequest('/api/admin/games');
}

async function getGameDetails(gameId) {
    return apiRequest(`/api/admin/games/${gameId}`);
}

async function endGame(gameId, reason) {
    return apiRequest(`/api/admin/games/${gameId}/end`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
    });
}

async function getInvites(includeExpired = false) {
    const params = new URLSearchParams({ include_expired: includeExpired });
    return apiRequest(`/api/admin/invites?${params}`);
}

async function createInvite(maxUses, expiresDays) {
    return apiRequest('/api/admin/invites', {
        method: 'POST',
        body: JSON.stringify({
            max_uses: maxUses,
            expires_days: expiresDays,
        }),
    });
}

async function revokeInvite(code) {
    return apiRequest(`/api/admin/invites/${code}`, {
        method: 'DELETE',
    });
}

async function getAuditLog(offset = 0, action = '', targetType = '') {
    const params = new URLSearchParams({
        offset,
        limit: PAGE_SIZE,
    });
    if (action) params.append('action', action);
    if (targetType) params.append('target_type', targetType);
    return apiRequest(`/api/admin/audit?${params}`);
}

// =============================================================================
// UI Functions
// =============================================================================

function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
    document.getElementById(screenId).classList.remove('hidden');
}

function showPanel(panelId) {
    currentPanel = panelId;
    document.querySelectorAll('.panel').forEach(p => p.classList.add('hidden'));
    document.getElementById(`${panelId}-panel`).classList.remove('hidden');

    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.panel === panelId);
    });

    // Load panel data
    switch (panelId) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'users':
            loadUsers();
            break;
        case 'games':
            loadGames();
            break;
        case 'invites':
            loadInvites();
            break;
        case 'audit':
            loadAuditLog();
            break;
    }
}

function showModal(modalId) {
    document.getElementById(modalId).classList.remove('hidden');
}

function hideModal(modalId) {
    document.getElementById(modalId).classList.add('hidden');
}

function hideAllModals() {
    document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4000);
}

function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDateShort(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleDateString();
}

function getStatusBadge(user) {
    if (user.is_banned) {
        return '<span class="badge badge-danger">Banned</span>';
    }
    if (!user.is_active) {
        return '<span class="badge badge-muted">Inactive</span>';
    }
    if (user.force_password_reset) {
        return '<span class="badge badge-warning">Reset Required</span>';
    }
    if (!user.email_verified && user.email) {
        return '<span class="badge badge-warning">Unverified</span>';
    }
    return '<span class="badge badge-success">Active</span>';
}

// =============================================================================
// Data Loading
// =============================================================================

async function loadDashboard() {
    try {
        const stats = await getStats();

        document.getElementById('stat-active-users').textContent = stats.active_users_now;
        document.getElementById('stat-active-games').textContent = stats.active_games_now;
        document.getElementById('stat-total-users').textContent = stats.total_users;
        document.getElementById('stat-games-today').textContent = stats.games_today;
        document.getElementById('stat-reg-today').textContent = stats.registrations_today;
        document.getElementById('stat-reg-week').textContent = stats.registrations_week;
        document.getElementById('stat-total-games').textContent = stats.total_games_completed;
        document.getElementById('stat-events-hour').textContent = stats.events_last_hour;

        // Top players table
        const tbody = document.querySelector('#top-players-table tbody');
        tbody.innerHTML = '';
        stats.top_players.forEach((player, index) => {
            const winRate = player.games_played > 0
                ? Math.round((player.games_won / player.games_played) * 100)
                : 0;
            tbody.innerHTML += `
                <tr>
                    <td>${index + 1}</td>
                    <td>${escapeHtml(player.username)}</td>
                    <td>${player.games_won}</td>
                    <td>${player.games_played}</td>
                    <td>${winRate}%</td>
                </tr>
            `;
        });

        if (stats.top_players.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted">No players yet</td></tr>';
        }
    } catch (error) {
        showToast('Failed to load dashboard: ' + error.message, 'error');
    }
}

async function loadUsers() {
    try {
        const query = document.getElementById('user-search').value;
        const includeBanned = document.getElementById('include-banned').checked;
        const data = await getUsers(query, usersPage * PAGE_SIZE, includeBanned);

        const tbody = document.querySelector('#users-table tbody');
        tbody.innerHTML = '';

        data.users.forEach(user => {
            tbody.innerHTML += `
                <tr>
                    <td>${escapeHtml(user.username)}</td>
                    <td>${escapeHtml(user.email || '-')}</td>
                    <td><span class="badge badge-${user.role === 'admin' ? 'info' : 'muted'}">${user.role}</span></td>
                    <td>${getStatusBadge(user)}</td>
                    <td>${user.games_played} (${user.games_won} wins)</td>
                    <td>${formatDateShort(user.created_at)}</td>
                    <td>
                        <button class="btn btn-small" data-action="view-user" data-id="${user.id}">View</button>
                    </td>
                </tr>
            `;
        });

        if (data.users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted">No users found</td></tr>';
        }

        // Update pagination
        document.getElementById('users-page-info').textContent = `Page ${usersPage + 1}`;
        document.getElementById('users-prev').disabled = usersPage === 0;
        document.getElementById('users-next').disabled = data.users.length < PAGE_SIZE;
    } catch (error) {
        showToast('Failed to load users: ' + error.message, 'error');
    }
}

async function viewUser(userId) {
    try {
        selectedUserId = userId;
        const user = await getUser(userId);
        const history = await getUserBanHistory(userId);

        // Populate details
        document.getElementById('detail-username').textContent = user.username;
        document.getElementById('detail-email').textContent = user.email || '-';
        document.getElementById('detail-role').textContent = user.role;
        document.getElementById('detail-status').innerHTML = getStatusBadge(user);
        document.getElementById('detail-games-played').textContent = user.games_played;
        document.getElementById('detail-games-won').textContent = user.games_won;
        document.getElementById('detail-joined').textContent = formatDate(user.created_at);
        document.getElementById('detail-last-login').textContent = formatDate(user.last_login);

        // Update action buttons visibility
        document.getElementById('action-ban').classList.toggle('hidden', user.is_banned);
        document.getElementById('action-unban').classList.toggle('hidden', !user.is_banned);
        document.getElementById('action-make-admin').classList.toggle('hidden', user.role === 'admin');
        document.getElementById('action-remove-admin').classList.toggle('hidden', user.role !== 'admin');

        // Ban history
        const historyBody = document.querySelector('#ban-history-table tbody');
        historyBody.innerHTML = '';
        history.history.forEach(ban => {
            const status = ban.unbanned_at
                ? `<span class="badge badge-success">Unbanned</span>`
                : (ban.expires_at && new Date(ban.expires_at) < new Date()
                    ? `<span class="badge badge-muted">Expired</span>`
                    : `<span class="badge badge-danger">Active</span>`);
            historyBody.innerHTML += `
                <tr>
                    <td>${formatDateShort(ban.banned_at)}</td>
                    <td>${escapeHtml(ban.reason || '-')}</td>
                    <td>${escapeHtml(ban.banned_by)}</td>
                    <td>${status}</td>
                </tr>
            `;
        });

        if (history.history.length === 0) {
            historyBody.innerHTML = '<tr><td colspan="4" class="text-muted">No ban history</td></tr>';
        }

        showModal('user-modal');
    } catch (error) {
        showToast('Failed to load user: ' + error.message, 'error');
    }
}

async function loadGames() {
    try {
        const data = await getGames();

        const tbody = document.querySelector('#games-table tbody');
        tbody.innerHTML = '';

        data.games.forEach(game => {
            tbody.innerHTML += `
                <tr>
                    <td><strong>${escapeHtml(game.room_code)}</strong></td>
                    <td>${game.player_count}</td>
                    <td>${game.phase || game.status || '-'}</td>
                    <td>${game.current_round || '-'}</td>
                    <td><span class="badge badge-${game.status === 'playing' ? 'success' : 'info'}">${game.status}</span></td>
                    <td>${formatDate(game.created_at)}</td>
                    <td>
                        <button class="btn btn-small btn-danger" data-action="end-game" data-id="${game.game_id}">End</button>
                    </td>
                </tr>
            `;
        });

        if (data.games.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted">No active games</td></tr>';
        }
    } catch (error) {
        showToast('Failed to load games: ' + error.message, 'error');
    }
}

let selectedGameId = null;

function promptEndGame(gameId) {
    selectedGameId = gameId;
    document.getElementById('end-game-reason').value = '';
    showModal('end-game-modal');
}

async function loadInvites() {
    try {
        const includeExpired = document.getElementById('include-expired').checked;
        const data = await getInvites(includeExpired);

        const tbody = document.querySelector('#invites-table tbody');
        tbody.innerHTML = '';

        data.codes.forEach(invite => {
            const isExpired = new Date(invite.expires_at) < new Date();
            const status = !invite.is_active
                ? '<span class="badge badge-danger">Revoked</span>'
                : isExpired
                    ? '<span class="badge badge-muted">Expired</span>'
                    : invite.remaining_uses <= 0
                        ? '<span class="badge badge-warning">Used Up</span>'
                        : '<span class="badge badge-success">Active</span>';

            tbody.innerHTML += `
                <tr>
                    <td><code>${escapeHtml(invite.code)}</code></td>
                    <td>${invite.use_count} / ${invite.max_uses}</td>
                    <td>${invite.remaining_uses}</td>
                    <td>${escapeHtml(invite.created_by_username)}</td>
                    <td>${formatDate(invite.expires_at)}</td>
                    <td>${status}</td>
                    <td>
                        ${invite.is_active && !isExpired && invite.remaining_uses > 0
                            ? `<button class="btn btn-small" data-action="copy-invite" data-code="${escapeHtml(invite.code)}">Copy Link</button>
                               <button class="btn btn-small btn-danger" data-action="revoke-invite" data-code="${escapeHtml(invite.code)}">Revoke</button>`
                            : '-'
                        }
                    </td>
                </tr>
            `;
        });

        if (data.codes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted">No invite codes</td></tr>';
        }
    } catch (error) {
        showToast('Failed to load invites: ' + error.message, 'error');
    }
}

async function loadAuditLog() {
    try {
        const action = document.getElementById('audit-action-filter').value;
        const targetType = document.getElementById('audit-target-filter').value;
        const data = await getAuditLog(auditPage * PAGE_SIZE, action, targetType);

        const tbody = document.querySelector('#audit-table tbody');
        tbody.innerHTML = '';

        data.entries.forEach(entry => {
            const details = Object.keys(entry.details).length > 0
                ? `<code class="text-small">${escapeHtml(JSON.stringify(entry.details))}</code>`
                : '-';

            tbody.innerHTML += `
                <tr>
                    <td>${formatDate(entry.created_at)}</td>
                    <td>${escapeHtml(entry.admin_username)}</td>
                    <td><span class="badge badge-info">${entry.action}</span></td>
                    <td>${entry.target_type ? `${entry.target_type}: ${entry.target_id || '-'}` : '-'}</td>
                    <td>${details}</td>
                    <td class="text-muted text-small">${entry.ip_address || '-'}</td>
                </tr>
            `;
        });

        if (data.entries.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-muted">No audit entries</td></tr>';
        }

        // Update pagination
        document.getElementById('audit-page-info').textContent = `Page ${auditPage + 1}`;
        document.getElementById('audit-prev').disabled = auditPage === 0;
        document.getElementById('audit-next').disabled = data.entries.length < PAGE_SIZE;
    } catch (error) {
        showToast('Failed to load audit log: ' + error.message, 'error');
    }
}

// =============================================================================
// Actions
// =============================================================================

async function handleBanUser(event) {
    event.preventDefault();

    const reason = document.getElementById('ban-reason').value;
    const duration = document.getElementById('ban-duration').value;

    try {
        await banUser(selectedUserId, reason, duration ? parseInt(duration) : null);
        showToast('User banned successfully', 'success');
        hideAllModals();
        loadUsers();
    } catch (error) {
        showToast('Failed to ban user: ' + error.message, 'error');
    }
}

async function handleUnbanUser() {
    if (!confirm('Are you sure you want to unban this user?')) return;

    try {
        await unbanUser(selectedUserId);
        showToast('User unbanned successfully', 'success');
        hideAllModals();
        loadUsers();
    } catch (error) {
        showToast('Failed to unban user: ' + error.message, 'error');
    }
}

async function handleForcePasswordReset() {
    if (!confirm('Are you sure you want to force a password reset for this user? They will be logged out.')) return;

    try {
        await forcePasswordReset(selectedUserId);
        showToast('Password reset required for user', 'success');
        hideAllModals();
        loadUsers();
    } catch (error) {
        showToast('Failed to force password reset: ' + error.message, 'error');
    }
}

async function handleMakeAdmin() {
    if (!confirm('Are you sure you want to make this user an admin?')) return;

    try {
        await changeUserRole(selectedUserId, 'admin');
        showToast('User is now an admin', 'success');
        hideAllModals();
        loadUsers();
    } catch (error) {
        showToast('Failed to change role: ' + error.message, 'error');
    }
}

async function handleRemoveAdmin() {
    if (!confirm('Are you sure you want to remove admin privileges from this user?')) return;

    try {
        await changeUserRole(selectedUserId, 'user');
        showToast('Admin privileges removed', 'success');
        hideAllModals();
        loadUsers();
    } catch (error) {
        showToast('Failed to change role: ' + error.message, 'error');
    }
}

async function handleImpersonate() {
    try {
        const data = await impersonateUser(selectedUserId);
        showToast(`Viewing as ${data.user.username} (read-only). Check console for details.`, 'success');
        console.log('Impersonation data:', data);
    } catch (error) {
        showToast('Failed to impersonate: ' + error.message, 'error');
    }
}

async function handleEndGame(event) {
    event.preventDefault();

    const reason = document.getElementById('end-game-reason').value;

    try {
        await endGame(selectedGameId, reason);
        showToast('Game ended successfully', 'success');
        hideAllModals();
        loadGames();
    } catch (error) {
        showToast('Failed to end game: ' + error.message, 'error');
    }
}

async function handleCreateInvite() {
    const maxUses = parseInt(document.getElementById('invite-max-uses').value) || 1;
    const expiresDays = parseInt(document.getElementById('invite-expires-days').value) || 7;

    try {
        const data = await createInvite(maxUses, expiresDays);
        showToast(`Invite code created: ${data.code}`, 'success');
        loadInvites();
    } catch (error) {
        showToast('Failed to create invite: ' + error.message, 'error');
    }
}

function copyInviteLink(code) {
    const link = `${window.location.origin}/?invite=${encodeURIComponent(code)}`;
    navigator.clipboard.writeText(link).then(() => {
        showToast('Invite link copied!', 'success');
    }).catch(() => {
        // Fallback: select text for manual copy
        prompt('Copy this link:', link);
    });
}

async function promptRevokeInvite(code) {
    if (!confirm(`Are you sure you want to revoke invite code ${code}?`)) return;

    try {
        await revokeInvite(code);
        showToast('Invite code revoked', 'success');
        loadInvites();
    } catch (error) {
        showToast('Failed to revoke invite: ' + error.message, 'error');
    }
}

// =============================================================================
// Auth
// =============================================================================

async function handleLogin(event) {
    event.preventDefault();

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const errorEl = document.getElementById('login-error');

    try {
        const data = await login(username, password);

        // Check if user is admin
        if (data.user.role !== 'admin') {
            errorEl.textContent = 'Admin access required';
            return;
        }

        // Store auth
        authToken = data.token;
        currentUser = data.user;
        localStorage.setItem('adminToken', data.token);
        localStorage.setItem('adminUser', JSON.stringify(data.user));

        // Show dashboard
        document.getElementById('admin-username').textContent = currentUser.username;
        showScreen('dashboard-screen');
        showPanel('dashboard');
    } catch (error) {
        errorEl.textContent = error.message;
    }
}

function logout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('adminToken');
    localStorage.removeItem('adminUser');
    showScreen('login-screen');
}

function checkAuth() {
    const savedToken = localStorage.getItem('adminToken');
    const savedUser = localStorage.getItem('adminUser');

    if (savedToken && savedUser) {
        authToken = savedToken;
        currentUser = JSON.parse(savedUser);

        if (currentUser.role === 'admin') {
            document.getElementById('admin-username').textContent = currentUser.username;
            showScreen('dashboard-screen');
            showPanel('dashboard');
            return;
        }
    }

    showScreen('login-screen');
}

// =============================================================================
// Utilities
// =============================================================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// Event Listeners
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Login form
    document.getElementById('login-form').addEventListener('submit', handleLogin);

    // Logout button
    document.getElementById('logout-btn').addEventListener('click', logout);

    // Navigation
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            showPanel(link.dataset.panel);
        });
    });

    // Users panel
    document.getElementById('user-search-btn').addEventListener('click', () => {
        usersPage = 0;
        loadUsers();
    });
    document.getElementById('user-search').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            usersPage = 0;
            loadUsers();
        }
    });
    document.getElementById('include-banned').addEventListener('change', () => {
        usersPage = 0;
        loadUsers();
    });
    document.getElementById('users-prev').addEventListener('click', () => {
        if (usersPage > 0) {
            usersPage--;
            loadUsers();
        }
    });
    document.getElementById('users-next').addEventListener('click', () => {
        usersPage++;
        loadUsers();
    });

    // User modal actions
    document.getElementById('action-ban').addEventListener('click', () => {
        document.getElementById('ban-reason').value = '';
        document.getElementById('ban-duration').value = '';
        showModal('ban-modal');
    });
    document.getElementById('action-unban').addEventListener('click', handleUnbanUser);
    document.getElementById('action-reset-pw').addEventListener('click', handleForcePasswordReset);
    document.getElementById('action-make-admin').addEventListener('click', handleMakeAdmin);
    document.getElementById('action-remove-admin').addEventListener('click', handleRemoveAdmin);
    document.getElementById('action-impersonate').addEventListener('click', handleImpersonate);

    // Ban form
    document.getElementById('ban-form').addEventListener('submit', handleBanUser);

    // Games panel
    document.getElementById('refresh-games-btn').addEventListener('click', loadGames);

    // End game form
    document.getElementById('end-game-form').addEventListener('submit', handleEndGame);

    // Invites panel
    document.getElementById('create-invite-btn').addEventListener('click', handleCreateInvite);
    document.getElementById('include-expired').addEventListener('change', loadInvites);

    // Audit panel
    document.getElementById('audit-filter-btn').addEventListener('click', () => {
        auditPage = 0;
        loadAuditLog();
    });
    document.getElementById('audit-prev').addEventListener('click', () => {
        if (auditPage > 0) {
            auditPage--;
            loadAuditLog();
        }
    });
    document.getElementById('audit-next').addEventListener('click', () => {
        auditPage++;
        loadAuditLog();
    });

    // Modal close buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', hideAllModals);
    });

    // Close modal on overlay click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                hideAllModals();
            }
        });
    });

    // Delegated click handlers for dynamically-created buttons
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;

        const action = btn.dataset.action;
        if (action === 'view-user') viewUser(btn.dataset.id);
        else if (action === 'end-game') promptEndGame(btn.dataset.id);
        else if (action === 'copy-invite') copyInviteLink(btn.dataset.code);
        else if (action === 'revoke-invite') promptRevokeInvite(btn.dataset.code);
    });

    // Check auth on load
    checkAuth();
});
