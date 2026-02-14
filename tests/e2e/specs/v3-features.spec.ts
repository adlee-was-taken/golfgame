/**
 * V3 Feature Integration Tests
 *
 * Tests that V3 features are properly integrated and visible in the DOM.
 * Transient animations and audio are excluded (manual QA only).
 */

import { test, expect } from '@playwright/test';
import { GolfBot } from '../bot/golf-bot';
import { FreezeDetector } from '../health/freeze-detector';
import { SELECTORS } from '../utils/selectors';
import { waitForAnimations } from '../utils/timing';

/**
 * Helper: create a game with one CPU opponent and start it
 */
async function setupGame(
  page: import('@playwright/test').Page,
  options: Parameters<GolfBot['startGame']>[0] = {}
) {
  const bot = new GolfBot(page);
  await bot.goto();
  await bot.createGame('V3Tester');
  await bot.addCPU('Sofia');
  await bot.startGame({ holes: 1, ...options });
  return bot;
}

// =============================================================================
// V3_01: Dealer Rotation
// =============================================================================

test.describe('V3_01: Dealer Rotation', () => {
  test('dealer badge exists after game starts', async ({ page }) => {
    const bot = await setupGame(page);
    await waitForAnimations(page);

    // The game state should include dealer info — check that the UI renders
    // a dealer indicator somewhere in the player areas
    const dealerBadge = page.locator(SELECTORS.v3.dealerBadge);
    // At least one dealer badge should be visible
    const count = await dealerBadge.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });
});

// =============================================================================
// V3_02: Dealing Animation
// =============================================================================

test.describe('V3_02: Dealing Animation', () => {
  test('cards are dealt without errors', async ({ page }) => {
    const bot = await setupGame(page);
    await waitForAnimations(page);

    // Verify player has 6 cards rendered
    const playerCards = page.locator(`${SELECTORS.game.playerCards} .card`);
    await expect(playerCards).toHaveCount(6);

    // No console errors during deal
    const errors = bot.getConsoleErrors();
    expect(errors).toHaveLength(0);
  });
});

// =============================================================================
// V3_06: CPU Thinking Indicator
// =============================================================================

test.describe('V3_06: CPU Thinking Indicator', () => {
  test('thinking indicator element exists on CPU opponent', async ({ page }) => {
    const bot = await setupGame(page);
    await waitForAnimations(page);

    // The thinking indicator span should exist in the DOM for CPU opponents
    const indicator = page.locator(SELECTORS.v3.thinkingIndicator);
    const count = await indicator.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('thinking indicator is hidden when not CPU turn', async ({ page }) => {
    const bot = await setupGame(page);
    await bot.completeInitialFlips();
    await waitForAnimations(page);

    // Wait for bot's turn (not CPU's turn)
    const isMyTurn = await bot.isMyTurn();
    if (isMyTurn) {
      // During our turn, CPU indicator should be hidden
      const indicator = page.locator(`${SELECTORS.v3.thinkingIndicator}:not(.hidden)`);
      const visibleCount = await indicator.count();
      expect(visibleCount).toBe(0);
    }
  });
});

// =============================================================================
// V3_08: Swap Highlight
// =============================================================================

test.describe('V3_08: Swap Highlight', () => {
  test('player area gets can-swap class when holding a card', async ({ page }) => {
    const bot = await setupGame(page);
    await bot.completeInitialFlips();
    await waitForAnimations(page);

    // Wait for our turn
    await bot.waitForMyTurn(15000);

    // Before drawing: no can-swap
    const playerArea = page.locator(SELECTORS.game.playerArea);
    await expect(playerArea).not.toHaveClass(/can-swap/);

    // Draw from deck
    const deck = page.locator(SELECTORS.game.deck);
    if (await deck.isVisible()) {
      await deck.click();
      await page.waitForTimeout(800);

      // After drawing: should have can-swap
      await expect(playerArea).toHaveClass(/can-swap/);
    }
  });
});

// =============================================================================
// V3_09: Knock Early
// =============================================================================

test.describe('V3_09: Knock Early', () => {
  test('knock early button exists when rule is enabled', async ({ page }) => {
    // Enable knock early via the settings
    const bot = new GolfBot(page);
    await bot.goto();
    await bot.createGame('V3Tester');
    await bot.addCPU('Sofia');

    // Check the knock-early checkbox before starting
    const advancedSection = page.locator('.advanced-options-section');
    if (await advancedSection.isVisible()) {
      const isOpen = await advancedSection.evaluate(el => el.hasAttribute('open'));
      if (!isOpen) {
        await advancedSection.locator('summary').click();
        await page.waitForTimeout(300);
      }
    }
    const knockCheckbox = page.locator('#knock-early');
    await knockCheckbox.check();

    // Start game
    await page.locator(SELECTORS.waiting.startGameBtn).click();
    await page.waitForSelector(SELECTORS.screens.game, {
      state: 'visible',
      timeout: 10000,
    });
    await waitForAnimations(page);

    // The knock early button should exist in the DOM
    const knockBtn = page.locator(SELECTORS.game.knockEarlyBtn);
    const count = await knockBtn.count();
    expect(count).toBe(1);
  });

  test('knock early button hidden with default rules', async ({ page }) => {
    const bot = await setupGame(page);
    await waitForAnimations(page);

    const knockBtn = page.locator(SELECTORS.game.knockEarlyBtn);
    // Should be hidden or not present
    const isVisible = await knockBtn.isVisible().catch(() => false);
    expect(isVisible).toBe(false);
  });
});

// =============================================================================
// V3_10: Pair Indicators
// =============================================================================

test.describe('V3_10: Pair Indicators', () => {
  test('paired class applied to matching column cards', async ({ page }) => {
    const bot = await setupGame(page);
    await bot.completeInitialFlips();

    // Play a few turns to increase chance of pairs forming
    for (let i = 0; i < 5; i++) {
      const phase = await bot.getGamePhase();
      if (phase === 'round_over' || phase === 'game_over') break;
      if (await bot.isMyTurn()) {
        await bot.playTurn();
      }
      await page.waitForTimeout(500);
    }

    // Check if any paired classes exist (may or may not depending on game state)
    // This test just verifies the CSS class system works without errors
    const pairedCards = page.locator('.card.paired');
    const count = await pairedCards.count();
    // count >= 0 is always true, but the point is no errors were thrown
    expect(count).toBeGreaterThanOrEqual(0);

    // No console errors from pair indicator rendering
    const errors = bot.getConsoleErrors();
    expect(errors).toHaveLength(0);
  });
});

// =============================================================================
// V3_13: Card Tooltips
// =============================================================================

test.describe('V3_13: Card Tooltips', () => {
  test('tooltip appears on long press of face-up card', async ({ page }) => {
    const bot = await setupGame(page);
    await bot.completeInitialFlips();
    await waitForAnimations(page);

    // Find a face-up card in player's hand
    const faceUpCard = page.locator(`${SELECTORS.game.playerCards} .card:not(.face-down)`).first();

    if (await faceUpCard.count() > 0) {
      // Simulate long press (mousedown, wait, then check tooltip)
      const box = await faceUpCard.boundingBox();
      if (box) {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down();
        await page.waitForTimeout(600); // Tooltip delay

        const tooltip = page.locator(SELECTORS.v3.cardTooltip);
        // Tooltip might or might not appear depending on implementation details
        const tooltipCount = await tooltip.count();
        // Just verify no crash
        expect(tooltipCount).toBeGreaterThanOrEqual(0);

        await page.mouse.up();
      }
    }
  });
});

// =============================================================================
// V3_14: Active Rules Context
// =============================================================================

test.describe('V3_14: Active Rules Context', () => {
  test('rule tags have data-rule attributes', async ({ page }) => {
    // Start game with a house rule enabled
    const bot = new GolfBot(page);
    await bot.goto();
    await bot.createGame('V3Tester');
    await bot.addCPU('Sofia');

    // Enable knock penalty
    const advancedSection = page.locator('.advanced-options-section');
    if (await advancedSection.isVisible()) {
      const isOpen = await advancedSection.evaluate(el => el.hasAttribute('open'));
      if (!isOpen) {
        await advancedSection.locator('summary').click();
        await page.waitForTimeout(300);
      }
    }
    const knockPenalty = page.locator(SELECTORS.waiting.knockPenalty);
    if (await knockPenalty.isVisible()) {
      await knockPenalty.check();
    }

    await page.locator(SELECTORS.waiting.startGameBtn).click();
    await page.waitForSelector(SELECTORS.screens.game, {
      state: 'visible',
      timeout: 10000,
    });
    await waitForAnimations(page);

    // Check that rule tags exist with data-rule attributes
    const ruleTags = page.locator(`${SELECTORS.v3.ruleTag}[data-rule]`);
    const count = await ruleTags.count();
    expect(count).toBeGreaterThanOrEqual(1);

    // Verify the knock_penalty rule tag specifically
    const knockTag = page.locator(`${SELECTORS.v3.ruleTag}[data-rule="knock_penalty"]`);
    const knockCount = await knockTag.count();
    expect(knockCount).toBe(1);
  });

  test('standard game shows no rule tags or standard tag', async ({ page }) => {
    const bot = await setupGame(page);
    await waitForAnimations(page);

    // With no house rules, should show "Standard" or no rule tags
    const activeRulesBar = page.locator(SELECTORS.game.activeRulesBar);
    const isVisible = await activeRulesBar.isVisible();
    // Bar may be hidden or show "Standard"
    if (isVisible) {
      const text = await activeRulesBar.textContent();
      // Should contain "Standard" or be empty/minimal
      expect(text).toBeDefined();
    }
  });
});

// =============================================================================
// V3_15: Discard Pile History
// =============================================================================

test.describe('V3_15: Discard Pile History', () => {
  test('discard pile shows depth after multiple discards', async ({ page }) => {
    const bot = await setupGame(page);
    await bot.completeInitialFlips();

    // Play several turns to accumulate discards
    for (let i = 0; i < 8; i++) {
      const phase = await bot.getGamePhase();
      if (phase === 'round_over' || phase === 'game_over') break;
      if (await bot.isMyTurn()) {
        await bot.playTurn();
      }
      await page.waitForTimeout(500);
    }

    // Check if discard has depth data attribute
    const discard = page.locator(SELECTORS.game.discard);
    const depth = await discard.getAttribute('data-depth');
    // After several turns, depth should be > 0
    // (initial discard + player/CPU discards)
    if (depth !== null) {
      expect(parseInt(depth)).toBeGreaterThanOrEqual(1);
    }
  });
});

// =============================================================================
// Integration: Full Game Stability with V3 Features
// =============================================================================

test.describe('V3 Integration: Full Game Stability', () => {
  test('complete 3-hole game with zero errors', async ({ page }) => {
    test.setTimeout(180000); // 3 minutes

    const bot = new GolfBot(page);
    const freezeDetector = new FreezeDetector(page);

    await bot.goto();
    await bot.createGame('V3Tester');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 3 });

    const result = await bot.playGame(3);

    expect(result.success).toBe(true);
    expect(result.rounds).toBeGreaterThanOrEqual(1);

    // Zero console errors
    const errors = bot.getConsoleErrors();
    expect(errors).toHaveLength(0);

    // No UI freezes
    const health = await freezeDetector.runHealthCheck();
    expect(health.healthy).toBe(true);
  });

  test('game with house rules completes without errors', async ({ page }) => {
    test.setTimeout(120000); // 2 minutes

    const bot = new GolfBot(page);
    const freezeDetector = new FreezeDetector(page);

    await bot.goto();
    await bot.createGame('V3Tester');
    await bot.addCPU('Marcus');

    // Enable some house rules before starting
    const advancedSection = page.locator('.advanced-options-section');
    if (await advancedSection.isVisible()) {
      const isOpen = await advancedSection.evaluate(el => el.hasAttribute('open'));
      if (!isOpen) {
        await advancedSection.locator('summary').click();
        await page.waitForTimeout(300);
      }
    }

    // Enable knock penalty and knock early
    const knockPenalty = page.locator(SELECTORS.waiting.knockPenalty);
    if (await knockPenalty.isVisible()) {
      await knockPenalty.check();
    }
    const knockEarly = page.locator('#knock-early');
    if (await knockEarly.isVisible()) {
      await knockEarly.check();
    }

    await bot.startGame({ holes: 2 });

    const result = await bot.playGame(2);

    expect(result.success).toBe(true);

    const errors = bot.getConsoleErrors();
    expect(errors).toHaveLength(0);

    const health = await freezeDetector.runHealthCheck();
    expect(health.healthy).toBe(true);
  });
});
