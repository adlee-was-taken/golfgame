/**
 * Game action executors with proper animation timing
 */

import { Page } from '@playwright/test';
import { SELECTORS } from '../utils/selectors';
import { TIMING, waitForAnimations } from '../utils/timing';

/**
 * Result of a game action
 */
export interface ActionResult {
  success: boolean;
  error?: string;
}

/**
 * Executes game actions on the page
 */
export class Actions {
  constructor(private page: Page) {}

  /**
   * Draw a card from the deck
   */
  async drawFromDeck(): Promise<ActionResult> {
    try {
      // Wait for any ongoing animations first
      await waitForAnimations(this.page);

      const deck = this.page.locator(SELECTORS.game.deck);
      await deck.waitFor({ state: 'visible', timeout: 5000 });

      // Wait for deck to become clickable (may take a moment after turn starts)
      let isClickable = false;
      for (let i = 0; i < 20; i++) {
        isClickable = await deck.evaluate(el => el.classList.contains('clickable'));
        if (isClickable) break;
        await this.page.waitForTimeout(100);
      }

      if (!isClickable) {
        return { success: false, error: 'Deck is not clickable' };
      }

      // Use force:true because deck-area has a pulsing animation that makes it "unstable"
      await deck.click({ force: true, timeout: 5000 });
      await this.page.waitForTimeout(TIMING.drawComplete);
      await waitForAnimations(this.page);
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Draw a card from the discard pile
   */
  async drawFromDiscard(): Promise<ActionResult> {
    try {
      // Wait for any ongoing animations first
      await waitForAnimations(this.page);

      const discard = this.page.locator(SELECTORS.game.discard);
      await discard.waitFor({ state: 'visible', timeout: 5000 });
      // Use force:true because deck-area has a pulsing animation
      await discard.click({ force: true, timeout: 5000 });
      await this.page.waitForTimeout(TIMING.drawComplete);
      await waitForAnimations(this.page);
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Swap drawn card with a card at position
   */
  async swapCard(position: number): Promise<ActionResult> {
    try {
      const cardSelector = SELECTORS.cards.playerCard(position);
      const card = this.page.locator(cardSelector);
      await card.waitFor({ state: 'visible', timeout: 5000 });
      // Use force:true to handle any CSS animations
      await card.click({ force: true, timeout: 5000 });
      await this.page.waitForTimeout(TIMING.swapComplete);
      await waitForAnimations(this.page);
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Discard the drawn card
   */
  async discardDrawn(): Promise<ActionResult> {
    try {
      const discardBtn = this.page.locator(SELECTORS.game.discardBtn);
      await discardBtn.click();
      await this.page.waitForTimeout(TIMING.pauseAfterDiscard);
      await waitForAnimations(this.page);
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Flip a card at position
   */
  async flipCard(position: number): Promise<ActionResult> {
    try {
      // Wait for animations before clicking
      await waitForAnimations(this.page);

      const cardSelector = SELECTORS.cards.playerCard(position);
      const card = this.page.locator(cardSelector);
      await card.waitFor({ state: 'visible', timeout: 5000 });
      // Use force:true to handle any CSS animations
      await card.click({ force: true, timeout: 5000 });
      await this.page.waitForTimeout(TIMING.flipComplete);
      await waitForAnimations(this.page);
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Skip the optional flip (endgame mode)
   */
  async skipFlip(): Promise<ActionResult> {
    try {
      const skipBtn = this.page.locator(SELECTORS.game.skipFlipBtn);
      await skipBtn.click();
      await this.page.waitForTimeout(TIMING.turnTransition);
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Knock early (flip all remaining cards)
   */
  async knockEarly(): Promise<ActionResult> {
    try {
      const knockBtn = this.page.locator(SELECTORS.game.knockEarlyBtn);
      await knockBtn.click();
      await this.page.waitForTimeout(TIMING.swapComplete);
      await waitForAnimations(this.page);
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Wait for turn to start
   */
  async waitForMyTurn(timeout: number = 30000): Promise<boolean> {
    try {
      await this.page.waitForFunction(
        (sel) => {
          const deckArea = document.querySelector(sel);
          return deckArea?.classList.contains('your-turn-to-draw');
        },
        SELECTORS.game.deckArea,
        { timeout }
      );
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Wait for game phase change
   */
  async waitForPhase(
    expectedPhases: string[],
    timeout: number = 30000
  ): Promise<boolean> {
    const start = Date.now();

    while (Date.now() - start < timeout) {
      // Check for round over
      const nextRoundBtn = this.page.locator(SELECTORS.game.nextRoundBtn);
      if (await nextRoundBtn.isVisible().catch(() => false)) {
        if (expectedPhases.includes('round_over')) return true;
      }

      // Check for game over
      const newGameBtn = this.page.locator(SELECTORS.game.newGameBtn);
      if (await newGameBtn.isVisible().catch(() => false)) {
        if (expectedPhases.includes('game_over')) return true;
      }

      // Check for final turn
      const finalTurnBadge = this.page.locator(SELECTORS.game.finalTurnBadge);
      if (await finalTurnBadge.isVisible().catch(() => false)) {
        if (expectedPhases.includes('final_turn')) return true;
      }

      // Check for my turn (playing phase)
      const deckArea = this.page.locator(SELECTORS.game.deckArea);
      const isMyTurn = await deckArea.evaluate(el =>
        el.classList.contains('your-turn-to-draw')
      ).catch(() => false);
      if (isMyTurn && expectedPhases.includes('playing')) return true;

      await this.page.waitForTimeout(100);
    }

    return false;
  }

  /**
   * Click the "Next Hole" button to start next round
   */
  async nextRound(): Promise<ActionResult> {
    try {
      const btn = this.page.locator(SELECTORS.game.nextRoundBtn);
      await btn.waitFor({ state: 'visible', timeout: 5000 });
      await btn.click();
      await this.page.waitForTimeout(TIMING.roundOverDelay);
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Click the "New Game" button to return to waiting room
   */
  async newGame(): Promise<ActionResult> {
    try {
      const btn = this.page.locator(SELECTORS.game.newGameBtn);
      await btn.waitFor({ state: 'visible', timeout: 5000 });
      await btn.click();
      await this.page.waitForTimeout(TIMING.turnTransition);
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  }

  /**
   * Wait for animations to complete
   */
  async waitForAnimationComplete(timeout: number = 5000): Promise<void> {
    await waitForAnimations(this.page, timeout);
  }
}
