"""
Game logic for 6-Card Golf.

This module implements the core game mechanics for the 6-Card Golf card game,
including card/deck management, player state, scoring rules, and game flow.

6-Card Golf Rules Summary:
    - Each player has 6 cards arranged in a 2x3 grid (2 rows, 3 columns)
    - Goal: Achieve the lowest score over multiple rounds (holes)
    - On your turn: Draw from deck or discard pile, then swap or discard
    - Matching pairs in a column cancel out (score 0)
    - Game ends when one player reveals all cards, then others get one final turn

Card Layout:
    [0] [1] [2]   <- top row
    [3] [4] [5]   <- bottom row

    Columns: (0,3), (1,4), (2,5) - matching ranks in a column score 0
"""

import random
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from constants import (
    DEFAULT_CARD_VALUES,
    SUPER_KINGS_VALUE,
    TEN_PENNY_VALUE,
    LUCKY_SWING_JOKER_VALUE,
)


class FlipMode(str, Enum):
    """
    Mode for flip-on-discard rule.

    NEVER: No flip when discarding from deck (standard rules)
    ALWAYS: Must flip when discarding from deck (Speed Golf - faster games)
    ENDGAME: Optional flip when any player has ≤1 face-down card (Suspense mode)
    """

    NEVER = "never"
    ALWAYS = "always"
    ENDGAME = "endgame"


class Suit(Enum):
    """Card suits for a standard deck."""

    HEARTS = "hearts"
    DIAMONDS = "diamonds"
    CLUBS = "clubs"
    SPADES = "spades"


class Rank(Enum):
    """
    Card ranks with their display values.

    Standard Golf scoring (can be modified by house rules):
        - Ace: 1 point
        - 2-10: Face value (except Kings)
        - Jack/Queen: 10 points
        - King: 0 points
        - Joker: -2 points (when enabled)
    """

    ACE = "A"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    JOKER = "★"


# Map Rank enum to point values (derived from constants.py as single source of truth)
RANK_VALUES: dict[Rank, int] = {rank: DEFAULT_CARD_VALUES[rank.value] for rank in Rank}


def get_card_value(card: "Card", options: Optional["GameOptions"] = None) -> int:
    """
    Get point value for a card, with house rules applied.

    This is the single source of truth for Card object value calculations.
    Use this instead of card.value() when house rules need to be considered.

    Args:
        card: Card object to evaluate
        options: Optional GameOptions with house rule flags

    Returns:
        Point value for the card
    """
    if options:
        if card.rank == Rank.JOKER:
            if options.eagle_eye:
                return 2  # Eagle-eyed: jokers worth +2 unpaired, -4 when paired (handled in calculate_score)
            return LUCKY_SWING_JOKER_VALUE if options.lucky_swing else RANK_VALUES[Rank.JOKER]
        if card.rank == Rank.KING and options.super_kings:
            return SUPER_KINGS_VALUE
        if card.rank == Rank.TEN and options.ten_penny:
            return TEN_PENNY_VALUE
    return RANK_VALUES[card.rank]


@dataclass
class Card:
    """
    A playing card with suit, rank, and face-up state.

    Attributes:
        suit: The card's suit (hearts, diamonds, clubs, spades).
        rank: The card's rank (A, 2-10, J, Q, K, or Joker).
        face_up: Whether the card is visible to all players.
    """

    suit: Suit
    rank: Rank
    face_up: bool = False

    def to_dict(self, reveal: bool = False) -> dict:
        """
        Convert card to dictionary for JSON serialization.

        Args:
            reveal: If True, show card details even if face-down.

        Returns:
            Dict with card info, or just {face_up: False} if hidden.
        """
        if self.face_up or reveal:
            return {
                "suit": self.suit.value,
                "rank": self.rank.value,
                "face_up": self.face_up,
            }
        return {"face_up": False}

    def value(self) -> int:
        """Get base point value (without house rule modifications)."""
        return RANK_VALUES[self.rank]


class Deck:
    """
    A deck of playing cards that can be shuffled and drawn from.

    Supports multiple standard 52-card decks combined, with optional
    jokers in various configurations (standard 2-per-deck or lucky swing).
    """

    def __init__(
        self,
        num_decks: int = 1,
        use_jokers: bool = False,
        lucky_swing: bool = False,
    ) -> None:
        """
        Initialize a new deck.

        Args:
            num_decks: Number of standard 52-card decks to combine.
            use_jokers: Whether to include joker cards.
            lucky_swing: If True, use single -5 joker instead of two -2 jokers.
        """
        self.cards: list[Card] = []

        # Build deck(s) with standard cards
        for _ in range(num_decks):
            for suit in Suit:
                for rank in Rank:
                    if rank != Rank.JOKER:
                        self.cards.append(Card(suit, rank))

            # Standard jokers: 2 per deck, worth -2 each
            if use_jokers and not lucky_swing:
                self.cards.append(Card(Suit.HEARTS, Rank.JOKER))
                self.cards.append(Card(Suit.SPADES, Rank.JOKER))

        # Lucky Swing: Single joker total, worth -5
        if use_jokers and lucky_swing:
            self.cards.append(Card(Suit.HEARTS, Rank.JOKER))

        self.shuffle()

    def shuffle(self) -> None:
        """Randomize the order of cards in the deck."""
        random.shuffle(self.cards)

    def draw(self) -> Optional[Card]:
        """
        Draw the top card from the deck.

        Returns:
            The drawn Card, or None if deck is empty.
        """
        if self.cards:
            return self.cards.pop()
        return None

    def cards_remaining(self) -> int:
        """Return the number of cards left in the deck."""
        return len(self.cards)

    def add_cards(self, cards: list[Card]) -> None:
        """
        Add cards to the deck and shuffle.

        Used when reshuffling the discard pile back into the deck.

        Args:
            cards: List of cards to add.
        """
        self.cards.extend(cards)
        self.shuffle()


@dataclass
class Player:
    """
    A player in the Golf card game.

    Attributes:
        id: Unique identifier for the player.
        name: Display name.
        cards: The player's 6-card hand arranged in a 2x3 grid.
        score: Points scored in the current round.
        total_score: Cumulative points across all rounds.
        rounds_won: Number of rounds where this player had the lowest score.
    """

    id: str
    name: str
    cards: list[Card] = field(default_factory=list)
    score: int = 0
    total_score: int = 0
    rounds_won: int = 0

    def all_face_up(self) -> bool:
        """Check if all of the player's cards are revealed."""
        return all(card.face_up for card in self.cards)

    def flip_card(self, position: int) -> None:
        """
        Reveal a card at the given position.

        Args:
            position: Index 0-5 in the card grid.
        """
        if 0 <= position < len(self.cards):
            self.cards[position].face_up = True

    def swap_card(self, position: int, new_card: Card) -> Card:
        """
        Replace a card in the player's hand with a new card.

        Args:
            position: Index 0-5 in the card grid.
            new_card: The card to place in the hand.

        Returns:
            The card that was replaced (now face-up for discard).
        """
        old_card = self.cards[position]
        new_card.face_up = True
        self.cards[position] = new_card
        return old_card

    def calculate_score(self, options: Optional["GameOptions"] = None) -> int:
        """
        Calculate the player's score for the current round.

        Scoring rules:
            - Each card contributes its point value
            - Matching pairs in a column (same rank) cancel out (score 0)
            - House rules may modify individual card values or add bonuses

        Card grid layout:
            [0] [1] [2]   <- top row
            [3] [4] [5]   <- bottom row
            Columns: (0,3), (1,4), (2,5)

        Args:
            options: Game options with house rule flags.

        Returns:
            Total score for this round (lower is better).
        """
        if len(self.cards) != 6:
            return 0

        total = 0
        jack_pairs = 0  # Track paired Jacks for Wolfpack bonus

        for col in range(3):
            top_idx = col
            bottom_idx = col + 3
            top_card = self.cards[top_idx]
            bottom_card = self.cards[bottom_idx]

            # Check if column pair matches (same rank cancels out)
            if top_card.rank == bottom_card.rank:
                # Track Jack pairs for Wolfpack bonus
                if top_card.rank == Rank.JACK:
                    jack_pairs += 1

                # Eagle Eye: paired jokers score -4 instead of 0
                if (options and options.eagle_eye and
                        top_card.rank == Rank.JOKER):
                    total -= 4
                    continue

                # Normal matching pair: scores 0 (skip adding values)
                continue

            # Non-matching cards: add both values
            total += get_card_value(top_card, options)
            total += get_card_value(bottom_card, options)

        # Wolfpack bonus: 2+ pairs of Jacks = -5 pts
        if options and options.wolfpack and jack_pairs >= 2:
            total -= 5

        self.score = total
        return total

    def cards_to_dict(self, reveal: bool = False) -> list[dict]:
        """
        Convert all cards to dictionaries for JSON serialization.

        Args:
            reveal: If True, show all card details regardless of face-up state.

        Returns:
            List of card dictionaries.
        """
        return [card.to_dict(reveal) for card in self.cards]


class GamePhase(Enum):
    """
    Phases of a Golf game round.

    Flow: WAITING -> INITIAL_FLIP -> PLAYING -> FINAL_TURN -> ROUND_OVER
    After all rounds: GAME_OVER
    """

    WAITING = "waiting"          # Lobby, waiting for players to join
    INITIAL_FLIP = "initial_flip"  # Players choosing initial cards to reveal
    PLAYING = "playing"          # Normal gameplay, taking turns
    FINAL_TURN = "final_turn"    # After someone reveals all cards, others get one turn
    ROUND_OVER = "round_over"    # Round complete, showing scores
    GAME_OVER = "game_over"      # All rounds complete, showing final standings


@dataclass
class GameOptions:
    """
    Configuration options for game rules and house variants.

    These options can modify scoring, add special rules, and change gameplay.
    All options default to False/standard values for a classic Golf game.
    """

    # --- Standard Options ---
    flip_mode: str = "never"
    """Flip mode when discarding from deck: 'never', 'always', or 'endgame'."""

    initial_flips: int = 2
    """Number of cards each player reveals at round start (0, 1, or 2)."""

    knock_penalty: bool = False
    """If True, +10 penalty if you go out but don't have the lowest score."""

    use_jokers: bool = False
    """If True, add joker cards to the deck."""

    # --- House Rules: Point Modifiers ---
    lucky_swing: bool = False
    """Use single -5 joker instead of two -2 jokers."""

    super_kings: bool = False
    """Kings worth -2 instead of 0."""

    ten_penny: bool = False
    """10s worth 1 point instead of 10."""

    # --- House Rules: Bonuses/Penalties ---
    knock_bonus: bool = False
    """First player to reveal all cards gets -5 bonus."""

    underdog_bonus: bool = False
    """Lowest scorer each round gets -3 bonus."""

    tied_shame: bool = False
    """Players who tie with another get +5 penalty."""

    blackjack: bool = False
    """Hole score of exactly 21 becomes 0."""

    wolfpack: bool = False
    """Two pairs of Jacks (all 4 Jacks) grants -5 bonus."""

    # --- House Rules: Special ---
    eagle_eye: bool = False
    """Jokers worth +2 unpaired, -4 when paired (instead of -2/0)."""


@dataclass
class Game:
    """
    Main game state and logic controller for 6-Card Golf.

    Manages the full game lifecycle including:
        - Player management (add/remove/lookup)
        - Deck and discard pile management
        - Turn flow and phase transitions
        - Scoring with house rules
        - Multi-round game progression

    Attributes:
        players: List of players in the game (max 6).
        deck: The draw pile.
        discard_pile: Face-up cards that have been discarded.
        current_player_index: Index of the player whose turn it is.
        phase: Current game phase (waiting, playing, etc.).
        num_decks: Number of 52-card decks combined.
        num_rounds: Total rounds (holes) to play.
        current_round: Current round number (1-indexed).
        drawn_card: Card currently held by active player (if any).
        drawn_from_discard: Whether drawn_card came from discard pile.
        finisher_id: ID of player who first revealed all cards.
        players_with_final_turn: Set of player IDs who've had final turn.
        initial_flips_done: Set of player IDs who've done initial flips.
        options: Game configuration and house rules.
    """

    players: list[Player] = field(default_factory=list)
    deck: Optional[Deck] = None
    discard_pile: list[Card] = field(default_factory=list)
    current_player_index: int = 0
    phase: GamePhase = GamePhase.WAITING
    num_decks: int = 1
    num_rounds: int = 1
    current_round: int = 1
    drawn_card: Optional[Card] = None
    drawn_from_discard: bool = False
    finisher_id: Optional[str] = None
    players_with_final_turn: set = field(default_factory=set)
    initial_flips_done: set = field(default_factory=set)
    options: GameOptions = field(default_factory=GameOptions)

    @property
    def flip_on_discard(self) -> bool:
        """
        Whether current turn requires/allows a flip after discard.

        Returns True if:
        - flip_mode is 'always' (Speed Golf)
        - flip_mode is 'endgame' AND any player has ≤1 face-down card (Suspense)
        """
        if self.options.flip_mode == FlipMode.ALWAYS.value:
            return True
        if self.options.flip_mode == FlipMode.ENDGAME.value:
            # Check if any player has ≤1 face-down card
            for player in self.players:
                face_down_count = sum(1 for c in player.cards if not c.face_up)
                if face_down_count <= 1:
                    return True
            return False
        return False  # "never"

    @property
    def flip_is_optional(self) -> bool:
        """
        Whether the flip is optional (endgame mode) vs mandatory (always mode).

        In endgame mode, player can choose to skip the flip.
        """
        return self.options.flip_mode == FlipMode.ENDGAME.value and self.flip_on_discard

    def get_card_values(self) -> dict[str, int]:
        """
        Get card value mapping with house rules applied.

        Returns:
            Dict mapping rank strings to point values.
        """
        values = DEFAULT_CARD_VALUES.copy()

        if self.options.super_kings:
            values['K'] = SUPER_KINGS_VALUE
        if self.options.ten_penny:
            values['10'] = TEN_PENNY_VALUE
        if self.options.lucky_swing:
            values['★'] = LUCKY_SWING_JOKER_VALUE
        elif self.options.eagle_eye:
            values['★'] = 2  # +2 unpaired, -4 paired (handled in scoring)

        return values

    # -------------------------------------------------------------------------
    # Player Management
    # -------------------------------------------------------------------------

    def add_player(self, player: Player) -> bool:
        """
        Add a player to the game.

        Args:
            player: The player to add.

        Returns:
            True if added, False if game is full (max 6 players).
        """
        if len(self.players) >= 6:
            return False
        self.players.append(player)
        return True

    def remove_player(self, player_id: str) -> Optional[Player]:
        """
        Remove a player from the game by ID.

        Args:
            player_id: The unique ID of the player to remove.

        Returns:
            The removed Player, or None if not found.
        """
        for i, player in enumerate(self.players):
            if player.id == player_id:
                return self.players.pop(i)
        return None

    def get_player(self, player_id: str) -> Optional[Player]:
        """
        Find a player by their ID.

        Args:
            player_id: The unique ID to search for.

        Returns:
            The Player if found, None otherwise.
        """
        for player in self.players:
            if player.id == player_id:
                return player
        return None

    def current_player(self) -> Optional[Player]:
        """Get the player whose turn it currently is."""
        if self.players:
            return self.players[self.current_player_index]
        return None

    # -------------------------------------------------------------------------
    # Game Lifecycle
    # -------------------------------------------------------------------------

    def start_game(
        self,
        num_decks: int = 1,
        num_rounds: int = 1,
        options: Optional[GameOptions] = None,
    ) -> None:
        """
        Initialize and start a new game.

        Args:
            num_decks: Number of card decks to use (1-3).
            num_rounds: Number of rounds/holes to play.
            options: Game configuration and house rules.
        """
        self.num_decks = num_decks
        self.num_rounds = num_rounds
        self.options = options or GameOptions()
        self.current_round = 1
        self.start_round()

    def start_round(self) -> None:
        """
        Initialize a new round.

        Creates fresh deck, deals 6 cards to each player, starts discard pile,
        and sets phase to INITIAL_FLIP (or PLAYING if no flips required).
        """
        self.deck = Deck(
            self.num_decks,
            use_jokers=self.options.use_jokers,
            lucky_swing=self.options.lucky_swing,
        )
        self.discard_pile = []
        self.drawn_card = None
        self.drawn_from_discard = False
        self.finisher_id = None
        self.players_with_final_turn = set()
        self.initial_flips_done = set()

        # Deal 6 cards to each player
        for player in self.players:
            player.cards = []
            player.score = 0
            for _ in range(6):
                card = self.deck.draw()
                if card:
                    player.cards.append(card)

        # Start discard pile with one face-up card
        first_discard = self.deck.draw()
        if first_discard:
            first_discard.face_up = True
            self.discard_pile.append(first_discard)

        self.current_player_index = 0

        # Skip initial flip phase if 0 flips required
        if self.options.initial_flips == 0:
            self.phase = GamePhase.PLAYING
        else:
            self.phase = GamePhase.INITIAL_FLIP

    def flip_initial_cards(self, player_id: str, positions: list[int]) -> bool:
        """
        Handle a player's initial card flip selection.

        Called during INITIAL_FLIP phase when player chooses which
        cards to reveal at the start of the round.

        Args:
            player_id: ID of the player flipping cards.
            positions: List of card positions (0-5) to flip.

        Returns:
            True if flips were valid and applied, False otherwise.
        """
        if self.phase != GamePhase.INITIAL_FLIP:
            return False

        if player_id in self.initial_flips_done:
            return False

        required_flips = self.options.initial_flips
        if len(positions) != required_flips:
            return False

        player = self.get_player(player_id)
        if not player:
            return False

        for pos in positions:
            if not (0 <= pos < 6):
                return False
            player.flip_card(pos)

        self.initial_flips_done.add(player_id)

        # Transition to PLAYING when all players have flipped
        if len(self.initial_flips_done) == len(self.players):
            self.phase = GamePhase.PLAYING

        return True

    # -------------------------------------------------------------------------
    # Turn Actions
    # -------------------------------------------------------------------------

    def draw_card(self, player_id: str, source: str) -> Optional[Card]:
        """
        Draw a card from the deck or discard pile.

        This is the first action of a player's turn. After drawing, the player
        must either swap the card with one in their hand or discard it (if
        drawn from deck).

        Args:
            player_id: ID of the player drawing.
            source: Either "deck" or "discard".

        Returns:
            The drawn Card, or None if action is invalid.
        """
        player = self.current_player()
        if not player or player.id != player_id:
            return None

        if self.phase not in (GamePhase.PLAYING, GamePhase.FINAL_TURN):
            return None

        if self.drawn_card is not None:
            return None

        if source == "deck":
            card = self.deck.draw()
            if not card:
                # Deck empty - try to reshuffle discard pile
                card = self._reshuffle_discard_pile()
            if card:
                self.drawn_card = card
                self.drawn_from_discard = False
                return card
            # No cards available anywhere - end round gracefully
            self._end_round()
            return None

        if source == "discard" and self.discard_pile:
            card = self.discard_pile.pop()
            self.drawn_card = card
            self.drawn_from_discard = True
            return card

        return None

    def _reshuffle_discard_pile(self) -> Optional[Card]:
        """
        Reshuffle the discard pile back into the deck.

        Called when the deck is empty. Keeps the top discard card visible,
        shuffles the rest back into the deck, and draws a card.

        Returns:
            A drawn Card from the reshuffled deck, or None if not possible.
        """
        if len(self.discard_pile) <= 1:
            return None

        # Keep the top card visible, reshuffle the rest
        top_card = self.discard_pile[-1]
        cards_to_reshuffle = self.discard_pile[:-1]

        for card in cards_to_reshuffle:
            card.face_up = False

        self.deck.add_cards(cards_to_reshuffle)
        self.discard_pile = [top_card]

        return self.deck.draw()

    def swap_card(self, player_id: str, position: int) -> Optional[Card]:
        """
        Swap the drawn card with a card in the player's hand.

        The swapped-out card goes to the discard pile face-up.

        Args:
            player_id: ID of the player swapping.
            position: Index 0-5 in the player's card grid.

        Returns:
            The card that was replaced, or None if action is invalid.
        """
        player = self.current_player()
        if not player or player.id != player_id:
            return None

        if self.drawn_card is None:
            return None

        if not (0 <= position < 6):
            return None

        old_card = player.swap_card(position, self.drawn_card)
        old_card.face_up = True
        self.discard_pile.append(old_card)
        self.drawn_card = None

        self._check_end_turn(player)
        return old_card

    def can_discard_drawn(self) -> bool:
        """
        Check if the current player can discard their drawn card.

        Cards drawn from the discard pile must be swapped (cannot be discarded).

        Returns:
            True if discard is allowed, False if swap is required.
        """
        if self.drawn_from_discard:
            return False
        return True

    def discard_drawn(self, player_id: str) -> bool:
        """
        Discard the drawn card without swapping.

        Only allowed when the card was drawn from the deck (not discard pile).
        If flip_on_discard is enabled, player must then flip a face-down card.

        Args:
            player_id: ID of the player discarding.

        Returns:
            True if discard was successful, False otherwise.
        """
        player = self.current_player()
        if not player or player.id != player_id:
            return False

        if self.drawn_card is None:
            return False

        if not self.can_discard_drawn():
            return False

        self.drawn_card.face_up = True
        self.discard_pile.append(self.drawn_card)
        self.drawn_card = None

        if self.flip_on_discard:
            # Player must flip a card before turn ends
            has_face_down = any(not card.face_up for card in player.cards)
            if not has_face_down:
                self._check_end_turn(player)
            # Otherwise, wait for flip_and_end_turn to be called
        else:
            self._check_end_turn(player)

        return True

    def flip_and_end_turn(self, player_id: str, position: int) -> bool:
        """
        Flip a face-down card to complete turn (flip_on_discard variant).

        Called after discarding when flip_on_discard option is enabled.

        Args:
            player_id: ID of the player flipping.
            position: Index 0-5 of the card to flip.

        Returns:
            True if flip was valid and turn ended, False otherwise.
        """
        player = self.current_player()
        if not player or player.id != player_id:
            return False

        if not (0 <= position < 6):
            return False

        if player.cards[position].face_up:
            return False

        player.flip_card(position)
        self._check_end_turn(player)
        return True

    def skip_flip_and_end_turn(self, player_id: str) -> bool:
        """
        Skip optional flip and end turn (endgame mode only).

        In endgame mode (flip_mode='endgame'), the flip is optional,
        so players can choose to skip it and end their turn immediately.

        Args:
            player_id: ID of the player skipping the flip.

        Returns:
            True if skip was valid and turn ended, False otherwise.
        """
        if not self.flip_is_optional:
            return False

        player = self.current_player()
        if not player or player.id != player_id:
            return False

        self._check_end_turn(player)
        return True

    # -------------------------------------------------------------------------
    # Turn & Round Flow (Internal)
    # -------------------------------------------------------------------------

    def _check_end_turn(self, player: Player) -> None:
        """
        Check if player triggered end-game and advance to next turn.

        If the player has revealed all cards and is the first to do so,
        triggers FINAL_TURN phase where other players get one more turn.

        In FINAL_TURN phase, reveal all of the player's cards after their turn.

        Args:
            player: The player whose turn just ended.
        """
        if player.all_face_up() and self.finisher_id is None:
            self.finisher_id = player.id
            self.phase = GamePhase.FINAL_TURN
            self.players_with_final_turn.add(player.id)
        elif self.phase == GamePhase.FINAL_TURN:
            # Reveal this player's cards immediately after their final turn
            for card in player.cards:
                card.face_up = True

        self._next_turn()

    def _next_turn(self) -> None:
        """
        Advance to the next player's turn.

        In FINAL_TURN phase, tracks which players have had their final turn
        and ends the round when everyone has played.
        """
        if self.phase == GamePhase.FINAL_TURN:
            next_index = (self.current_player_index + 1) % len(self.players)
            next_player = self.players[next_index]

            if next_player.id in self.players_with_final_turn:
                # Everyone has had their final turn
                self._end_round()
                return

            self.current_player_index = next_index
            self.players_with_final_turn.add(next_player.id)
        else:
            self.current_player_index = (self.current_player_index + 1) % len(self.players)

    # -------------------------------------------------------------------------
    # Scoring & Round End
    # -------------------------------------------------------------------------

    def _end_round(self) -> None:
        """
        End the current round and calculate final scores.

        Reveals all cards, calculates base scores, then applies house rule
        bonuses and penalties in order:
            1. Blackjack (21 -> 0)
            2. Knock penalty (+10 if finisher doesn't have lowest)
            3. Knock bonus (-5 to finisher)
            4. Underdog bonus (-3 to lowest scorer)
            5. Tied shame (+5 to players with matching scores)

        Finally, updates total scores and awards round wins.
        """
        self.phase = GamePhase.ROUND_OVER

        # Reveal all cards and calculate base scores
        for player in self.players:
            for card in player.cards:
                card.face_up = True
            player.calculate_score(self.options)

        # --- Apply House Rule Bonuses/Penalties ---

        # Blackjack: exact score of 21 becomes 0
        if self.options.blackjack:
            for player in self.players:
                if player.score == 21:
                    player.score = 0

        # Knock penalty: +10 if finisher doesn't have the lowest score
        if self.options.knock_penalty and self.finisher_id:
            finisher = self.get_player(self.finisher_id)
            if finisher:
                min_score = min(p.score for p in self.players)
                if finisher.score > min_score:
                    finisher.score += 10

        # Knock bonus: -5 to the player who went out first
        if self.options.knock_bonus and self.finisher_id:
            finisher = self.get_player(self.finisher_id)
            if finisher:
                finisher.score -= 5

        # Underdog bonus: -3 to the lowest scorer(s)
        if self.options.underdog_bonus:
            min_score = min(p.score for p in self.players)
            for player in self.players:
                if player.score == min_score:
                    player.score -= 3

        # Tied shame: +5 to players who share a score with someone
        if self.options.tied_shame:
            score_counts = Counter(p.score for p in self.players)
            for player in self.players:
                if score_counts[player.score] > 1:
                    player.score += 5

        # Update cumulative totals
        for player in self.players:
            player.total_score += player.score

        # Award round win to lowest scorer(s)
        min_score = min(p.score for p in self.players)
        for player in self.players:
            if player.score == min_score:
                player.rounds_won += 1

    def start_next_round(self) -> bool:
        """
        Start the next round of the game.

        Returns:
            True if next round started, False if game is over or not ready.
        """
        if self.phase != GamePhase.ROUND_OVER:
            return False

        if self.current_round >= self.num_rounds:
            self.phase = GamePhase.GAME_OVER
            return False

        self.current_round += 1
        self.start_round()
        return True

    # -------------------------------------------------------------------------
    # State Queries
    # -------------------------------------------------------------------------

    def discard_top(self) -> Optional[Card]:
        """Get the top card of the discard pile (if any)."""
        if self.discard_pile:
            return self.discard_pile[-1]
        return None

    def get_state(self, for_player_id: str) -> dict:
        """
        Get the full game state for a specific player.

        Returns a dictionary suitable for JSON serialization and sending
        to the client. Hides opponent card values unless the round is over.

        Args:
            for_player_id: The player who will receive this state.
                Their own cards are always revealed.

        Returns:
            Dict containing phase, players, current turn, discard pile,
            deck info, round info, and active house rules.
        """
        current = self.current_player()

        players_data = []
        for player in self.players:
            reveal = self.phase in (GamePhase.ROUND_OVER, GamePhase.GAME_OVER)
            is_self = player.id == for_player_id

            players_data.append({
                "id": player.id,
                "name": player.name,
                "cards": player.cards_to_dict(reveal=reveal or is_self),
                "score": player.score if reveal else None,
                "total_score": player.total_score,
                "rounds_won": player.rounds_won,
                "all_face_up": player.all_face_up(),
            })

        discard_top = self.discard_top()

        # Build active rules list for display
        active_rules = []
        if self.options:
            if self.options.flip_mode == FlipMode.ALWAYS.value:
                active_rules.append("Speed Golf")
            elif self.options.flip_mode == FlipMode.ENDGAME.value:
                active_rules.append("Endgame Flip")
            if self.options.knock_penalty:
                active_rules.append("Knock Penalty")
            if self.options.use_jokers and not self.options.lucky_swing and not self.options.eagle_eye:
                active_rules.append("Jokers")
            if self.options.lucky_swing:
                active_rules.append("Lucky Swing")
            if self.options.eagle_eye:
                active_rules.append("Eagle-Eye")
            if self.options.super_kings:
                active_rules.append("Super Kings")
            if self.options.ten_penny:
                active_rules.append("Ten Penny")
            if self.options.knock_bonus:
                active_rules.append("Knock Bonus")
            if self.options.underdog_bonus:
                active_rules.append("Underdog")
            if self.options.tied_shame:
                active_rules.append("Tied Shame")
            if self.options.blackjack:
                active_rules.append("Blackjack")
            if self.options.wolfpack:
                active_rules.append("Wolfpack")

        return {
            "phase": self.phase.value,
            "players": players_data,
            "current_player_id": current.id if current else None,
            "discard_top": discard_top.to_dict(reveal=True) if discard_top else None,
            "deck_remaining": self.deck.cards_remaining() if self.deck else 0,
            "current_round": self.current_round,
            "total_rounds": self.num_rounds,
            "has_drawn_card": self.drawn_card is not None,
            "can_discard": self.can_discard_drawn() if self.drawn_card else True,
            "waiting_for_initial_flip": (
                self.phase == GamePhase.INITIAL_FLIP and
                for_player_id not in self.initial_flips_done
            ),
            "initial_flips": self.options.initial_flips,
            "flip_on_discard": self.flip_on_discard,
            "flip_mode": self.options.flip_mode,
            "flip_is_optional": self.flip_is_optional,
            "card_values": self.get_card_values(),
            "active_rules": active_rules,
        }
