/**
 * Full game playthrough tests
 * Tests complete game sessions with the bot
 */

import { test, expect } from '@playwright/test';
import { GolfBot } from '../bot/golf-bot';
import { FreezeDetector } from '../health/freeze-detector';
import { ScreenshotValidator } from '../visual/screenshot-validator';

test.describe('Full Game Playthrough', () => {
  test('bot completes 3-hole game against CPU', async ({ page }) => {
    test.setTimeout(180000); // 3 minutes for 3-hole game

    const bot = new GolfBot(page);
    const freezeDetector = new FreezeDetector(page);
    const validator = new ScreenshotValidator(page);

    // Navigate to game
    await bot.goto();

    // Create game and add CPU
    const roomCode = await bot.createGame('TestBot');
    expect(roomCode).toHaveLength(4);

    await bot.addCPU('Sofia');

    // Take screenshot of waiting room
    await validator.capture('waiting-room');

    // Start game with 3 holes
    await bot.startGame({ holes: 3 });

    // Verify game started
    const phase = await bot.getGamePhase();
    expect(['initial_flip', 'playing']).toContain(phase);

    // Take screenshot of game start
    await validator.capture('game-start', phase);

    // Play through the entire game
    const result = await bot.playGame(3);

    // Take final screenshot
    await validator.capture('game-over', 'game_over');

    // Verify game completed
    expect(result.success).toBe(true);
    expect(result.rounds).toBeGreaterThanOrEqual(1);

    // Check for errors
    const errors = bot.getConsoleErrors();
    expect(errors).toHaveLength(0);

    // Verify no freezes occurred
    const health = await freezeDetector.runHealthCheck();
    expect(health.healthy).toBe(true);
  });

  test('bot completes 9-hole game against CPU', async ({ page }) => {
    test.setTimeout(900000); // 15 minutes for 9-hole game

    const bot = new GolfBot(page);
    const freezeDetector = new FreezeDetector(page);

    await bot.goto();

    const roomCode = await bot.createGame('TestBot');
    await bot.addCPU('Marcus');

    await bot.startGame({ holes: 9 });

    // Play full game
    const result = await bot.playGame(9);

    expect(result.success).toBe(true);
    expect(result.rounds).toBe(9);

    // Verify game ended properly
    const finalPhase = await bot.getGamePhase();
    expect(finalPhase).toBe('game_over');

    // Check health
    const health = await freezeDetector.runHealthCheck();
    expect(health.healthy).toBe(true);
  });

  test('bot handles initial flip phase correctly', async ({ page }) => {
    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1, initialFlips: 2 });

    // Wait for initial flip phase
    await page.waitForTimeout(500);

    // Take screenshot before flips
    await validator.capture('before-initial-flip');

    // Complete initial flips
    await bot.completeInitialFlips();

    // Take screenshot after flips
    await validator.capture('after-initial-flip');

    // Verify 2 cards are face-up
    const state = await bot.getGameState();
    const faceUpCount = state.myPlayer?.cards.filter(c => c.faceUp).length || 0;
    expect(faceUpCount).toBeGreaterThanOrEqual(2);
  });

  test('bot recovers from rapid turn changes', async ({ page }) => {
    test.setTimeout(90000); // 90 seconds

    const bot = new GolfBot(page);

    await bot.goto();
    await bot.createGame('TestBot');

    // Add multiple fast CPUs
    await bot.addCPU('Maya'); // Aggressive
    await bot.addCPU('Sage'); // Sneaky finisher

    await bot.startGame({ holes: 1 });

    // Play with health monitoring
    let frozenCount = 0;
    let turnCount = 0;

    while (await bot.getGamePhase() !== 'round_over' && turnCount < 50) {
      if (await bot.isMyTurn()) {
        const result = await bot.playTurn();
        expect(result.success).toBe(true);
        turnCount++;
      }

      // Check for freeze
      if (await bot.isFrozen(2000)) {
        frozenCount++;
      }

      await page.waitForTimeout(100);
    }

    // Should not have frozen
    expect(frozenCount).toBe(0);
  });

  test('game handles all players finishing', async ({ page }) => {
    test.setTimeout(90000); // 90 seconds for single round

    const bot = new GolfBot(page);
    const validator = new ScreenshotValidator(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    // Play until round over
    const roundResult = await bot.playRound(100);
    expect(roundResult.success).toBe(true);

    // Take screenshot of round end
    await validator.capture('round-end');

    // Verify all player cards are revealed
    const state = await bot.getGameState();
    const allRevealed = state.myPlayer?.cards.every(c => c.faceUp) ?? false;
    expect(allRevealed).toBe(true);

    // Verify scoreboard is visible
    const scoreboardVisible = await validator.expectVisible('#game-buttons');
    expect(scoreboardVisible.passed).toBe(true);
  });
});

test.describe('Game Settings', () => {
  test('Speed Golf mode (flip on discard)', async ({ page }) => {
    test.setTimeout(90000); // 90 seconds

    const bot = new GolfBot(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');

    // Start with Speed Golf (always flip)
    await bot.startGame({
      holes: 1,
      flipMode: 'always',
    });

    // Play through
    const result = await bot.playRound(50);
    expect(result.success).toBe(true);

    // No errors should occur
    expect(bot.getConsoleErrors()).toHaveLength(0);
  });

  test('Endgame mode (optional flip)', async ({ page }) => {
    test.setTimeout(90000); // 90 seconds

    const bot = new GolfBot(page);

    await bot.goto();
    await bot.createGame('TestBot');
    await bot.addCPU('Sofia');

    // Start with Endgame mode
    await bot.startGame({
      holes: 1,
      flipMode: 'endgame',
    });

    // Play through
    const result = await bot.playRound(50);
    expect(result.success).toBe(true);

    expect(bot.getConsoleErrors()).toHaveLength(0);
  });

  test('Multiple decks with many players', async ({ page }) => {
    test.setTimeout(90000);

    const bot = new GolfBot(page);

    await bot.goto();
    await bot.createGame('TestBot');

    // Add 4 CPUs (5 total players)
    await bot.addCPU('Sofia');
    await bot.addCPU('Marcus');
    await bot.addCPU('Maya');
    await bot.addCPU('Kenji');

    // Start with 2 decks
    await bot.startGame({
      holes: 1,
      decks: 2,
    });

    // Play through
    const result = await bot.playRound(100);
    expect(result.success).toBe(true);

    expect(bot.getConsoleErrors()).toHaveLength(0);
  });
});
