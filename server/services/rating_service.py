"""
Glicko-2 rating service for Golf game matchmaking.

Implements the Glicko-2 rating system adapted for multiplayer games.
Each game is treated as a set of pairwise comparisons between all players.

Reference: http://www.glicko.net/glicko/glicko2.pdf
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# Glicko-2 constants
INITIAL_RATING = 1500.0
INITIAL_RD = 350.0
INITIAL_VOLATILITY = 0.06
TAU = 0.5  # System constant (constrains volatility change)
CONVERGENCE_TOLERANCE = 0.000001
GLICKO2_SCALE = 173.7178  # Factor to convert between Glicko and Glicko-2 scales


@dataclass
class PlayerRating:
    """A player's Glicko-2 rating."""
    user_id: str
    rating: float = INITIAL_RATING
    rd: float = INITIAL_RD
    volatility: float = INITIAL_VOLATILITY
    updated_at: Optional[datetime] = None

    @property
    def mu(self) -> float:
        """Convert rating to Glicko-2 scale."""
        return (self.rating - 1500) / GLICKO2_SCALE

    @property
    def phi(self) -> float:
        """Convert RD to Glicko-2 scale."""
        return self.rd / GLICKO2_SCALE

    def to_dict(self) -> dict:
        return {
            "rating": round(self.rating, 1),
            "rd": round(self.rd, 1),
            "volatility": round(self.volatility, 6),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def _g(phi: float) -> float:
    """Glicko-2 g function."""
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _E(mu: float, mu_j: float, phi_j: float) -> float:
    """Glicko-2 expected score."""
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _compute_variance(mu: float, opponents: list[tuple[float, float]]) -> float:
    """
    Compute the estimated variance of the player's rating
    based on game outcomes.

    opponents: list of (mu_j, phi_j) tuples
    """
    v_inv = 0.0
    for mu_j, phi_j in opponents:
        g_phi = _g(phi_j)
        e = _E(mu, mu_j, phi_j)
        v_inv += g_phi * g_phi * e * (1.0 - e)
    if v_inv == 0:
        return float('inf')
    return 1.0 / v_inv


def _compute_delta(mu: float, opponents: list[tuple[float, float, float]], v: float) -> float:
    """
    Compute the estimated improvement in rating.

    opponents: list of (mu_j, phi_j, score) tuples
    """
    total = 0.0
    for mu_j, phi_j, score in opponents:
        total += _g(phi_j) * (score - _E(mu, mu_j, phi_j))
    return v * total


def _new_volatility(sigma: float, phi: float, v: float, delta: float) -> float:
    """Compute new volatility using the Illinois algorithm (Glicko-2 Step 5)."""
    a = math.log(sigma * sigma)
    delta_sq = delta * delta
    phi_sq = phi * phi

    def f(x):
        ex = math.exp(x)
        num1 = ex * (delta_sq - phi_sq - v - ex)
        denom1 = 2.0 * (phi_sq + v + ex) ** 2
        return num1 / denom1 - (x - a) / (TAU * TAU)

    # Set initial bounds
    A = a
    if delta_sq > phi_sq + v:
        B = math.log(delta_sq - phi_sq - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        B = a - k * TAU

    # Illinois algorithm
    f_A = f(A)
    f_B = f(B)

    for _ in range(100):  # Safety limit
        if abs(B - A) < CONVERGENCE_TOLERANCE:
            break
        C = A + (A - B) * f_A / (f_B - f_A)
        f_C = f(C)

        if f_C * f_B <= 0:
            A = B
            f_A = f_B
        else:
            f_A /= 2.0

        B = C
        f_B = f_C

    return math.exp(A / 2.0)


def update_rating(player: PlayerRating, opponents: list[tuple[float, float, float]]) -> PlayerRating:
    """
    Update a single player's rating based on game results.

    Args:
        player: Current player rating.
        opponents: List of (mu_j, phi_j, score) where score is 1.0 (win), 0.5 (draw), 0.0 (loss).

    Returns:
        Updated PlayerRating.
    """
    if not opponents:
        # No opponents - just increase RD for inactivity
        new_phi = math.sqrt(player.phi ** 2 + player.volatility ** 2)
        return PlayerRating(
            user_id=player.user_id,
            rating=player.rating,
            rd=min(new_phi * GLICKO2_SCALE, INITIAL_RD),
            volatility=player.volatility,
            updated_at=datetime.now(timezone.utc),
        )

    mu = player.mu
    phi = player.phi
    sigma = player.volatility

    opp_pairs = [(mu_j, phi_j) for mu_j, phi_j, _ in opponents]

    v = _compute_variance(mu, opp_pairs)
    delta = _compute_delta(mu, opponents, v)

    # New volatility
    new_sigma = _new_volatility(sigma, phi, v, delta)

    # Update phi (pre-rating)
    phi_star = math.sqrt(phi ** 2 + new_sigma ** 2)

    # New phi
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star ** 2) + 1.0 / v)

    # New mu
    improvement = 0.0
    for mu_j, phi_j, score in opponents:
        improvement += _g(phi_j) * (score - _E(mu, mu_j, phi_j))
    new_mu = mu + new_phi ** 2 * improvement

    # Convert back to Glicko scale
    new_rating = new_mu * GLICKO2_SCALE + 1500
    new_rd = new_phi * GLICKO2_SCALE

    # Clamp RD to reasonable range
    new_rd = max(30.0, min(new_rd, INITIAL_RD))

    return PlayerRating(
        user_id=player.user_id,
        rating=max(100.0, new_rating),  # Floor at 100
        rd=new_rd,
        volatility=new_sigma,
        updated_at=datetime.now(timezone.utc),
    )


class RatingService:
    """
    Manages Glicko-2 ratings for players.

    Ratings are only updated for standard-rules games.
    Multiplayer games are decomposed into pairwise comparisons.
    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_rating(self, user_id: str) -> PlayerRating:
        """Get a player's current rating."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT rating, rating_deviation, rating_volatility, rating_updated_at
                FROM player_stats
                WHERE user_id = $1
                """,
                user_id,
            )

            if not row or row["rating"] is None:
                return PlayerRating(user_id=user_id)

            return PlayerRating(
                user_id=user_id,
                rating=float(row["rating"]),
                rd=float(row["rating_deviation"]),
                volatility=float(row["rating_volatility"]),
                updated_at=row["rating_updated_at"],
            )

    async def get_ratings_batch(self, user_ids: list[str]) -> dict[str, PlayerRating]:
        """Get ratings for multiple players."""
        ratings = {}
        for uid in user_ids:
            ratings[uid] = await self.get_rating(uid)
        return ratings

    async def update_ratings(
        self,
        player_results: list[tuple[str, int]],
        is_standard_rules: bool,
    ) -> dict[str, PlayerRating]:
        """
        Update ratings after a game.

        Args:
            player_results: List of (user_id, total_score) for each human player.
            is_standard_rules: Whether the game used standard rules.

        Returns:
            Dict of user_id -> updated PlayerRating.
        """
        if not is_standard_rules:
            logger.debug("Skipping rating update for non-standard rules game")
            return {}

        if len(player_results) < 2:
            logger.debug("Skipping rating update: fewer than 2 human players")
            return {}

        # Get current ratings
        user_ids = [uid for uid, _ in player_results]
        current_ratings = await self.get_ratings_batch(user_ids)

        # Sort by score (lower is better in Golf)
        sorted_results = sorted(player_results, key=lambda x: x[1])

        # Build pairwise comparisons for each player
        updated_ratings = {}
        for uid, score in player_results:
            player = current_ratings[uid]
            opponents = []

            for opp_uid, opp_score in player_results:
                if opp_uid == uid:
                    continue

                opp = current_ratings[opp_uid]

                # Determine outcome (lower score wins in Golf)
                if score < opp_score:
                    outcome = 1.0  # Win
                elif score == opp_score:
                    outcome = 0.5  # Draw
                else:
                    outcome = 0.0  # Loss

                opponents.append((opp.mu, opp.phi, outcome))

            updated = update_rating(player, opponents)
            updated_ratings[uid] = updated

        # Persist updated ratings
        async with self.pool.acquire() as conn:
            for uid, rating in updated_ratings.items():
                await conn.execute(
                    """
                    UPDATE player_stats
                    SET rating = $2,
                        rating_deviation = $3,
                        rating_volatility = $4,
                        rating_updated_at = $5
                    WHERE user_id = $1
                    """,
                    uid,
                    rating.rating,
                    rating.rd,
                    rating.volatility,
                    rating.updated_at,
                )

        logger.info(
            f"Ratings updated for {len(updated_ratings)} players: "
            + ", ".join(f"{uid[:8]}={r.rating:.0f}" for uid, r in updated_ratings.items())
        )

        return updated_ratings
