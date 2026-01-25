"""Game logic for 6-Card Golf."""

import random
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Suit(Enum):
    HEARTS = "hearts"
    DIAMONDS = "diamonds"
    CLUBS = "clubs"
    SPADES = "spades"


class Rank(Enum):
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


RANK_VALUES = {
    Rank.ACE: 1,
    Rank.TWO: -2,
    Rank.THREE: 3,
    Rank.FOUR: 4,
    Rank.FIVE: 5,
    Rank.SIX: 6,
    Rank.SEVEN: 7,
    Rank.EIGHT: 8,
    Rank.NINE: 9,
    Rank.TEN: 10,
    Rank.JACK: 10,
    Rank.QUEEN: 10,
    Rank.KING: 0,
    Rank.JOKER: -2,
}


@dataclass
class Card:
    suit: Suit
    rank: Rank
    face_up: bool = False

    def to_dict(self, reveal: bool = False) -> dict:
        if self.face_up or reveal:
            return {
                "suit": self.suit.value,
                "rank": self.rank.value,
                "face_up": self.face_up,
            }
        return {"face_up": False}

    def value(self) -> int:
        return RANK_VALUES[self.rank]


class Deck:
    def __init__(self, num_decks: int = 1, use_jokers: bool = False, lucky_swing: bool = False):
        self.cards: list[Card] = []
        for _ in range(num_decks):
            for suit in Suit:
                for rank in Rank:
                    if rank != Rank.JOKER:
                        self.cards.append(Card(suit, rank))
            if use_jokers and not lucky_swing:
                # Standard: Add 2 jokers worth -2 each per deck
                self.cards.append(Card(Suit.HEARTS, Rank.JOKER))
                self.cards.append(Card(Suit.SPADES, Rank.JOKER))
        # Lucky Swing: Add just 1 joker total (worth -5)
        if use_jokers and lucky_swing:
            self.cards.append(Card(Suit.HEARTS, Rank.JOKER))
        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self) -> Optional[Card]:
        if self.cards:
            return self.cards.pop()
        return None

    def cards_remaining(self) -> int:
        return len(self.cards)

    def add_cards(self, cards: list[Card]):
        """Add cards to the deck and shuffle."""
        self.cards.extend(cards)
        self.shuffle()


@dataclass
class Player:
    id: str
    name: str
    cards: list[Card] = field(default_factory=list)
    score: int = 0
    total_score: int = 0
    rounds_won: int = 0

    def all_face_up(self) -> bool:
        return all(card.face_up for card in self.cards)

    def flip_card(self, position: int):
        if 0 <= position < len(self.cards):
            self.cards[position].face_up = True

    def swap_card(self, position: int, new_card: Card) -> Card:
        old_card = self.cards[position]
        new_card.face_up = True
        self.cards[position] = new_card
        return old_card

    def calculate_score(self, options: Optional["GameOptions"] = None) -> int:
        """Calculate score with column pair matching and house rules."""
        if len(self.cards) != 6:
            return 0

        def get_card_value(card: Card) -> int:
            """Get card value with house rules applied."""
            if options:
                if card.rank == Rank.JOKER:
                    return -5 if options.lucky_swing else -2
                if card.rank == Rank.KING and options.super_kings:
                    return -2
                if card.rank == Rank.SEVEN and options.lucky_sevens:
                    return 0
                if card.rank == Rank.TEN and options.ten_penny:
                    return 1
            return card.value()

        def cards_match(card1: Card, card2: Card) -> bool:
            """Check if two cards match for pairing (with Queens Wild support)."""
            if card1.rank == card2.rank:
                return True
            if options and options.queens_wild:
                if card1.rank == Rank.QUEEN or card2.rank == Rank.QUEEN:
                    return True
            return False

        total = 0
        # Cards are arranged in 2 rows x 3 columns
        # Position mapping: [0, 1, 2] (top row)
        #                   [3, 4, 5] (bottom row)
        # Columns: (0,3), (1,4), (2,5)

        # Check for Four of a Kind first (4 cards same rank = all score 0)
        four_of_kind_positions: set[int] = set()
        if options and options.four_of_a_kind:
            from collections import Counter
            rank_positions: dict[Rank, list[int]] = {}
            for i, card in enumerate(self.cards):
                if card.rank not in rank_positions:
                    rank_positions[card.rank] = []
                rank_positions[card.rank].append(i)
            for rank, positions in rank_positions.items():
                if len(positions) >= 4:
                    four_of_kind_positions.update(positions)

        for col in range(3):
            top_idx = col
            bottom_idx = col + 3
            top_card = self.cards[top_idx]
            bottom_card = self.cards[bottom_idx]

            # Skip if part of four of a kind
            if top_idx in four_of_kind_positions and bottom_idx in four_of_kind_positions:
                continue

            # Check if column pair matches (same rank or Queens Wild)
            if cards_match(top_card, bottom_card):
                # Eagle Eye: paired jokers score -8 (2³) instead of canceling
                if (options and options.eagle_eye and
                    top_card.rank == Rank.JOKER and bottom_card.rank == Rank.JOKER):
                    total -= 8
                    continue
                # Normal matching pair scores 0
                continue
            else:
                if top_idx not in four_of_kind_positions:
                    total += get_card_value(top_card)
                if bottom_idx not in four_of_kind_positions:
                    total += get_card_value(bottom_card)

        self.score = total
        return total

    def cards_to_dict(self, reveal: bool = False) -> list[dict]:
        return [card.to_dict(reveal) for card in self.cards]


class GamePhase(Enum):
    WAITING = "waiting"
    INITIAL_FLIP = "initial_flip"
    PLAYING = "playing"
    FINAL_TURN = "final_turn"
    ROUND_OVER = "round_over"
    GAME_OVER = "game_over"


@dataclass
class GameOptions:
    # Standard options
    flip_on_discard: bool = False      # Flip a card when discarding from deck
    initial_flips: int = 2             # Cards to flip at start (0, 1, or 2)
    knock_penalty: bool = False        # +10 if you go out but don't have lowest
    use_jokers: bool = False           # Add jokers worth -2 points

    # House Rules - Point Modifiers
    lucky_swing: bool = False          # Single joker worth -5 instead of two -2 jokers
    super_kings: bool = False          # Kings worth -2 instead of 0
    lucky_sevens: bool = False         # 7s worth 0 instead of 7
    ten_penny: bool = False            # 10s worth 1 (like Ace) instead of 10

    # House Rules - Bonuses/Penalties
    knock_bonus: bool = False          # First to reveal all cards gets -5 bonus
    underdog_bonus: bool = False       # Lowest score player gets -3 each hole
    tied_shame: bool = False           # Tie with someone's score = +5 penalty to both
    blackjack: bool = False            # Hole score of exactly 21 becomes 0

    # House Rules - Gameplay Twists
    queens_wild: bool = False          # Queens count as any rank for pairing
    four_of_a_kind: bool = False       # 4 cards of same rank in grid = all 4 score 0
    eagle_eye: bool = False            # Paired jokers double instead of cancel (-4 or -10)


@dataclass
class Game:
    players: list[Player] = field(default_factory=list)
    deck: Optional[Deck] = None
    discard_pile: list[Card] = field(default_factory=list)
    current_player_index: int = 0
    phase: GamePhase = GamePhase.WAITING
    num_decks: int = 1
    num_rounds: int = 1
    current_round: int = 1
    drawn_card: Optional[Card] = None
    drawn_from_discard: bool = False   # Track if current draw was from discard
    finisher_id: Optional[str] = None
    players_with_final_turn: set = field(default_factory=set)
    initial_flips_done: set = field(default_factory=set)
    options: GameOptions = field(default_factory=GameOptions)

    @property
    def flip_on_discard(self) -> bool:
        return self.options.flip_on_discard

    def add_player(self, player: Player) -> bool:
        if len(self.players) >= 6:
            return False
        self.players.append(player)
        return True

    def remove_player(self, player_id: str) -> Optional[Player]:
        for i, player in enumerate(self.players):
            if player.id == player_id:
                return self.players.pop(i)
        return None

    def get_player(self, player_id: str) -> Optional[Player]:
        for player in self.players:
            if player.id == player_id:
                return player
        return None

    def current_player(self) -> Optional[Player]:
        if self.players:
            return self.players[self.current_player_index]
        return None

    def start_game(self, num_decks: int = 1, num_rounds: int = 1, options: Optional[GameOptions] = None):
        self.num_decks = num_decks
        self.num_rounds = num_rounds
        self.options = options or GameOptions()
        self.current_round = 1
        self.start_round()

    def start_round(self):
        self.deck = Deck(
            self.num_decks,
            use_jokers=self.options.use_jokers,
            lucky_swing=self.options.lucky_swing
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

        # Start discard pile with one card
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

        # Check if all players have flipped
        if len(self.initial_flips_done) == len(self.players):
            self.phase = GamePhase.PLAYING

        return True

    def draw_card(self, player_id: str, source: str) -> Optional[Card]:
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
            else:
                # No cards available anywhere - end round gracefully
                self._end_round()
                return None
        elif source == "discard" and self.discard_pile:
            card = self.discard_pile.pop()
            self.drawn_card = card
            self.drawn_from_discard = True
            return card

        return None

    def _reshuffle_discard_pile(self) -> Optional[Card]:
        """Reshuffle discard pile into deck, keeping top card. Returns drawn card or None."""
        if len(self.discard_pile) <= 1:
            # No cards to reshuffle (only top card or empty)
            return None

        # Keep the top card, take the rest
        top_card = self.discard_pile[-1]
        cards_to_reshuffle = self.discard_pile[:-1]

        # Reset face_up for reshuffled cards
        for card in cards_to_reshuffle:
            card.face_up = False

        # Add to deck and shuffle
        self.deck.add_cards(cards_to_reshuffle)

        # Keep only top card in discard pile
        self.discard_pile = [top_card]

        # Draw from the newly shuffled deck
        return self.deck.draw()

    def swap_card(self, player_id: str, position: int) -> Optional[Card]:
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
        """Check if player can discard the drawn card."""
        # Must swap if taking from discard pile (always enforced)
        if self.drawn_from_discard:
            return False
        return True

    def discard_drawn(self, player_id: str) -> bool:
        player = self.current_player()
        if not player or player.id != player_id:
            return False

        if self.drawn_card is None:
            return False

        # Cannot discard if drawn from discard pile (must swap)
        if not self.can_discard_drawn():
            return False

        self.drawn_card.face_up = True
        self.discard_pile.append(self.drawn_card)
        self.drawn_card = None

        if self.flip_on_discard:
            # Version 1: Must flip a card after discarding
            has_face_down = any(not card.face_up for card in player.cards)
            if not has_face_down:
                self._check_end_turn(player)
            # Otherwise, wait for flip_and_end_turn to be called
        else:
            # Version 2 (default): Just end the turn
            self._check_end_turn(player)
        return True

    def flip_and_end_turn(self, player_id: str, position: int) -> bool:
        """Flip a face-down card after discarding from deck draw."""
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

    def _check_end_turn(self, player: Player):
        # Check if player finished (all cards face up)
        if player.all_face_up() and self.finisher_id is None:
            self.finisher_id = player.id
            self.phase = GamePhase.FINAL_TURN
            self.players_with_final_turn.add(player.id)

        # Move to next player
        self._next_turn()

    def _next_turn(self):
        if self.phase == GamePhase.FINAL_TURN:
            # In final turn phase, track who has had their turn
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

    def _end_round(self):
        self.phase = GamePhase.ROUND_OVER

        # Reveal all cards and calculate scores
        for player in self.players:
            for card in player.cards:
                card.face_up = True
            player.calculate_score(self.options)

        # Apply Blackjack rule: score of exactly 21 becomes 0
        if self.options.blackjack:
            for player in self.players:
                if player.score == 21:
                    player.score = 0

        # Apply knock penalty if enabled (+10 if you go out but don't have lowest)
        if self.options.knock_penalty and self.finisher_id:
            finisher = self.get_player(self.finisher_id)
            if finisher:
                min_score = min(p.score for p in self.players)
                if finisher.score > min_score:
                    finisher.score += 10

        # Apply knock bonus if enabled (-5 to first player who reveals all)
        if self.options.knock_bonus and self.finisher_id:
            finisher = self.get_player(self.finisher_id)
            if finisher:
                finisher.score -= 5

        # Apply underdog bonus (-3 to lowest scorer)
        if self.options.underdog_bonus:
            min_score = min(p.score for p in self.players)
            for player in self.players:
                if player.score == min_score:
                    player.score -= 3

        # Apply tied shame (+5 to players who tie with someone else)
        if self.options.tied_shame:
            from collections import Counter
            score_counts = Counter(p.score for p in self.players)
            for player in self.players:
                if score_counts[player.score] > 1:
                    player.score += 5

        for player in self.players:
            player.total_score += player.score

        # Award round win to lowest scorer(s)
        min_score = min(p.score for p in self.players)
        for player in self.players:
            if player.score == min_score:
                player.rounds_won += 1

    def start_next_round(self) -> bool:
        if self.phase != GamePhase.ROUND_OVER:
            return False

        if self.current_round >= self.num_rounds:
            self.phase = GamePhase.GAME_OVER
            return False

        self.current_round += 1
        self.start_round()
        return True

    def discard_top(self) -> Optional[Card]:
        if self.discard_pile:
            return self.discard_pile[-1]
        return None

    def get_state(self, for_player_id: str) -> dict:
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
        }
