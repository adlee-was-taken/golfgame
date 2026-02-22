"""
Stats service for Golf game leaderboards and achievements.

Provides player statistics aggregation, leaderboard queries, and achievement tracking.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

import asyncpg

from stores.event_store import EventStore
from models.events import EventType
from game import GameOptions

logger = logging.getLogger(__name__)


@dataclass
class PlayerStats:
    """Full player statistics."""
    user_id: str
    username: str
    games_played: int = 0
    games_won: int = 0
    win_rate: float = 0.0
    rounds_played: int = 0
    rounds_won: int = 0
    avg_score: float = 0.0
    best_round_score: Optional[int] = None
    worst_round_score: Optional[int] = None
    knockouts: int = 0
    perfect_rounds: int = 0
    wolfpacks: int = 0
    current_win_streak: int = 0
    best_win_streak: int = 0
    rating: float = 1500.0
    rating_deviation: float = 350.0
    first_game_at: Optional[datetime] = None
    last_game_at: Optional[datetime] = None
    achievements: List[str] = field(default_factory=list)


@dataclass
class LeaderboardEntry:
    """Single entry on a leaderboard."""
    rank: int
    user_id: str
    username: str
    value: float
    games_played: int
    secondary_value: Optional[float] = None


@dataclass
class Achievement:
    """Achievement definition."""
    id: str
    name: str
    description: str
    icon: str
    category: str
    threshold: int


@dataclass
class UserAchievement:
    """Achievement earned by a user."""
    id: str
    name: str
    description: str
    icon: str
    earned_at: datetime
    game_id: Optional[str] = None


class StatsService:
    """
    Player statistics and leaderboards service.

    Provides methods for:
    - Querying player stats
    - Fetching leaderboards by various metrics
    - Processing game completion for stats aggregation
    - Achievement checking and awarding
    """

    def __init__(self, pool: asyncpg.Pool, event_store: Optional[EventStore] = None):
        """
        Initialize stats service.

        Args:
            pool: asyncpg connection pool.
            event_store: Optional EventStore for event-based stats processing.
        """
        self.pool = pool
        self.event_store = event_store

    # -------------------------------------------------------------------------
    # Stats Queries
    # -------------------------------------------------------------------------

    async def get_player_stats(self, user_id: str) -> Optional[PlayerStats]:
        """
        Get full stats for a specific player.

        Args:
            user_id: User UUID.

        Returns:
            PlayerStats or None if player not found.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT s.*, u.username,
                    ROUND(s.games_won::numeric / NULLIF(s.games_played, 0) * 100, 1) as win_rate,
                    ROUND(s.total_points::numeric / NULLIF(s.total_rounds, 0), 1) as avg_score_calc
                FROM player_stats s
                JOIN users_v2 u ON s.user_id = u.id
                WHERE s.user_id = $1
            """, user_id)

            if not row:
                # Check if user exists but has no stats
                user_row = await conn.fetchrow(
                    "SELECT username FROM users_v2 WHERE id = $1",
                    user_id
                )
                if user_row:
                    return PlayerStats(
                        user_id=user_id,
                        username=user_row["username"],
                    )
                return None

            # Get achievements
            achievements = await conn.fetch("""
                SELECT achievement_id FROM user_achievements
                WHERE user_id = $1
            """, user_id)

            return PlayerStats(
                user_id=str(row["user_id"]),
                username=row["username"],
                games_played=row["games_played"] or 0,
                games_won=row["games_won"] or 0,
                win_rate=float(row["win_rate"] or 0),
                rounds_played=row["total_rounds"] or 0,
                rounds_won=row["rounds_won"] or 0,
                avg_score=float(row["avg_score_calc"] or 0),
                best_round_score=row["best_score"],
                worst_round_score=row["worst_score"],
                knockouts=row["knockouts"] or 0,
                perfect_rounds=row["perfect_rounds"] or 0,
                wolfpacks=row["wolfpacks"] or 0,
                current_win_streak=row["current_win_streak"] or 0,
                best_win_streak=row["best_win_streak"] or 0,
                rating=float(row["rating"]) if row.get("rating") else 1500.0,
                rating_deviation=float(row["rating_deviation"]) if row.get("rating_deviation") else 350.0,
                first_game_at=row["first_game_at"].replace(tzinfo=timezone.utc) if row["first_game_at"] else None,
                last_game_at=row["last_game_at"].replace(tzinfo=timezone.utc) if row["last_game_at"] else None,
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

        Args:
            metric: Ranking metric - wins, win_rate, avg_score, knockouts, streak.
            limit: Maximum entries to return.
            offset: Pagination offset.

        Returns:
            List of LeaderboardEntry sorted by metric.
        """
        order_map = {
            "wins": ("games_won", "DESC"),
            "win_rate": ("win_rate", "DESC"),
            "avg_score": ("avg_score", "ASC"),  # Lower is better
            "knockouts": ("knockouts", "DESC"),
            "streak": ("best_win_streak", "DESC"),
            "rating": ("rating", "DESC"),
        }

        if metric not in order_map:
            metric = "wins"

        column, direction = order_map[metric]

        async with self.pool.acquire() as conn:
            # Check if materialized view exists
            view_exists = await conn.fetchval(
                "SELECT 1 FROM pg_matviews WHERE matviewname = 'leaderboard_overall'"
            )

            if view_exists:
                # Use materialized view for performance
                rows = await conn.fetch(f"""
                    SELECT
                        user_id, username, games_played, games_won,
                        win_rate, avg_score, knockouts, best_win_streak,
                        COALESCE(rating, 1500) as rating,
                        ROW_NUMBER() OVER (ORDER BY {column} {direction}) as rank
                    FROM leaderboard_overall
                    ORDER BY {column} {direction}
                    LIMIT $1 OFFSET $2
                """, limit, offset)
            else:
                # Fall back to direct query
                rows = await conn.fetch(f"""
                    SELECT
                        s.user_id, u.username, s.games_played, s.games_won,
                        ROUND(s.games_won::numeric / NULLIF(s.games_played, 0) * 100, 1) as win_rate,
                        ROUND(s.total_points::numeric / NULLIF(s.total_rounds, 0), 1) as avg_score,
                        s.knockouts, s.best_win_streak,
                        COALESCE(s.rating, 1500) as rating,
                        ROW_NUMBER() OVER (ORDER BY {column} {direction}) as rank
                    FROM player_stats s
                    JOIN users_v2 u ON s.user_id = u.id
                    WHERE s.games_played >= 5
                    AND u.deleted_at IS NULL
                    AND (u.is_banned = false OR u.is_banned IS NULL)
                    ORDER BY {column} {direction}
                    LIMIT $1 OFFSET $2
                """, limit, offset)

            return [
                LeaderboardEntry(
                    rank=row["rank"],
                    user_id=str(row["user_id"]),
                    username=row["username"],
                    value=float(row[column] or 0),
                    games_played=row["games_played"],
                    secondary_value=float(row["win_rate"] or 0) if metric != "win_rate" else None,
                )
                for row in rows
            ]

    async def get_player_rank(self, user_id: str, metric: str = "wins") -> Optional[int]:
        """
        Get a player's rank on a leaderboard.

        Args:
            user_id: User UUID.
            metric: Ranking metric.

        Returns:
            Rank number or None if not ranked (< 5 games or not found).
        """
        order_map = {
            "wins": ("games_won", "DESC"),
            "win_rate": ("win_rate", "DESC"),
            "avg_score": ("avg_score", "ASC"),
            "knockouts": ("knockouts", "DESC"),
            "streak": ("best_win_streak", "DESC"),
        }

        if metric not in order_map:
            return None

        column, direction = order_map[metric]

        async with self.pool.acquire() as conn:
            # Check if user qualifies (5+ games)
            games = await conn.fetchval(
                "SELECT games_played FROM player_stats WHERE user_id = $1",
                user_id
            )
            if not games or games < 5:
                return None

            view_exists = await conn.fetchval(
                "SELECT 1 FROM pg_matviews WHERE matviewname = 'leaderboard_overall'"
            )

            if view_exists:
                row = await conn.fetchrow(f"""
                    SELECT rank FROM (
                        SELECT user_id, ROW_NUMBER() OVER (ORDER BY {column} {direction}) as rank
                        FROM leaderboard_overall
                    ) ranked
                    WHERE user_id = $1
                """, user_id)
            else:
                row = await conn.fetchrow(f"""
                    SELECT rank FROM (
                        SELECT s.user_id, ROW_NUMBER() OVER (ORDER BY {column} {direction}) as rank
                        FROM player_stats s
                        JOIN users_v2 u ON s.user_id = u.id
                        WHERE s.games_played >= 5
                        AND u.deleted_at IS NULL
                        AND (u.is_banned = false OR u.is_banned IS NULL)
                    ) ranked
                    WHERE user_id = $1
                """, user_id)

            return row["rank"] if row else None

    async def refresh_leaderboard(self) -> bool:
        """
        Refresh the materialized leaderboard view.

        Returns:
            True if refresh succeeded.
        """
        async with self.pool.acquire() as conn:
            try:
                # Check if view exists
                view_exists = await conn.fetchval(
                    "SELECT 1 FROM pg_matviews WHERE matviewname = 'leaderboard_overall'"
                )
                if view_exists:
                    await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY leaderboard_overall")
                    logger.info("Refreshed leaderboard materialized view")
                return True
            except Exception as e:
                logger.error(f"Failed to refresh leaderboard: {e}")
                return False

    # -------------------------------------------------------------------------
    # Achievement Queries
    # -------------------------------------------------------------------------

    async def get_achievements(self) -> List[Achievement]:
        """Get all available achievements."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, description, icon, category, threshold
                FROM achievements
                ORDER BY sort_order
            """)

            return [
                Achievement(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"] or "",
                    icon=row["icon"] or "",
                    category=row["category"] or "",
                    threshold=row["threshold"] or 0,
                )
                for row in rows
            ]

    async def get_user_achievements(self, user_id: str) -> List[UserAchievement]:
        """
        Get achievements earned by a user.

        Args:
            user_id: User UUID.

        Returns:
            List of earned achievements.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT a.id, a.name, a.description, a.icon, ua.earned_at, ua.game_id
                FROM user_achievements ua
                JOIN achievements a ON ua.achievement_id = a.id
                WHERE ua.user_id = $1
                ORDER BY ua.earned_at DESC
            """, user_id)

            return [
                UserAchievement(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"] or "",
                    icon=row["icon"] or "",
                    earned_at=row["earned_at"].replace(tzinfo=timezone.utc) if row["earned_at"] else datetime.now(timezone.utc),
                    game_id=str(row["game_id"]) if row["game_id"] else None,
                )
                for row in rows
            ]

    # -------------------------------------------------------------------------
    # Stats Processing (Game Completion)
    # -------------------------------------------------------------------------

    async def process_game_end(self, game_id: str) -> List[str]:
        """
        Process a completed game and update player stats.

        Extracts game data from events and updates player_stats table.

        Args:
            game_id: Game UUID.

        Returns:
            List of newly awarded achievement IDs.
        """
        if not self.event_store:
            logger.warning("No event store configured, skipping stats processing")
            return []

        # Get game events
        try:
            events = await self.event_store.get_events(game_id)
        except Exception as e:
            logger.error(f"Failed to get events for game {game_id}: {e}")
            return []

        if not events:
            logger.warning(f"No events found for game {game_id}")
            return []

        # Extract game data from events
        game_data = self._extract_game_data(events)

        if not game_data:
            logger.warning(f"Could not extract game data from events for {game_id}")
            return []

        all_new_achievements = []

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for player_id, player_data in game_data["players"].items():
                    # Skip CPU players (they don't have user accounts)
                    if player_data.get("is_cpu"):
                        continue

                    # Check if this is a valid user UUID
                    try:
                        UUID(player_id)
                    except (ValueError, TypeError):
                        # Not a UUID - likely a websocket session ID, skip
                        continue

                    # Ensure stats row exists
                    await conn.execute("""
                        INSERT INTO player_stats (user_id)
                        VALUES ($1)
                        ON CONFLICT (user_id) DO NOTHING
                    """, player_id)

                    # Calculate values
                    is_winner = player_id == game_data["winner_id"]
                    total_score = player_data["total_score"]
                    rounds_won = player_data["rounds_won"]
                    num_rounds = game_data["num_rounds"]
                    knockouts = player_data.get("knockouts", 0)
                    best_round = player_data.get("best_round")
                    worst_round = player_data.get("worst_round")
                    perfect_rounds = player_data.get("perfect_rounds", 0)
                    wolfpacks = player_data.get("wolfpacks", 0)
                    has_human_opponents = game_data.get("has_human_opponents", False)

                    # Update stats
                    await conn.execute("""
                        UPDATE player_stats SET
                            games_played = games_played + 1,
                            games_won = games_won + $2,
                            total_rounds = total_rounds + $3,
                            rounds_won = rounds_won + $4,
                            total_points = total_points + $5,
                            knockouts = knockouts + $6,
                            perfect_rounds = perfect_rounds + $7,
                            wolfpacks = wolfpacks + $8,
                            best_score = CASE
                                WHEN best_score IS NULL THEN $9
                                WHEN $9 IS NOT NULL AND $9 < best_score THEN $9
                                ELSE best_score
                            END,
                            worst_score = CASE
                                WHEN worst_score IS NULL THEN $10
                                WHEN $10 IS NOT NULL AND $10 > worst_score THEN $10
                                ELSE worst_score
                            END,
                            current_win_streak = CASE WHEN $2 = 1 THEN current_win_streak + 1 ELSE 0 END,
                            best_win_streak = GREATEST(best_win_streak,
                                CASE WHEN $2 = 1 THEN current_win_streak + 1 ELSE best_win_streak END),
                            first_game_at = COALESCE(first_game_at, NOW()),
                            last_game_at = NOW(),
                            games_vs_humans = games_vs_humans + $11,
                            games_won_vs_humans = games_won_vs_humans + $12,
                            updated_at = NOW()
                        WHERE user_id = $1
                    """,
                        player_id,
                        1 if is_winner else 0,
                        num_rounds,
                        rounds_won,
                        total_score,
                        knockouts,
                        perfect_rounds,
                        wolfpacks,
                        best_round,
                        worst_round,
                        1 if has_human_opponents else 0,
                        1 if is_winner and has_human_opponents else 0,
                    )

                    # Check for new achievements
                    new_achievements = await self._check_achievements(
                        conn, player_id, game_id, player_data, is_winner
                    )
                    all_new_achievements.extend(new_achievements)

        logger.info(f"Processed stats for game {game_id}, awarded {len(all_new_achievements)} achievements")
        return all_new_achievements

    def _extract_game_data(self, events) -> Optional[dict]:
        """
        Extract game statistics from event stream.

        Args:
            events: List of GameEvent objects.

        Returns:
            Dict with players, num_rounds, winner_id, etc.
        """
        data = {
            "players": {},
            "num_rounds": 0,
            "winner_id": None,
            "has_human_opponents": False,
        }

        human_count = 0

        for event in events:
            if event.event_type == EventType.PLAYER_JOINED:
                is_cpu = event.data.get("is_cpu", False)
                if not is_cpu:
                    human_count += 1

                data["players"][event.player_id] = {
                    "is_cpu": is_cpu,
                    "total_score": 0,
                    "rounds_won": 0,
                    "knockouts": 0,
                    "perfect_rounds": 0,
                    "wolfpacks": 0,
                    "best_round": None,
                    "worst_round": None,
                }

            elif event.event_type == EventType.ROUND_ENDED:
                data["num_rounds"] += 1
                scores = event.data.get("scores", {})
                finisher_id = event.data.get("finisher_id")

                # Track who went out first (knockout)
                if finisher_id and finisher_id in data["players"]:
                    data["players"][finisher_id]["knockouts"] += 1

                # Find round winner (lowest score)
                if scores:
                    min_score = min(scores.values())
                    for pid, score in scores.items():
                        if pid in data["players"]:
                            p = data["players"][pid]
                            p["total_score"] += score

                            # Track best/worst rounds
                            if p["best_round"] is None or score < p["best_round"]:
                                p["best_round"] = score
                            if p["worst_round"] is None or score > p["worst_round"]:
                                p["worst_round"] = score

                            # Check for perfect round (score <= 0)
                            if score <= 0:
                                p["perfect_rounds"] += 1

                            # Award round win
                            if score == min_score:
                                p["rounds_won"] += 1

                # Check for wolfpack (4 Jacks) in final hands
                final_hands = event.data.get("final_hands", {})
                for pid, hand in final_hands.items():
                    if pid in data["players"]:
                        jack_count = sum(1 for card in hand if card.get("rank") == "J")
                        if jack_count >= 4:
                            data["players"][pid]["wolfpacks"] += 1

            elif event.event_type == EventType.GAME_ENDED:
                data["winner_id"] = event.data.get("winner_id")

        # Mark if there were human opponents
        data["has_human_opponents"] = human_count > 1

        return data if data["num_rounds"] > 0 else None

    @staticmethod
    def _check_win_milestones(stats_row, earned_ids: set) -> List[str]:
        """Check win/streak achievement milestones. Shared by event and legacy paths."""
        new = []
        wins = stats_row["games_won"]
        for threshold, achievement_id in [(1, "first_win"), (10, "win_10"), (50, "win_50"), (100, "win_100")]:
            if wins >= threshold and achievement_id not in earned_ids:
                new.append(achievement_id)
        streak = stats_row["current_win_streak"]
        for threshold, achievement_id in [(5, "streak_5"), (10, "streak_10")]:
            if streak >= threshold and achievement_id not in earned_ids:
                new.append(achievement_id)
        return new

    @staticmethod
    async def _get_earned_ids(conn: asyncpg.Connection, user_id: str) -> set:
        """Get set of already-earned achievement IDs for a user."""
        earned = await conn.fetch(
            "SELECT achievement_id FROM user_achievements WHERE user_id = $1",
            user_id,
        )
        return {e["achievement_id"] for e in earned}

    @staticmethod
    async def _award_achievements(
        conn: asyncpg.Connection,
        user_id: str,
        achievement_ids: List[str],
        game_id: Optional[str] = None,
    ) -> None:
        """Insert achievement records for a user."""
        for achievement_id in achievement_ids:
            try:
                await conn.execute("""
                    INSERT INTO user_achievements (user_id, achievement_id, game_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                """, user_id, achievement_id, game_id)
            except Exception as e:
                logger.error(f"Failed to award achievement {achievement_id}: {e}")

    async def _check_achievements(
        self,
        conn: asyncpg.Connection,
        user_id: str,
        game_id: str,
        player_data: dict,
        is_winner: bool,
    ) -> List[str]:
        """
        Check and award new achievements to a player.

        Args:
            conn: Database connection (within transaction).
            user_id: Player's user ID.
            game_id: Current game ID.
            player_data: Player's data from this game.
            is_winner: Whether player won the game.

        Returns:
            List of newly awarded achievement IDs.
        """
        # Get current stats (after update)
        stats = await conn.fetchrow("""
            SELECT games_won, knockouts, best_win_streak, current_win_streak, perfect_rounds, wolfpacks
            FROM player_stats
            WHERE user_id = $1
        """, user_id)

        if not stats:
            return []

        earned_ids = await self._get_earned_ids(conn, user_id)

        # Win/streak milestones (shared logic)
        new_achievements = self._check_win_milestones(stats, earned_ids)

        # Game-specific achievements (event path only)
        if stats["knockouts"] >= 10 and "knockout_10" not in earned_ids:
            new_achievements.append("knockout_10")

        best_round = player_data.get("best_round")
        if best_round is not None:
            if best_round <= 0 and "perfect_round" not in earned_ids:
                new_achievements.append("perfect_round")
            if best_round < 0 and "negative_round" not in earned_ids:
                new_achievements.append("negative_round")

        if player_data.get("wolfpacks", 0) > 0 and "wolfpack" not in earned_ids:
            new_achievements.append("wolfpack")

        await self._award_achievements(conn, user_id, new_achievements, game_id)
        return new_achievements

    # -------------------------------------------------------------------------
    # Direct Game State Processing (for legacy games without event sourcing)
    # -------------------------------------------------------------------------

    async def process_game_from_state(
        self,
        players: list,
        winner_id: Optional[str],
        num_rounds: int,
        player_user_ids: dict[str, str] = None,
        game_options: Optional[GameOptions] = None,
    ) -> List[str]:
        """
        Process game stats directly from game state (for legacy games).

        This is used when games don't have event sourcing. Stats are updated
        based on final game state. Only standard-rules games count toward
        leaderboard stats.

        Args:
            players: List of game.Player objects with final scores.
            winner_id: Player ID of the winner.
            num_rounds: Total rounds played.
            player_user_ids: Optional mapping of player_id to user_id (for authenticated players).
            game_options: Optional game options to check for standard rules.

        Returns:
            List of newly awarded achievement IDs.
        """
        if not players:
            return []

        # Only track stats for standard-rules games
        if game_options and not game_options.is_standard_rules():
            logger.debug("Skipping stats for non-standard rules game")
            return []

        # Count human players for has_human_opponents calculation
        # For legacy games, we assume all players are human unless otherwise indicated
        human_count = len(players)
        has_human_opponents = human_count > 1

        all_new_achievements = []

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for player in players:
                    # Get user_id - could be the player_id itself if it's a UUID,
                    # or mapped via player_user_ids
                    user_id = None
                    if player_user_ids and player.id in player_user_ids:
                        user_id = player_user_ids[player.id]
                    else:
                        # Try to use player.id as user_id if it looks like a UUID
                        try:
                            UUID(player.id)
                            user_id = player.id
                        except (ValueError, TypeError):
                            # Not a UUID, skip this player
                            continue

                    if not user_id:
                        continue

                    # Ensure stats row exists
                    await conn.execute("""
                        INSERT INTO player_stats (user_id)
                        VALUES ($1)
                        ON CONFLICT (user_id) DO NOTHING
                    """, user_id)

                    is_winner = player.id == winner_id
                    total_score = player.total_score
                    rounds_won = player.rounds_won

                    # We don't have per-round data in legacy mode, so some stats are limited
                    # Use total_score / num_rounds as an approximation for avg round score
                    avg_round_score = total_score / num_rounds if num_rounds > 0 else None

                    # Update stats
                    await conn.execute("""
                        UPDATE player_stats SET
                            games_played = games_played + 1,
                            games_won = games_won + $2,
                            total_rounds = total_rounds + $3,
                            rounds_won = rounds_won + $4,
                            total_points = total_points + $5,
                            best_score = CASE
                                WHEN best_score IS NULL THEN $6
                                WHEN $6 IS NOT NULL AND $6 < best_score THEN $6
                                ELSE best_score
                            END,
                            worst_score = CASE
                                WHEN worst_score IS NULL THEN $7
                                WHEN $7 IS NOT NULL AND $7 > worst_score THEN $7
                                ELSE worst_score
                            END,
                            current_win_streak = CASE WHEN $2 = 1 THEN current_win_streak + 1 ELSE 0 END,
                            best_win_streak = GREATEST(best_win_streak,
                                CASE WHEN $2 = 1 THEN current_win_streak + 1 ELSE best_win_streak END),
                            first_game_at = COALESCE(first_game_at, NOW()),
                            last_game_at = NOW(),
                            games_vs_humans = games_vs_humans + $8,
                            games_won_vs_humans = games_won_vs_humans + $9,
                            updated_at = NOW()
                        WHERE user_id = $1
                    """,
                        user_id,
                        1 if is_winner else 0,
                        num_rounds,
                        rounds_won,
                        total_score,
                        avg_round_score,  # Approximation for best_score
                        avg_round_score,  # Approximation for worst_score
                        1 if has_human_opponents else 0,
                        1 if is_winner and has_human_opponents else 0,
                    )

                    # Check achievements (limited data in legacy mode)
                    new_achievements = await self._check_achievements_legacy(
                        conn, user_id, is_winner
                    )
                    all_new_achievements.extend(new_achievements)

        logger.info(f"Processed stats for legacy game with {len(players)} players")
        return all_new_achievements

    async def _check_achievements_legacy(
        self,
        conn: asyncpg.Connection,
        user_id: str,
        is_winner: bool,
    ) -> List[str]:
        """
        Check and award achievements for legacy games (limited data).

        Only checks win-based achievements since we don't have round-level data.
        """
        stats = await conn.fetchrow("""
            SELECT games_won, current_win_streak FROM player_stats
            WHERE user_id = $1
        """, user_id)

        if not stats:
            return []

        earned_ids = await self._get_earned_ids(conn, user_id)
        new_achievements = self._check_win_milestones(stats, earned_ids)
        await self._award_achievements(conn, user_id, new_achievements)
        return new_achievements

    # -------------------------------------------------------------------------
    # Stats Queue Management
    # -------------------------------------------------------------------------

    async def queue_game_for_processing(self, game_id: str) -> int:
        """
        Add a game to the stats processing queue.

        Args:
            game_id: Game UUID.

        Returns:
            Queue entry ID.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO stats_queue (game_id)
                VALUES ($1)
                RETURNING id
            """, game_id)
            return row["id"]

    async def process_pending_queue(self, limit: int = 100) -> int:
        """
        Process pending games in the stats queue.

        Args:
            limit: Maximum games to process.

        Returns:
            Number of games processed.
        """
        processed = 0

        async with self.pool.acquire() as conn:
            # Get pending games
            games = await conn.fetch("""
                SELECT id, game_id FROM stats_queue
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT $1
            """, limit)

            for game in games:
                try:
                    # Mark as processing
                    await conn.execute("""
                        UPDATE stats_queue SET status = 'processing' WHERE id = $1
                    """, game["id"])

                    # Process
                    await self.process_game_end(str(game["game_id"]))

                    # Mark complete
                    await conn.execute("""
                        UPDATE stats_queue
                        SET status = 'completed', processed_at = NOW()
                        WHERE id = $1
                    """, game["id"])

                    processed += 1

                except Exception as e:
                    logger.error(f"Failed to process game {game['game_id']}: {e}")
                    # Mark failed
                    await conn.execute("""
                        UPDATE stats_queue
                        SET status = 'failed', error_message = $2, processed_at = NOW()
                        WHERE id = $1
                    """, game["id"], str(e))

        return processed

    async def cleanup_old_queue_entries(self, days: int = 7) -> int:
        """
        Clean up old completed/failed queue entries.

        Args:
            days: Delete entries older than this many days.

        Returns:
            Number of entries deleted.
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM stats_queue
                WHERE status IN ('completed', 'failed')
                AND processed_at < NOW() - INTERVAL '1 day' * $1
            """, days)
            # Parse "DELETE N" result
            return int(result.split()[1]) if result else 0


# Global stats service instance
_stats_service: Optional[StatsService] = None


async def get_stats_service(
    pool: asyncpg.Pool,
    event_store: Optional[EventStore] = None,
) -> StatsService:
    """
    Get or create the global stats service instance.

    Args:
        pool: asyncpg connection pool.
        event_store: Optional EventStore.

    Returns:
        StatsService instance.
    """
    global _stats_service
    if _stats_service is None:
        _stats_service = StatsService(pool, event_store)
    return _stats_service


def set_stats_service(service: StatsService) -> None:
    """Set the global stats service instance."""
    global _stats_service
    _stats_service = service


def close_stats_service() -> None:
    """Close the global stats service."""
    global _stats_service
    _stats_service = None
