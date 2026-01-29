/**
 * AI decision-making logic for the test bot
 * Simplified port of server/ai.py for client-side decision making
 */

import { CardState, PlayerState } from './state-parser';

/**
 * Card value mapping (standard rules)
 */
const CARD_VALUES: Record<string, number> = {
  '★': -2,  // Joker
  '2': -2,
  'A': 1,
  'K': 0,
  '3': 3,
  '4': 4,
  '5': 5,
  '6': 6,
  '7': 7,
  '8': 8,
  '9': 9,
  '10': 10,
  'J': 10,
  'Q': 10,
};

/**
 * Game options that affect card values
 */
export interface GameOptions {
  superKings?: boolean;  // K = -2 instead of 0
  tenPenny?: boolean;    // 10 = 1 instead of 10
  oneEyedJacks?: boolean; // J♥/J♠ = 0
  eagleEye?: boolean;    // Jokers +2 unpaired, -4 paired
}

/**
 * Get the point value of a card
 */
export function getCardValue(card: { rank: string | null; suit?: string | null }, options: GameOptions = {}): number {
  if (!card.rank) return 5; // Unknown card estimated at average

  let value = CARD_VALUES[card.rank] ?? 5;

  // Super Kings rule
  if (options.superKings && card.rank === 'K') {
    value = -2;
  }

  // Ten Penny rule
  if (options.tenPenny && card.rank === '10') {
    value = 1;
  }

  // One-Eyed Jacks rule
  if (options.oneEyedJacks && card.rank === 'J') {
    if (card.suit === 'hearts' || card.suit === 'spades') {
      value = 0;
    }
  }

  // Eagle Eye rule (Jokers are +2 when unpaired)
  // Note: We can't know pairing status from just one card, so this is informational
  if (options.eagleEye && card.rank === '★') {
    value = 2; // Default to unpaired value
  }

  return value;
}

/**
 * Get column partner position (cards that can form pairs)
 * Column pairs: (0,3), (1,4), (2,5)
 */
export function getColumnPartner(position: number): number {
  return position < 3 ? position + 3 : position - 3;
}

/**
 * AI Brain - makes decisions for the test bot
 */
export class AIBrain {
  constructor(private options: GameOptions = {}) {}

  /**
   * Choose 2 cards for initial flip
   * Prefer different columns for better pair information
   */
  chooseInitialFlips(cards: CardState[]): number[] {
    const faceDown = cards.filter(c => !c.faceUp);
    if (faceDown.length === 0) return [];
    if (faceDown.length === 1) return [faceDown[0].position];

    // Good initial flip patterns (different columns)
    const patterns = [
      [0, 4], [2, 4], [3, 1], [5, 1],
      [0, 5], [2, 3],
    ];

    // Find a valid pattern
    for (const pattern of patterns) {
      const valid = pattern.every(p =>
        faceDown.some(c => c.position === p)
      );
      if (valid) return pattern;
    }

    // Fallback: pick any two face-down cards in different columns
    const result: number[] = [];
    const usedColumns = new Set<number>();

    for (const card of faceDown) {
      const col = card.position % 3;
      if (!usedColumns.has(col)) {
        result.push(card.position);
        usedColumns.add(col);
        if (result.length === 2) break;
      }
    }

    // If we couldn't get different columns, just take first two
    if (result.length < 2) {
      for (const card of faceDown) {
        if (!result.includes(card.position)) {
          result.push(card.position);
          if (result.length === 2) break;
        }
      }
    }

    return result;
  }

  /**
   * Decide whether to take from discard pile
   */
  shouldTakeDiscard(
    discardCard: { rank: string; suit: string } | null,
    myCards: CardState[]
  ): boolean {
    if (!discardCard) return false;

    const value = getCardValue(discardCard, this.options);

    // Always take Jokers and Kings (excellent cards)
    if (discardCard.rank === '★' || discardCard.rank === 'K') {
      return true;
    }

    // Always take negative/low value cards
    if (value <= 2) {
      return true;
    }

    // Check if discard can form a pair with a visible card
    for (const card of myCards) {
      if (card.faceUp && card.rank === discardCard.rank) {
        const partnerPos = getColumnPartner(card.position);
        const partnerCard = myCards.find(c => c.position === partnerPos);

        // Only pair if partner is face-down (unknown) - pairing negative cards is wasteful
        if (partnerCard && !partnerCard.faceUp && value > 0) {
          return true;
        }
      }
    }

    // Take medium cards if we have visible bad cards to replace
    if (value <= 5) {
      for (const card of myCards) {
        if (card.faceUp && card.rank) {
          const cardValue = getCardValue(card, this.options);
          if (cardValue > value + 1) {
            return true;
          }
        }
      }
    }

    // Default: draw from deck
    return false;
  }

  /**
   * Choose position to swap drawn card, or null to discard
   */
  chooseSwapPosition(
    drawnCard: { rank: string; suit?: string | null },
    myCards: CardState[],
    mustSwap: boolean = false  // True if drawn from discard
  ): number | null {
    const drawnValue = getCardValue(drawnCard, this.options);

    // Calculate score for each position
    const scores: { pos: number; score: number }[] = [];

    for (let pos = 0; pos < 6; pos++) {
      const card = myCards.find(c => c.position === pos);
      if (!card) continue;

      let score = 0;
      const partnerPos = getColumnPartner(pos);
      const partnerCard = myCards.find(c => c.position === partnerPos);

      // Check for pair creation
      if (partnerCard?.faceUp && partnerCard.rank === drawnCard.rank) {
        const partnerValue = getCardValue(partnerCard, this.options);

        if (drawnValue >= 0) {
          // Good pair! Both cards become 0
          score += drawnValue + partnerValue;
        } else {
          // Pairing negative cards is wasteful (unless special rules)
          score -= Math.abs(drawnValue) * 2;
        }
      }

      // Point improvement
      if (card.faceUp && card.rank) {
        const currentValue = getCardValue(card, this.options);
        score += currentValue - drawnValue;
      } else {
        // Face-down card - expected value ~4.5
        const expectedHidden = 4.5;
        score += (expectedHidden - drawnValue) * 0.7; // Discount for uncertainty
      }

      // Bonus for revealing hidden cards with good drawn cards
      if (!card.faceUp && drawnValue <= 3) {
        score += 2;
      }

      scores.push({ pos, score });
    }

    // Sort by score descending
    scores.sort((a, b) => b.score - a.score);

    // If best score is positive, swap there
    if (scores.length > 0 && scores[0].score > 0) {
      return scores[0].pos;
    }

    // Must swap if drawn from discard
    if (mustSwap && scores.length > 0) {
      // Find a face-down position if possible
      const faceDownScores = scores.filter(s => {
        const card = myCards.find(c => c.position === s.pos);
        return card && !card.faceUp;
      });

      if (faceDownScores.length > 0) {
        return faceDownScores[0].pos;
      }

      // Otherwise take the best score even if negative
      return scores[0].pos;
    }

    // Discard the drawn card
    return null;
  }

  /**
   * Choose which card to flip after discarding
   */
  chooseFlipPosition(myCards: CardState[]): number {
    const faceDown = myCards.filter(c => !c.faceUp);
    if (faceDown.length === 0) return 0;

    // Prefer flipping cards where the partner is visible (pair info)
    for (const card of faceDown) {
      const partnerPos = getColumnPartner(card.position);
      const partner = myCards.find(c => c.position === partnerPos);
      if (partner?.faceUp) {
        return card.position;
      }
    }

    // Random face-down card
    return faceDown[Math.floor(Math.random() * faceDown.length)].position;
  }

  /**
   * Decide whether to skip optional flip (endgame mode)
   */
  shouldSkipFlip(myCards: CardState[]): boolean {
    const faceDown = myCards.filter(c => !c.faceUp);

    // Always flip if we have many hidden cards
    if (faceDown.length >= 3) {
      return false;
    }

    // Small chance to skip with 1-2 hidden cards
    return faceDown.length <= 2 && Math.random() < 0.15;
  }

  /**
   * Calculate estimated hand score
   */
  estimateScore(cards: CardState[]): number {
    let score = 0;

    // Group cards by column for pair detection
    const columns: (CardState | undefined)[][] = [
      [cards.find(c => c.position === 0), cards.find(c => c.position === 3)],
      [cards.find(c => c.position === 1), cards.find(c => c.position === 4)],
      [cards.find(c => c.position === 2), cards.find(c => c.position === 5)],
    ];

    for (const [top, bottom] of columns) {
      if (top?.faceUp && bottom?.faceUp) {
        if (top.rank === bottom.rank) {
          // Pair - contributes 0
          continue;
        }
        score += getCardValue(top, this.options);
        score += getCardValue(bottom, this.options);
      } else if (top?.faceUp) {
        score += getCardValue(top, this.options);
        score += 4.5; // Estimate for hidden bottom
      } else if (bottom?.faceUp) {
        score += 4.5; // Estimate for hidden top
        score += getCardValue(bottom, this.options);
      } else {
        score += 9; // Both hidden, estimate 4.5 each
      }
    }

    return Math.round(score);
  }
}
