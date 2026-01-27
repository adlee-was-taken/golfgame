# V2-05: Stats & Leaderboards

## Overview

This document covers player statistics aggregation and leaderboard systems.

**Dependencies:** V2-03 (User Accounts), V2-01 (Events for aggregation)
**Dependents:** None (end feature)

---

## Goals

1. Aggregate player statistics from game events
2. Create leaderboard views (by wins, by average score, etc.)
3. Background worker for stats processing
4. Leaderboard API endpoints
5. Leaderboard UI in client
6. Achievement/badge system (stretch goal)

---

## Database Schema

```sql
-- migrations/versions/004_stats_leaderboards.sql

-- Player statistics (aggregated from events)
CREATE TABLE player_stats (
    user_id UUID PRIMARY KEY REFERENCES users(id),

    -- Game counts
    games_played INT DEFAULT 0,
    games_won INT DEFAULT 0,
    games_vs_humans INT DEFAULT 0,
    games_won_vs_humans INT DEFAULT 0,

    -- Round stats
    rounds_played INT DEFAULT 0,
    rounds_won INT DEFAULT 0,
    total_points INT DEFAULT 0,  -- Sum of all round scores (lower is better)

    -- Best/worst
    best_round_score INT,
    worst_round_score INT,
    best_game_score INT,  -- Lowest total in a game

    -- Achievements
    knockouts INT DEFAULT 0,       -- Times going out first
    perfect_rounds INT DEFAULT 0,  -- Score of 0 or less
    wolfpacks INT DEFAULT 0,       -- Four jacks achieved

    -- Streaks
    current_win_streak INT DEFAULT 0,
    best_win_streak INT DEFAULT 0,

    -- Timestamps
    first_game_at TIMESTAMPTZ,
    last_game_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Stats processing queue (for background worker)
CREATE TABLE stats_queue (
    id BIGSERIAL PRIMARY KEY,
    game_id UUID NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    error_message TEXT
);

-- Leaderboard cache (refreshed periodically)
CREATE MATERIALIZED VIEW leaderboard_overall AS
SELECT
    u.id as user_id,
    u.username,
    s.games_played,
    s.games_won,
    ROUND(s.games_won::numeric / NULLIF(s.games_played, 0) * 100, 1) as win_rate,
    s.rounds_won,
    ROUND(s.total_points::numeric / NULLIF(s.rounds_played, 0), 1) as avg_score,
    s.best_round_score,
    s.knockouts,
    s.best_win_streak,
    s.last_game_at
FROM player_stats s
JOIN users u ON s.user_id = u.id
WHERE s.games_played >= 5  -- Minimum games for ranking
AND u.deleted_at IS NULL
AND u.is_banned = false;

CREATE UNIQUE INDEX idx_leaderboard_overall_user ON leaderboard_overall(user_id);
CREATE INDEX idx_leaderboard_overall_wins ON leaderboard_overall(games_won DESC);
CREATE INDEX idx_leaderboard_overall_rate ON leaderboard_overall(win_rate DESC);
CREATE INDEX idx_leaderboard_overall_score ON leaderboard_overall(avg_score ASC);

-- Achievements/badges
CREATE TABLE achievements (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    category VARCHAR(50),  -- games, rounds, special
    threshold INT,  -- e.g., 10 for "Win 10 games"
    sort_order INT DEFAULT 0
);

CREATE TABLE user_achievements (
    user_id UUID REFERENCES users(id),
    achievement_id VARCHAR(50) REFERENCES achievements(id),
    earned_at TIMESTAMPTZ DEFAULT NOW(),
    game_id UUID,  -- Game where it was earned (optional)
    PRIMARY KEY (user_id, achievement_id)
);

-- Seed achievements
INSERT INTO achievements (id, name, description, icon, category, threshold, sort_order) VALUES
('first_win', 'First Victory', 'Win your first game', '🏆', 'games', 1, 1),
('win_10', 'Rising Star', 'Win 10 games', '⭐', 'games', 10, 2),
('win_50', 'Veteran', 'Win 50 games', '🎖️', 'games', 50, 3),
('win_100', 'Champion', 'Win 100 games', '👑', 'games', 100, 4),
('perfect_round', 'Perfect', 'Score 0 or less in a round', '💎', 'rounds', 1, 10),
('negative_round', 'Below Zero', 'Score negative in a round', '❄️', 'rounds', 1, 11),
('knockout_10', 'Closer', 'Go out first 10 times', '🚪', 'special', 10, 20),
('wolfpack', 'Wolfpack', 'Get all 4 Jacks', '🐺', 'special', 1, 21),
('streak_5', 'Hot Streak', 'Win 5 games in a row', '🔥', 'special', 5, 30),
('streak_10', 'Unstoppable', 'Win 10 games in a row', '⚡', 'special', 10, 31);

-- Indexes
CREATE INDEX idx_stats_queue_pending ON stats_queue(status, created_at)
    WHERE status = 'pending';
CREATE INDEX idx_user_achievements_user ON user_achievements(user_id);
```

---

## Stats Service

```python
# server/services/stats_service.py
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
import asyncpg

from stores.event_store import EventStore
from models.events import EventType


@dataclass
class PlayerStats:
    user_id: str
    username: str
    games_played: int
    games_won: int
    win_rate: float
    rounds_played: int
    rounds_won: int
    avg_score: float
    best_round_score: Optional[int]
    knockouts: int
    best_win_streak: int
    achievements: List[str]


@dataclass
class LeaderboardEntry:
    rank: int
    user_id: str
    username: str
    value: float  # The metric being ranked by
    games_played: int
    secondary_value: Optional[float] = None


class StatsService:
    """Player statistics and leaderboards."""

    def __init__(self, db_pool: asyncpg.Pool, event_store: EventStore):
        self.db = db_pool
        self.event_store = event_store

    # --- Stats Queries ---

    async def get_player_stats(self, user_id: str) -> Optional[PlayerStats]:
        """Get stats for a specific player."""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT s.*, u.username,
                    ROUND(s.games_won::numeric / NULLIF(s.games_played, 0) * 100, 1) as win_rate,
                    ROUND(s.total_points::numeric / NULLIF(s.rounds_played, 0), 1) as avg_score
                FROM player_stats s
                JOIN users u ON s.user_id = u.id
                WHERE s.user_id = $1
            """, user_id)

            if not row:
                return None

            # Get achievements
            achievements = await conn.fetch("""
                SELECT achievement_id FROM user_achievements
                WHERE user_id = $1
            """, user_id)

            return PlayerStats(
                user_id=row["user_id"],
                username=row["username"],
                games_played=row["games_played"],
                games_won=row["games_won"],
                win_rate=float(row["win_rate"] or 0),
                rounds_played=row["rounds_played"],
                rounds_won=row["rounds_won"],
                avg_score=float(row["avg_score"] or 0),
                best_round_score=row["best_round_score"],
                knockouts=row["knockouts"],
                best_win_streak=row["best_win_streak"],
                achievements=[a["achievement_id"] for a in achievements],
            )

    async def get_leaderboard(
        self,
        metric: str = "wins",
        limit: int = 50,
        offset: int = 0,
    ) -> List[LeaderboardEntry]:
        """
        Get leaderboard by metric.

        Metrics: wins, win_rate, avg_score, knockouts, streak
        """
        order_map = {
            "wins": ("games_won", "DESC"),
            "win_rate": ("win_rate", "DESC"),
            "avg_score": ("avg_score", "ASC"),  # Lower is better
            "knockouts": ("knockouts", "DESC"),
            "streak": ("best_win_streak", "DESC"),
        }

        if metric not in order_map:
            metric = "wins"

        column, direction = order_map[metric]

        async with self.db.acquire() as conn:
            # Use materialized view for performance
            rows = await conn.fetch(f"""
                SELECT
                    user_id, username, games_played, games_won,
                    win_rate, avg_score, knockouts, best_win_streak,
                    ROW_NUMBER() OVER (ORDER BY {column} {direction}) as rank
                FROM leaderboard_overall
                ORDER BY {column} {direction}
                LIMIT $1 OFFSET $2
            """, limit, offset)

            return [
                LeaderboardEntry(
                    rank=row["rank"],
                    user_id=row["user_id"],
                    username=row["username"],
                    value=float(row[column] or 0),
                    games_played=row["games_played"],
                    secondary_value=float(row["win_rate"] or 0) if metric != "win_rate" else None,
                )
                for row in rows
            ]

    async def get_player_rank(self, user_id: str, metric: str = "wins") -> Optional[int]:
        """Get a player's rank on a leaderboard."""
        order_map = {
            "wins": ("games_won", "DESC"),
            "win_rate": ("win_rate", "DESC"),
            "avg_score": ("avg_score", "ASC"),
        }

        if metric not in order_map:
            return None

        column, direction = order_map[metric]

        async with self.db.acquire() as conn:
            row = await conn.fetchrow(f"""
                SELECT rank FROM (
                    SELECT user_id, ROW_NUMBER() OVER (ORDER BY {column} {direction}) as rank
                    FROM leaderboard_overall
                ) ranked
                WHERE user_id = $1
            """, user_id)

            return row["rank"] if row else None

    async def refresh_leaderboard(self) -> None:
        """Refresh the materialized view."""
        async with self.db.acquire() as conn:
            await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY leaderboard_overall")

    # --- Achievement Queries ---

    async def get_achievements(self) -> List[dict]:
        """Get all available achievements."""
        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, description, icon, category, threshold
                FROM achievements
                ORDER BY sort_order
            """)

            return [dict(row) for row in rows]

    async def get_user_achievements(self, user_id: str) -> List[dict]:
        """Get achievements earned by a user."""
        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT a.id, a.name, a.description, a.icon, ua.earned_at
                FROM user_achievements ua
                JOIN achievements a ON ua.achievement_id = a.id
                WHERE ua.user_id = $1
                ORDER BY ua.earned_at DESC
            """, user_id)

            return [dict(row) for row in rows]

    # --- Stats Processing ---

    async def process_game_end(self, game_id: str) -> None:
        """
        Process a completed game and update player stats.
        Called by background worker or directly after game ends.
        """
        # Get game events
        events = await self.event_store.get_events(game_id)

        if not events:
            return

        # Extract game data from events
        game_data = self._extract_game_data(events)

        if not game_data:
            return

        async with self.db.acquire() as conn:
            async with conn.transaction():
                for player_id, player_data in game_data["players"].items():
                    # Skip CPU players (they don't have user accounts)
                    if player_data.get("is_cpu"):
                        continue

                    # Ensure stats row exists
                    await conn.execute("""
                        INSERT INTO player_stats (user_id)
                        VALUES ($1)
                        ON CONFLICT (user_id) DO NOTHING
                    """, player_id)

                    # Update stats
                    is_winner = player_id == game_data["winner_id"]
                    total_score = player_data["total_score"]
                    rounds_won = player_data["rounds_won"]

                    await conn.execute("""
                        UPDATE player_stats SET
                            games_played = games_played + 1,
                            games_won = games_won + $2,
                            rounds_played = rounds_played + $3,
                            rounds_won = rounds_won + $4,
                            total_points = total_points + $5,
                            knockouts = knockouts + $6,
                            best_round_score = LEAST(best_round_score, $7),
                            worst_round_score = GREATEST(worst_round_score, $8),
                            best_game_score = LEAST(best_game_score, $5),
                            current_win_streak = CASE WHEN $2 = 1 THEN current_win_streak + 1 ELSE 0 END,
                            best_win_streak = GREATEST(best_win_streak,
                                CASE WHEN $2 = 1 THEN current_win_streak + 1 ELSE best_win_streak END),
                            first_game_at = COALESCE(first_game_at, NOW()),
                            last_game_at = NOW(),
                            updated_at = NOW()
                        WHERE user_id = $1
                    """,
                        player_id,
                        1 if is_winner else 0,
                        game_data["num_rounds"],
                        rounds_won,
                        total_score,
                        player_data.get("knockouts", 0),
                        player_data.get("best_round", total_score),
                        player_data.get("worst_round", total_score),
                    )

                    # Check for new achievements
                    await self._check_achievements(conn, player_id, game_id, player_data, is_winner)

    def _extract_game_data(self, events) -> Optional[dict]:
        """Extract game data from events."""
        data = {
            "players": {},
            "num_rounds": 0,
            "winner_id": None,
        }

        for event in events:
            if event.event_type == EventType.PLAYER_JOINED:
                data["players"][event.player_id] = {
                    "is_cpu": event.data.get("is_cpu", False),
                    "total_score": 0,
                    "rounds_won": 0,
                    "knockouts": 0,
                    "best_round": None,
                    "worst_round": None,
                }

            elif event.event_type == EventType.ROUND_ENDED:
                data["num_rounds"] += 1
                scores = event.data.get("scores", {})
                winner_id = event.data.get("winner_id")

                for player_id, score in scores.items():
                    if player_id in data["players"]:
                        p = data["players"][player_id]
                        p["total_score"] += score

                        if p["best_round"] is None or score < p["best_round"]:
                            p["best_round"] = score
                        if p["worst_round"] is None or score > p["worst_round"]:
                            p["worst_round"] = score

                        if player_id == winner_id:
                            p["rounds_won"] += 1

                # Track who went out first (finisher)
                # This would need to be tracked in events

            elif event.event_type == EventType.GAME_ENDED:
                data["winner_id"] = event.data.get("winner_id")

        return data if data["num_rounds"] > 0 else None

    async def _check_achievements(
        self,
        conn: asyncpg.Connection,
        user_id: str,
        game_id: str,
        player_data: dict,
        is_winner: bool,
    ) -> List[str]:
        """Check and award new achievements."""
        new_achievements = []

        # Get current stats
        stats = await conn.fetchrow("""
            SELECT games_won, knockouts, best_win_streak, current_win_streak
            FROM player_stats
            WHERE user_id = $1
        """, user_id)

        if not stats:
            return []

        # Get already earned achievements
        earned = await conn.fetch("""
            SELECT achievement_id FROM user_achievements WHERE user_id = $1
        """, user_id)
        earned_ids = {e["achievement_id"] for e in earned}

        # Check win milestones
        wins = stats["games_won"]
        if wins >= 1 and "first_win" not in earned_ids:
            new_achievements.append("first_win")
        if wins >= 10 and "win_10" not in earned_ids:
            new_achievements.append("win_10")
        if wins >= 50 and "win_50" not in earned_ids:
            new_achievements.append("win_50")
        if wins >= 100 and "win_100" not in earned_ids:
            new_achievements.append("win_100")

        # Check streak achievements
        streak = stats["current_win_streak"]
        if streak >= 5 and "streak_5" not in earned_ids:
            new_achievements.append("streak_5")
        if streak >= 10 and "streak_10" not in earned_ids:
            new_achievements.append("streak_10")

        # Check knockout achievements
        if stats["knockouts"] >= 10 and "knockout_10" not in earned_ids:
            new_achievements.append("knockout_10")

        # Check round-specific achievements
        if player_data.get("best_round") is not None:
            if player_data["best_round"] <= 0 and "perfect_round" not in earned_ids:
                new_achievements.append("perfect_round")
            if player_data["best_round"] < 0 and "negative_round" not in earned_ids:
                new_achievements.append("negative_round")

        # Award new achievements
        for achievement_id in new_achievements:
            await conn.execute("""
                INSERT INTO user_achievements (user_id, achievement_id, game_id)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
            """, user_id, achievement_id, game_id)

        return new_achievements
```

---

## Background Worker

```python
# server/workers/stats_worker.py
import asyncio
from datetime import datetime, timedelta
import asyncpg
from arq import create_pool
from arq.connections import RedisSettings

from services.stats_service import StatsService
from stores.event_store import EventStore


async def process_stats_queue(ctx):
    """Process pending games in the stats queue."""
    db: asyncpg.Pool = ctx["db_pool"]
    stats_service: StatsService = ctx["stats_service"]

    async with db.acquire() as conn:
        # Get pending games
        games = await conn.fetch("""
            SELECT id, game_id FROM stats_queue
            WHERE status = 'pending'
            ORDER BY created_at
            LIMIT 100
        """)

        for game in games:
            try:
                # Mark as processing
                await conn.execute("""
                    UPDATE stats_queue SET status = 'processing' WHERE id = $1
                """, game["id"])

                # Process
                await stats_service.process_game_end(game["game_id"])

                # Mark complete
                await conn.execute("""
                    UPDATE stats_queue
                    SET status = 'completed', processed_at = NOW()
                    WHERE id = $1
                """, game["id"])

            except Exception as e:
                # Mark failed
                await conn.execute("""
                    UPDATE stats_queue
                    SET status = 'failed', error_message = $2
                    WHERE id = $1
                """, game["id"], str(e))


async def refresh_leaderboard(ctx):
    """Refresh the materialized leaderboard view."""
    stats_service: StatsService = ctx["stats_service"]
    await stats_service.refresh_leaderboard()


async def cleanup_old_queue_entries(ctx):
    """Clean up old processed queue entries."""
    db: asyncpg.Pool = ctx["db_pool"]

    async with db.acquire() as conn:
        await conn.execute("""
            DELETE FROM stats_queue
            WHERE status IN ('completed', 'failed')
            AND processed_at < NOW() - INTERVAL '7 days'
        """)


class WorkerSettings:
    """arq worker settings."""

    functions = [
        process_stats_queue,
        refresh_leaderboard,
        cleanup_old_queue_entries,
    ]

    cron_jobs = [
        # Process queue every minute
        cron(process_stats_queue, minute={0, 15, 30, 45}),
        # Refresh leaderboard every 5 minutes
        cron(refresh_leaderboard, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        # Cleanup daily
        cron(cleanup_old_queue_entries, hour=3, minute=0),
    ]

    redis_settings = RedisSettings()

    @staticmethod
    async def on_startup(ctx):
        """Initialize worker context."""
        ctx["db_pool"] = await asyncpg.create_pool(DATABASE_URL)
        ctx["event_store"] = EventStore(ctx["db_pool"])
        ctx["stats_service"] = StatsService(ctx["db_pool"], ctx["event_store"])

    @staticmethod
    async def on_shutdown(ctx):
        """Cleanup worker context."""
        await ctx["db_pool"].close()
```

---

## API Endpoints

```python
# server/routers/stats.py
from fastapi import APIRouter, Depends, Query
from typing import Optional

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/leaderboard")
async def get_leaderboard(
    metric: str = Query("wins", regex="^(wins|win_rate|avg_score|knockouts|streak)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: StatsService = Depends(get_stats_service),
):
    """Get leaderboard by metric."""
    entries = await service.get_leaderboard(metric, limit, offset)
    return {
        "metric": metric,
        "entries": [
            {
                "rank": e.rank,
                "user_id": e.user_id,
                "username": e.username,
                "value": e.value,
                "games_played": e.games_played,
            }
            for e in entries
        ],
    }


@router.get("/players/{user_id}")
async def get_player_stats(
    user_id: str,
    service: StatsService = Depends(get_stats_service),
):
    """Get stats for a specific player."""
    stats = await service.get_player_stats(user_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Player not found")

    return {
        "user_id": stats.user_id,
        "username": stats.username,
        "games_played": stats.games_played,
        "games_won": stats.games_won,
        "win_rate": stats.win_rate,
        "rounds_played": stats.rounds_played,
        "rounds_won": stats.rounds_won,
        "avg_score": stats.avg_score,
        "best_round_score": stats.best_round_score,
        "knockouts": stats.knockouts,
        "best_win_streak": stats.best_win_streak,
        "achievements": stats.achievements,
    }


@router.get("/players/{user_id}/rank")
async def get_player_rank(
    user_id: str,
    metric: str = "wins",
    service: StatsService = Depends(get_stats_service),
):
    """Get player's rank on a leaderboard."""
    rank = await service.get_player_rank(user_id, metric)
    return {"user_id": user_id, "metric": metric, "rank": rank}


@router.get("/me")
async def get_my_stats(
    user: User = Depends(get_current_user),
    service: StatsService = Depends(get_stats_service),
):
    """Get current user's stats."""
    stats = await service.get_player_stats(user.id)
    if not stats:
        return {
            "games_played": 0,
            "games_won": 0,
            "achievements": [],
        }
    return stats.__dict__


@router.get("/achievements")
async def get_achievements(
    service: StatsService = Depends(get_stats_service),
):
    """Get all available achievements."""
    return {"achievements": await service.get_achievements()}


@router.get("/players/{user_id}/achievements")
async def get_user_achievements(
    user_id: str,
    service: StatsService = Depends(get_stats_service),
):
    """Get achievements earned by a player."""
    return {"achievements": await service.get_user_achievements(user_id)}
```

---

## Frontend Integration

```javascript
// client/components/leaderboard.js

class LeaderboardComponent {
    constructor(container) {
        this.container = container;
        this.metric = 'wins';
        this.render();
    }

    async fetchLeaderboard() {
        const response = await fetch(`/api/stats/leaderboard?metric=${this.metric}&limit=50`);
        return response.json();
    }

    async render() {
        const data = await this.fetchLeaderboard();

        this.container.innerHTML = `
            <div class="leaderboard">
                <div class="leaderboard-tabs">
                    <button class="tab ${this.metric === 'wins' ? 'active' : ''}" data-metric="wins">Wins</button>
                    <button class="tab ${this.metric === 'win_rate' ? 'active' : ''}" data-metric="win_rate">Win Rate</button>
                    <button class="tab ${this.metric === 'avg_score' ? 'active' : ''}" data-metric="avg_score">Avg Score</button>
                </div>
                <table class="leaderboard-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Player</th>
                            <th>${this.getMetricLabel()}</th>
                            <th>Games</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.entries.map(e => `
                            <tr>
                                <td class="rank">${this.getRankBadge(e.rank)}</td>
                                <td class="username">${e.username}</td>
                                <td class="value">${this.formatValue(e.value)}</td>
                                <td class="games">${e.games_played}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

        // Bind tab clicks
        this.container.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                this.metric = tab.dataset.metric;
                this.render();
            });
        });
    }

    getMetricLabel() {
        const labels = {
            wins: 'Wins',
            win_rate: 'Win %',
            avg_score: 'Avg Score',
        };
        return labels[this.metric] || this.metric;
    }

    formatValue(value) {
        if (this.metric === 'win_rate') return `${value}%`;
        if (this.metric === 'avg_score') return value.toFixed(1);
        return value;
    }

    getRankBadge(rank) {
        if (rank === 1) return '🥇';
        if (rank === 2) return '🥈';
        if (rank === 3) return '🥉';
        return rank;
    }
}
```

---

## Acceptance Criteria

1. **Stats Aggregation**
   - [ ] Stats calculated from game events
   - [ ] Games played/won tracked
   - [ ] Rounds played/won tracked
   - [ ] Best/worst scores tracked
   - [ ] Win streaks tracked
   - [ ] Knockouts tracked

2. **Leaderboards**
   - [ ] Leaderboard by wins
   - [ ] Leaderboard by win rate
   - [ ] Leaderboard by average score
   - [ ] Minimum games requirement
   - [ ] Pagination working
   - [ ] Materialized view refreshes

3. **Background Worker**
   - [ ] Queue processing works
   - [ ] Failed jobs retried
   - [ ] Leaderboard auto-refreshes
   - [ ] Old entries cleaned up

4. **Achievements**
   - [ ] Achievement definitions in DB
   - [ ] Achievements awarded correctly
   - [ ] Achievement progress tracked
   - [ ] Achievement UI displays

5. **API**
   - [ ] GET /leaderboard works
   - [ ] GET /players/{id} works
   - [ ] GET /me works
   - [ ] GET /achievements works

6. **UI**
   - [ ] Leaderboard displays
   - [ ] Tabs switch metrics
   - [ ] Player profiles show stats
   - [ ] Achievements display

---

## Implementation Order

1. Create database migrations
2. Implement stats processing logic
3. Add stats queue integration
4. Set up background worker
5. Implement leaderboard queries
6. Create API endpoints
7. Build leaderboard UI
8. Add achievements system
9. Test full flow

---

## Notes

- Materialized views are great for leaderboards but need periodic refresh
- Consider caching hot leaderboard data in Redis
- Achievement checking should be efficient (batch checks)
- Stats processing is async - don't block game completion
- Consider separate "vs humans only" stats in future
