import { Page, Locator } from '@playwright/test';
import { SELECTORS } from '../utils/selectors';

/**
 * Represents a card's state as extracted from the DOM
 */
export interface CardState {
  position: number;
  faceUp: boolean;
  rank: string | null;
  suit: string | null;
  clickable: boolean;
  selected: boolean;
}

/**
 * Represents a player's state as extracted from the DOM
 */
export interface PlayerState {
  name: string;
  cards: CardState[];
  isCurrentTurn: boolean;
  score: number | null;
}

/**
 * Represents the overall game state as extracted from the DOM
 */
export interface ParsedGameState {
  phase: GamePhase;
  currentRound: number;
  totalRounds: number;
  statusMessage: string;
  isFinalTurn: boolean;
  myPlayer: PlayerState | null;
  opponents: PlayerState[];
  deck: {
    clickable: boolean;
  };
  discard: {
    hasCard: boolean;
    clickable: boolean;
    pickedUp: boolean;
    topCard: { rank: string; suit: string } | null;
  };
  heldCard: {
    visible: boolean;
    card: { rank: string; suit: string } | null;
  };
  canDiscard: boolean;
  canSkipFlip: boolean;
  canKnockEarly: boolean;
}

export type GamePhase =
  | 'lobby'
  | 'waiting'
  | 'initial_flip'
  | 'playing'
  | 'waiting_for_flip'
  | 'final_turn'
  | 'round_over'
  | 'game_over';

/**
 * Parses game state from the DOM
 * This allows visual validation - the DOM should reflect the internal game state
 */
export class StateParser {
  constructor(private page: Page) {}

  /**
   * Get the current screen/phase
   */
  async getPhase(): Promise<GamePhase> {
    // Check which screen is active
    const lobbyVisible = await this.isVisible(SELECTORS.screens.lobby);
    if (lobbyVisible) return 'lobby';

    const waitingVisible = await this.isVisible(SELECTORS.screens.waiting);
    if (waitingVisible) return 'waiting';

    const gameVisible = await this.isVisible(SELECTORS.screens.game);
    if (!gameVisible) return 'lobby';

    // We're in the game screen - determine game phase
    const statusText = await this.getStatusMessage();
    const gameButtons = await this.isVisible(SELECTORS.game.gameButtons);

    // Check for game over - Final Results modal or "New Game" button visible
    const finalResultsModal = this.page.locator('#final-results-modal');
    if (await finalResultsModal.isVisible().catch(() => false)) {
      return 'game_over';
    }
    const newGameBtn = this.page.locator(SELECTORS.game.newGameBtn);
    if (await newGameBtn.isVisible().catch(() => false)) {
      return 'game_over';
    }

    // Check for round over (Next Hole button visible)
    const nextRoundBtn = this.page.locator(SELECTORS.game.nextRoundBtn);
    if (await nextRoundBtn.isVisible().catch(() => false)) {
      // Check if this is the last round - if so, might be transitioning to game_over
      const currentRound = await this.getCurrentRound();
      const totalRounds = await this.getTotalRounds();

      // If on last round and all cards revealed, this is effectively game_over
      if (currentRound >= totalRounds) {
        // Check the button text - if it doesn't mention "Next", might be game over
        const btnText = await nextRoundBtn.textContent().catch(() => '');
        if (btnText && !btnText.toLowerCase().includes('next')) {
          return 'game_over';
        }
        // Still round_over but will transition to game_over soon
      }
      return 'round_over';
    }

    // Check for final turn badge
    const finalTurnBadge = this.page.locator(SELECTORS.game.finalTurnBadge);
    if (await finalTurnBadge.isVisible().catch(() => false)) {
      return 'final_turn';
    }

    // Check if waiting for initial flip
    if (statusText.toLowerCase().includes('flip') &&
        statusText.toLowerCase().includes('card')) {
      // Could be initial flip or flip after discard
      const skipFlipBtn = this.page.locator(SELECTORS.game.skipFlipBtn);
      if (await skipFlipBtn.isVisible().catch(() => false)) {
        return 'waiting_for_flip';
      }

      // Check if we're in initial flip phase (multiple cards to flip)
      const myCards = await this.getMyCards();
      const faceUpCount = myCards.filter(c => c.faceUp).length;
      if (faceUpCount < 2) {
        return 'initial_flip';
      }
      return 'waiting_for_flip';
    }

    return 'playing';
  }

  /**
   * Get full parsed game state
   */
  async getState(): Promise<ParsedGameState> {
    const phase = await this.getPhase();

    return {
      phase,
      currentRound: await this.getCurrentRound(),
      totalRounds: await this.getTotalRounds(),
      statusMessage: await this.getStatusMessage(),
      isFinalTurn: await this.isFinalTurn(),
      myPlayer: await this.getMyPlayer(),
      opponents: await this.getOpponents(),
      deck: {
        clickable: await this.isDeckClickable(),
      },
      discard: {
        hasCard: await this.discardHasCard(),
        clickable: await this.isDiscardClickable(),
        pickedUp: await this.isDiscardPickedUp(),
        topCard: await this.getDiscardTop(),
      },
      heldCard: {
        visible: await this.isHeldCardVisible(),
        card: await this.getHeldCard(),
      },
      canDiscard: await this.isVisible(SELECTORS.game.discardBtn),
      canSkipFlip: await this.isVisible(SELECTORS.game.skipFlipBtn),
      canKnockEarly: await this.isVisible(SELECTORS.game.knockEarlyBtn),
    };
  }

  /**
   * Get current round number
   */
  async getCurrentRound(): Promise<number> {
    const text = await this.getText(SELECTORS.game.currentRound);
    return parseInt(text) || 1;
  }

  /**
   * Get total rounds
   */
  async getTotalRounds(): Promise<number> {
    const text = await this.getText(SELECTORS.game.totalRounds);
    return parseInt(text) || 9;
  }

  /**
   * Get status message text
   */
  async getStatusMessage(): Promise<string> {
    return this.getText(SELECTORS.game.statusMessage);
  }

  /**
   * Check if final turn badge is visible
   */
  async isFinalTurn(): Promise<boolean> {
    return this.isVisible(SELECTORS.game.finalTurnBadge);
  }

  /**
   * Get local player's state
   */
  async getMyPlayer(): Promise<PlayerState | null> {
    const playerArea = this.page.locator(SELECTORS.game.playerArea).first();
    if (!await playerArea.isVisible().catch(() => false)) {
      return null;
    }

    const nameEl = playerArea.locator('.player-name');
    const name = await nameEl.textContent().catch(() => 'You') || 'You';

    const scoreEl = playerArea.locator(SELECTORS.game.yourScore);
    const scoreText = await scoreEl.textContent().catch(() => '0') || '0';
    const score = parseInt(scoreText) || 0;

    const cards = await this.getMyCards();
    const isCurrentTurn = await this.isMyTurn();

    return { name, cards, isCurrentTurn, score };
  }

  /**
   * Get cards for local player
   */
  async getMyCards(): Promise<CardState[]> {
    const cards: CardState[] = [];
    const cardContainer = this.page.locator(SELECTORS.game.playerCards);

    const cardEls = cardContainer.locator('.card, .card-slot .card');
    const count = await cardEls.count();

    for (let i = 0; i < Math.min(count, 6); i++) {
      const cardEl = cardEls.nth(i);
      cards.push(await this.parseCard(cardEl, i));
    }

    return cards;
  }

  /**
   * Get opponent players' states
   */
  async getOpponents(): Promise<PlayerState[]> {
    const opponents: PlayerState[] = [];
    const opponentAreas = this.page.locator('.opponent-area');
    const count = await opponentAreas.count();

    for (let i = 0; i < count; i++) {
      const area = opponentAreas.nth(i);
      const nameEl = area.locator('.opponent-name');
      const name = await nameEl.textContent().catch(() => `Opponent ${i + 1}`) || `Opponent ${i + 1}`;

      const scoreEl = area.locator('.opponent-showing');
      const scoreText = await scoreEl.textContent().catch(() => null);
      const score = scoreText ? parseInt(scoreText) : null;

      const isCurrentTurn = await area.evaluate(el =>
        el.classList.contains('current-turn')
      );

      const cards: CardState[] = [];
      const cardEls = area.locator('.card-grid .card');
      const cardCount = await cardEls.count();

      for (let j = 0; j < Math.min(cardCount, 6); j++) {
        cards.push(await this.parseCard(cardEls.nth(j), j));
      }

      opponents.push({ name, cards, isCurrentTurn, score });
    }

    return opponents;
  }

  /**
   * Parse a single card element
   */
  private async parseCard(cardEl: Locator, position: number): Promise<CardState> {
    const classList = await cardEl.evaluate(el => Array.from(el.classList));

    // Face-down cards have 'card-back' class, face-up have 'card-front' class
    const faceUp = classList.includes('card-front');
    const clickable = classList.includes('clickable');
    const selected = classList.includes('selected');

    let rank: string | null = null;
    let suit: string | null = null;

    if (faceUp) {
      const content = await cardEl.textContent().catch(() => '') || '';

      // Check for joker
      if (classList.includes('joker') || content.toLowerCase().includes('joker')) {
        rank = '★';
        // Determine suit from icon
        if (content.includes('🐉')) {
          suit = 'hearts';
        } else if (content.includes('👹')) {
          suit = 'spades';
        }
      } else {
        // Parse rank and suit from text
        const lines = content.split('\n').map(l => l.trim()).filter(l => l);
        if (lines.length >= 2) {
          rank = lines[0];
          suit = this.parseSuitSymbol(lines[1]);
        } else if (lines.length === 1) {
          // Try to extract rank from combined text
          const text = lines[0];
          const rankMatch = text.match(/^([AKQJ]|10|[2-9])/);
          if (rankMatch) {
            rank = rankMatch[1];
            const suitPart = text.slice(rank.length);
            suit = this.parseSuitSymbol(suitPart);
          }
        }
      }
    }

    return { position, faceUp, rank, suit, clickable, selected };
  }

  /**
   * Parse suit symbol to suit name
   */
  private parseSuitSymbol(symbol: string): string | null {
    const cleaned = symbol.trim();
    if (cleaned.includes('♥') || cleaned.includes('hearts')) return 'hearts';
    if (cleaned.includes('♦') || cleaned.includes('diamonds')) return 'diamonds';
    if (cleaned.includes('♣') || cleaned.includes('clubs')) return 'clubs';
    if (cleaned.includes('♠') || cleaned.includes('spades')) return 'spades';
    return null;
  }

  /**
   * Check if it's the local player's turn
   */
  async isMyTurn(): Promise<boolean> {
    // Check if deck area has your-turn-to-draw class
    const deckArea = this.page.locator(SELECTORS.game.deckArea);
    const hasClass = await deckArea.evaluate(el =>
      el.classList.contains('your-turn-to-draw')
    ).catch(() => false);

    if (hasClass) return true;

    // Check status message
    const status = await this.getStatusMessage();
    const statusLower = status.toLowerCase();

    // Various indicators that it's our turn
    if (statusLower.includes('your turn')) return true;
    if (statusLower.includes('select') && statusLower.includes('card')) return true; // Initial flip
    if (statusLower.includes('flip a card')) return true;
    if (statusLower.includes('choose a card')) return true;

    // Check if our cards are clickable (another indicator)
    const clickableCards = await this.getClickablePositions();
    if (clickableCards.length > 0) return true;

    return false;
  }

  /**
   * Check if deck is clickable
   */
  async isDeckClickable(): Promise<boolean> {
    const deck = this.page.locator(SELECTORS.game.deck);
    return deck.evaluate(el => el.classList.contains('clickable')).catch(() => false);
  }

  /**
   * Check if discard pile has a card
   */
  async discardHasCard(): Promise<boolean> {
    const discard = this.page.locator(SELECTORS.game.discard);
    return discard.evaluate(el =>
      el.classList.contains('has-card') || el.classList.contains('card-front')
    ).catch(() => false);
  }

  /**
   * Check if discard is clickable
   */
  async isDiscardClickable(): Promise<boolean> {
    const discard = this.page.locator(SELECTORS.game.discard);
    return discard.evaluate(el =>
      el.classList.contains('clickable') && !el.classList.contains('disabled')
    ).catch(() => false);
  }

  /**
   * Check if discard card is picked up (floating)
   */
  async isDiscardPickedUp(): Promise<boolean> {
    const discard = this.page.locator(SELECTORS.game.discard);
    return discard.evaluate(el => el.classList.contains('picked-up')).catch(() => false);
  }

  /**
   * Get the top card of the discard pile
   */
  async getDiscardTop(): Promise<{ rank: string; suit: string } | null> {
    const hasCard = await this.discardHasCard();
    if (!hasCard) return null;

    const content = await this.page.locator(SELECTORS.game.discardContent).textContent()
      .catch(() => null);
    if (!content) return null;

    return this.parseCardContent(content);
  }

  /**
   * Check if held card is visible
   */
  async isHeldCardVisible(): Promise<boolean> {
    const floating = this.page.locator(SELECTORS.game.heldCardFloating);
    return floating.isVisible().catch(() => false);
  }

  /**
   * Get held card details
   */
  async getHeldCard(): Promise<{ rank: string; suit: string } | null> {
    const visible = await this.isHeldCardVisible();
    if (!visible) return null;

    const content = await this.page.locator(SELECTORS.game.heldCardFloatingContent)
      .textContent().catch(() => null);
    if (!content) return null;

    return this.parseCardContent(content);
  }

  /**
   * Parse card content text (from held card, discard, etc.)
   */
  private parseCardContent(content: string): { rank: string; suit: string } | null {
    // Handle jokers
    if (content.toLowerCase().includes('joker')) {
      const suit = content.includes('🐉') ? 'hearts' : 'spades';
      return { rank: '★', suit };
    }

    // Try to parse rank and suit
    // Content may be "7\n♥" (with newline) or "7♥" (combined)
    const lines = content.split('\n').map(l => l.trim()).filter(l => l);

    if (lines.length >= 2) {
      // Two separate lines
      return {
        rank: lines[0],
        suit: this.parseSuitSymbol(lines[1]) || 'unknown',
      };
    } else if (lines.length === 1) {
      const text = lines[0];
      // Try to extract rank (A, K, Q, J, 10, or 2-9)
      const rankMatch = text.match(/^(10|[AKQJ2-9])/);
      if (rankMatch) {
        const rank = rankMatch[1];
        const suitPart = text.slice(rank.length);
        const suit = this.parseSuitSymbol(suitPart);
        if (suit) {
          return { rank, suit };
        }
      }
    }

    return null;
  }

  /**
   * Count face-up cards for local player
   */
  async countFaceUpCards(): Promise<number> {
    const cards = await this.getMyCards();
    return cards.filter(c => c.faceUp).length;
  }

  /**
   * Count face-down cards for local player
   */
  async countFaceDownCards(): Promise<number> {
    const cards = await this.getMyCards();
    return cards.filter(c => !c.faceUp).length;
  }

  /**
   * Get positions of clickable cards
   */
  async getClickablePositions(): Promise<number[]> {
    const cards = await this.getMyCards();
    return cards.filter(c => c.clickable).map(c => c.position);
  }

  /**
   * Get positions of face-down cards
   */
  async getFaceDownPositions(): Promise<number[]> {
    const cards = await this.getMyCards();
    return cards.filter(c => !c.faceUp).map(c => c.position);
  }

  // Helper methods
  private async isVisible(selector: string): Promise<boolean> {
    const el = this.page.locator(selector);
    return el.isVisible().catch(() => false);
  }

  private async getText(selector: string): Promise<string> {
    const el = this.page.locator(selector);
    return (await el.textContent().catch(() => '')) || '';
  }
}
