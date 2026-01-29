/**
 * Screenshot validator - captures screenshots and validates visual states
 */

import { Page, expect } from '@playwright/test';
import { SELECTORS } from '../utils/selectors';

/**
 * Visual expectation result
 */
export interface VisualExpectation {
  passed: boolean;
  selector: string;
  expected: string;
  actual?: string;
  error?: string;
}

/**
 * Screenshot capture result
 */
export interface CaptureResult {
  label: string;
  buffer: Buffer;
  timestamp: number;
  phase?: string;
}

/**
 * ScreenshotValidator - semantic visual validation
 */
export class ScreenshotValidator {
  private captures: CaptureResult[] = [];

  constructor(private page: Page) {}

  /**
   * Capture a screenshot with metadata
   */
  async capture(label: string, phase?: string): Promise<CaptureResult> {
    const buffer = await this.page.screenshot({ fullPage: true });
    const result: CaptureResult = {
      label,
      buffer,
      timestamp: Date.now(),
      phase,
    };
    this.captures.push(result);
    return result;
  }

  /**
   * Capture element-specific screenshot
   */
  async captureElement(
    selector: string,
    label: string
  ): Promise<CaptureResult | null> {
    try {
      const element = this.page.locator(selector);
      const buffer = await element.screenshot();
      const result: CaptureResult = {
        label,
        buffer,
        timestamp: Date.now(),
      };
      this.captures.push(result);
      return result;
    } catch {
      return null;
    }
  }

  /**
   * Get all captures
   */
  getCaptures(): CaptureResult[] {
    return [...this.captures];
  }

  /**
   * Clear captures
   */
  clearCaptures(): void {
    this.captures = [];
  }

  // ============== Semantic Validators ==============

  /**
   * Expect element to be visible
   */
  async expectVisible(selector: string): Promise<VisualExpectation> {
    try {
      const el = this.page.locator(selector);
      await expect(el).toBeVisible({ timeout: 2000 });
      return { passed: true, selector, expected: 'visible' };
    } catch (error) {
      return {
        passed: false,
        selector,
        expected: 'visible',
        actual: 'not visible',
        error: String(error),
      };
    }
  }

  /**
   * Expect element to be hidden
   */
  async expectNotVisible(selector: string): Promise<VisualExpectation> {
    try {
      const el = this.page.locator(selector);
      await expect(el).toBeHidden({ timeout: 2000 });
      return { passed: true, selector, expected: 'hidden' };
    } catch (error) {
      return {
        passed: false,
        selector,
        expected: 'hidden',
        actual: 'visible',
        error: String(error),
      };
    }
  }

  /**
   * Expect element to have specific CSS class
   */
  async expectHasClass(
    selector: string,
    className: string
  ): Promise<VisualExpectation> {
    try {
      const el = this.page.locator(selector);
      const hasClass = await el.evaluate(
        (node, cls) => node.classList.contains(cls),
        className
      );

      return {
        passed: hasClass,
        selector,
        expected: `has class "${className}"`,
        actual: hasClass ? `has class "${className}"` : `missing class "${className}"`,
      };
    } catch (error) {
      return {
        passed: false,
        selector,
        expected: `has class "${className}"`,
        error: String(error),
      };
    }
  }

  /**
   * Expect element to NOT have specific CSS class
   */
  async expectNoClass(
    selector: string,
    className: string
  ): Promise<VisualExpectation> {
    try {
      const el = this.page.locator(selector);
      const hasClass = await el.evaluate(
        (node, cls) => node.classList.contains(cls),
        className
      );

      return {
        passed: !hasClass,
        selector,
        expected: `no class "${className}"`,
        actual: hasClass ? `has class "${className}"` : `no class "${className}"`,
      };
    } catch (error) {
      return {
        passed: false,
        selector,
        expected: `no class "${className}"`,
        error: String(error),
      };
    }
  }

  /**
   * Expect text content to match
   */
  async expectText(
    selector: string,
    expected: string | RegExp
  ): Promise<VisualExpectation> {
    try {
      const el = this.page.locator(selector);
      const text = await el.textContent() || '';

      const matches = expected instanceof RegExp
        ? expected.test(text)
        : text.includes(expected);

      return {
        passed: matches,
        selector,
        expected: String(expected),
        actual: text,
      };
    } catch (error) {
      return {
        passed: false,
        selector,
        expected: String(expected),
        error: String(error),
      };
    }
  }

  /**
   * Expect specific number of elements
   */
  async expectCount(
    selector: string,
    count: number
  ): Promise<VisualExpectation> {
    try {
      const els = this.page.locator(selector);
      const actual = await els.count();

      return {
        passed: actual === count,
        selector,
        expected: `count=${count}`,
        actual: `count=${actual}`,
      };
    } catch (error) {
      return {
        passed: false,
        selector,
        expected: `count=${count}`,
        error: String(error),
      };
    }
  }

  /**
   * Expect card at position to be face-up
   */
  async expectCardFaceUp(position: number): Promise<VisualExpectation> {
    const selector = SELECTORS.cards.playerCard(position);
    return this.expectHasClass(selector, 'card-front');
  }

  /**
   * Expect card at position to be face-down
   */
  async expectCardFaceDown(position: number): Promise<VisualExpectation> {
    const selector = SELECTORS.cards.playerCard(position);
    return this.expectHasClass(selector, 'card-back');
  }

  /**
   * Expect card at position to be clickable
   */
  async expectCardClickable(position: number): Promise<VisualExpectation> {
    const selector = SELECTORS.cards.playerCard(position);
    return this.expectHasClass(selector, 'clickable');
  }

  /**
   * Expect deck to be clickable
   */
  async expectDeckClickable(): Promise<VisualExpectation> {
    return this.expectHasClass(SELECTORS.game.deck, 'clickable');
  }

  /**
   * Expect discard pile to have a card
   */
  async expectDiscardHasCard(): Promise<VisualExpectation> {
    return this.expectHasClass(SELECTORS.game.discard, 'has-card');
  }

  /**
   * Expect final turn badge visible
   */
  async expectFinalTurnBadge(): Promise<VisualExpectation> {
    return this.expectVisible(SELECTORS.game.finalTurnBadge);
  }

  /**
   * Expect held card floating visible
   */
  async expectHeldCardVisible(): Promise<VisualExpectation> {
    return this.expectVisible(SELECTORS.game.heldCardFloating);
  }

  /**
   * Expect held card floating hidden
   */
  async expectHeldCardHidden(): Promise<VisualExpectation> {
    return this.expectNotVisible(SELECTORS.game.heldCardFloating);
  }

  /**
   * Expect opponent to have current-turn class
   */
  async expectOpponentCurrentTurn(opponentIndex: number): Promise<VisualExpectation> {
    const selector = SELECTORS.cards.opponentArea(opponentIndex);
    return this.expectHasClass(selector, 'current-turn');
  }

  /**
   * Expect status message to contain text
   */
  async expectStatusMessage(text: string | RegExp): Promise<VisualExpectation> {
    return this.expectText(SELECTORS.game.statusMessage, text);
  }

  /**
   * Run a batch of visual checks
   */
  async runChecks(
    checks: Array<() => Promise<VisualExpectation>>
  ): Promise<{ passed: number; failed: number; results: VisualExpectation[] }> {
    const results: VisualExpectation[] = [];
    let passed = 0;
    let failed = 0;

    for (const check of checks) {
      const result = await check();
      results.push(result);
      if (result.passed) {
        passed++;
      } else {
        failed++;
      }
    }

    return { passed, failed, results };
  }
}
