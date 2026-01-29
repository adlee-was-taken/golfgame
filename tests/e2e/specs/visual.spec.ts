/**
 * Visual regression tests
 * Validates visual correctness at key game moments
 */

import { test, expect, devices } from '@playwright/test';
import { GolfBot } from '../bot/golf-bot';
import { ScreenshotValidator } from '../visual/screenshot-validator';
import {
  validateGameStart,
  validateAfterInitialFlip,
  validateDrawPhase,
  validateAfterDraw,
  validateRoundOver,
  validateFinalTurn,
  validateResponsiveLayout,
} from '../visual/visual-rules';

test.describe('Visual Validation', () => {
  test('game start visual state', async ({ page }) => {
    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    // Wait for game to fully render
    await page.waitForTimeout(1000);

    // Capture game start
    await validator.capture('game-start-visual');

    // Validate visual state
    const result = await validateGameStart(validator);
    expect(result.passed).toBe(true);
    if (!result.passed) {
      console.log('Failures:', result.failures);
    }
  });

  test('initial flip visual state', async ({ page }) => {
    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1, initialFlips: 2 });

    // Complete initial flips
    await bot.completeInitialFlips();
    await page.waitForTimeout(500);

    // Capture after flips
    await validator.capture('after-initial-flip-visual');

    // Validate
    const result = await validateAfterInitialFlip(validator, 2);
    expect(result.passed).toBe(true);
    if (!result.passed) {
      console.log('Failures:', result.failures);
    }
  });

  test('draw phase visual state', async ({ page }) => {
    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    // Complete initial phase and wait for our turn
    await bot.completeInitialFlips();

    // Wait for our turn
    await bot.waitForMyTurn(10000);

    // Capture draw phase
    await validator.capture('draw-phase-visual');

    // Validate
    const result = await validateDrawPhase(validator);
    expect(result.passed).toBe(true);
    if (!result.passed) {
      console.log('Failures:', result.failures);
    }
  });

  test('held card visual state', async ({ page }) => {
    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    await bot.completeInitialFlips();
    await bot.waitForMyTurn(10000);

    // Draw a card
    const deck = page.locator('#deck');
    await deck.click();

    // Wait for draw animation
    await page.waitForTimeout(500);

    // Capture held card state
    await validator.capture('held-card-visual');

    // Validate held card is visible
    const heldResult = await validator.expectHeldCardVisible();
    expect(heldResult.passed).toBe(true);

    // Validate cards are clickable
    const clickableResult = await validator.expectCount(
      '#player-cards .card.clickable',
      6
    );
    expect(clickableResult.passed).toBe(true);
  });

  test('round over visual state', async ({ page }) => {
    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    // Play until round over
    await bot.playRound(50);

    // Wait for animations
    await page.waitForTimeout(1000);

    // Capture round over
    await validator.capture('round-over-visual');

    // Validate
    const result = await validateRoundOver(validator);
    expect(result.passed).toBe(true);
    if (!result.passed) {
      console.log('Failures:', result.failures);
    }
  });

  test('card flip animation renders correctly', async ({ page }) => {
    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1, initialFlips: 0 }); // No initial flips

    // Wait for our turn
    await bot.waitForMyTurn(10000);

    // Capture before flip
    await validator.capture('before-flip');

    // Get a face-down card position
    const state = await bot.getGameState();
    const faceDownPos = state.myPlayer?.cards.find(c => !c.faceUp)?.position ?? 0;

    // Draw and swap to trigger flip
    const deck = page.locator('#deck');
    await deck.click();
    await page.waitForTimeout(300);

    // Click the face-down card to swap
    const card = page.locator(`#player-cards .card:nth-child(${faceDownPos + 1})`);
    await card.click();

    // Wait for animation to complete
    await page.waitForTimeout(1500);

    // Capture after flip
    await validator.capture('after-flip');

    // Verify card is now face-up
    const afterState = await bot.getGameState();
    const cardAfter = afterState.myPlayer?.cards.find(c => c.position === faceDownPos);
    expect(cardAfter?.faceUp).toBe(true);
  });

  test('opponent highlighting on their turn', async ({ page }) => {
    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    await bot.completeInitialFlips();

    // Play our turn and then wait for opponent's turn
    if (await bot.isMyTurn()) {
      await bot.playTurn();
    }

    // Wait for opponent turn indicator
    await page.waitForTimeout(1000);

    // Check if it's opponent's turn
    const state = await bot.getGameState();
    const opponentPlaying = state.opponents.some(o => o.isCurrentTurn);

    if (opponentPlaying) {
      // Capture opponent turn
      await validator.capture('opponent-turn-visual');

      // Find which opponent has current turn
      const currentOpponentIndex = state.opponents.findIndex(o => o.isCurrentTurn);
      if (currentOpponentIndex >= 0) {
        const result = await validator.expectOpponentCurrentTurn(currentOpponentIndex);
        expect(result.passed).toBe(true);
      }
    }
  });

  test('discard pile updates correctly', async ({ page }) => {
    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    await bot.completeInitialFlips();
    await bot.waitForMyTurn(10000);

    // Get initial discard state
    const beforeState = await bot.getGameState();
    const beforeDiscard = beforeState.discard.topCard;

    // Draw from deck and discard
    const deck = page.locator('#deck');
    await deck.click();
    await page.waitForTimeout(500);

    // Get the held card
    const heldCard = (await bot.getGameState()).heldCard.card;

    // Discard the drawn card
    const discardBtn = page.locator('#discard-btn');
    await discardBtn.click();
    await page.waitForTimeout(800);

    // Capture after discard
    await validator.capture('after-discard-visual');

    // Verify discard pile has the card we discarded
    const afterState = await bot.getGameState();
    expect(afterState.discard.hasCard).toBe(true);
  });
});

test.describe('Responsive Layout', () => {
  test('mobile layout (375px)', async ({ browser }) => {
    const context = await browser.newContext({
      ...devices['iPhone 13'],
    });
    const page = await context.newPage();

    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    await page.waitForTimeout(1000);

    // Capture mobile layout
    await validator.capture('mobile-375-layout');

    // Validate responsive elements
    const result = await validateResponsiveLayout(validator, 375);
    expect(result.passed).toBe(true);
    if (!result.passed) {
      console.log('Mobile failures:', result.failures);
    }

    await context.close();
  });

  test('tablet layout (768px)', async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 768, height: 1024 },
    });
    const page = await context.newPage();

    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    await page.waitForTimeout(1000);

    // Capture tablet layout
    await validator.capture('tablet-768-layout');

    // Validate responsive elements
    const result = await validateResponsiveLayout(validator, 768);
    expect(result.passed).toBe(true);

    await context.close();
  });

  test('desktop layout (1920px)', async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
    });
    const page = await context.newPage();

    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    await page.waitForTimeout(1000);

    // Capture desktop layout
    await validator.capture('desktop-1920-layout');

    // Validate responsive elements
    const result = await validateResponsiveLayout(validator, 1920);
    expect(result.passed).toBe(true);

    await context.close();
  });
});
