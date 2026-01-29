/**
 * Stress tests
 * Tests for race conditions, memory leaks, and edge cases
 */

import { test, expect } from '@playwright/test';
import { GolfBot } from '../bot/golf-bot';
import { FreezeDetector } from '../health/freeze-detector';
import { AnimationTracker } from '../health/animation-tracker';

test.describe('Stress Tests', () => {
  test('rapid action sequence (race condition detection)', async ({ page }) => {
    const bot = new GolfBot(page);
    const freezeDetector = new FreezeDetector(page);

    await bot.goto();
    await bot.createGame('StressBot');
    await bot.addCPU('Maya'); // Aggressive, fast player
    await bot.startGame({ holes: 1 });

    await bot.completeInitialFlips();

    let actionCount = 0;
    let errorCount = 0;

    // Rapid turns with minimal delays
    while (await bot.getGamePhase() !== 'round_over' && actionCount < 100) {
      if (await bot.isMyTurn()) {
        // Reduce normal waits
        const state = await bot.getGameState();

        if (!state.heldCard.visible) {
          // Quick draw
          const deck = page.locator('#deck');
          await deck.click({ timeout: 1000 }).catch(() => { errorCount++; });
          await page.waitForTimeout(100);
        } else {
          // Quick swap or discard
          const faceDown = state.myPlayer?.cards.find(c => !c.faceUp);
          if (faceDown) {
            const card = page.locator(`#player-cards .card:nth-child(${faceDown.position + 1})`);
            await card.click({ timeout: 1000 }).catch(() => { errorCount++; });
          } else {
            const discardBtn = page.locator('#discard-btn');
            await discardBtn.click({ timeout: 1000 }).catch(() => { errorCount++; });
          }
          await page.waitForTimeout(100);
        }

        actionCount++;
      } else {
        await page.waitForTimeout(50);
      }

      // Check for freezes
      if (await bot.isFrozen(2000)) {
        console.warn(`Freeze detected at action ${actionCount}`);
        break;
      }
    }

    // Verify no critical errors
    const health = await freezeDetector.runHealthCheck();
    expect(health.issues.filter(i => i.type === 'websocket_closed')).toHaveLength(0);

    // Some click errors are acceptable (timing issues), but not too many
    expect(errorCount).toBeLessThan(10);

    console.log(`Completed ${actionCount} rapid actions with ${errorCount} minor errors`);
  });

  test('multiple games in succession (memory leak detection)', async ({ page }) => {
    test.setTimeout(300000); // 5 minutes

    const bot = new GolfBot(page);
    const gamesCompleted: number[] = [];

    // Get initial memory if available
    const getMemory = async () => {
      try {
        return await page.evaluate(() => {
          if ('memory' in performance) {
            return (performance as any).memory.usedJSHeapSize;
          }
          return null;
        });
      } catch {
        return null;
      }
    };

    const initialMemory = await getMemory();
    console.log(`Initial memory: ${initialMemory ? Math.round(initialMemory / 1024 / 1024) + 'MB' : 'N/A'}`);

    // Play 10 quick games
    for (let game = 0; game < 10; game++) {
      await bot.goto();
      await bot.createGame(`MemBot${game}`);
      await bot.addCPU('Sofia');
      await bot.startGame({ holes: 1 });

      const result = await bot.playRound(50);

      if (result.success) {
        gamesCompleted.push(game);
      }

      // Check memory every few games
      if (game % 3 === 2) {
        const currentMemory = await getMemory();
        if (currentMemory) {
          console.log(`Game ${game + 1}: memory = ${Math.round(currentMemory / 1024 / 1024)}MB`);
        }
      }

      // Clear any accumulated errors
      bot.clearConsoleErrors();
    }

    // Should complete most games
    expect(gamesCompleted.length).toBeGreaterThanOrEqual(8);

    // Final memory check
    const finalMemory = await getMemory();
    if (initialMemory && finalMemory) {
      const memoryGrowth = finalMemory - initialMemory;
      console.log(`Memory growth: ${Math.round(memoryGrowth / 1024 / 1024)}MB`);

      // Memory shouldn't grow excessively (allow 50MB growth for 10 games)
      expect(memoryGrowth).toBeLessThan(50 * 1024 * 1024);
    }
  });

  test('6-player game with 5 CPUs (max players)', async ({ page }) => {
    test.setTimeout(180000); // 3 minutes

    const bot = new GolfBot(page);
    const freezeDetector = new FreezeDetector(page);

    await bot.goto();
    await bot.createGame('TestBot');

    // Add 5 CPU players (max typical setup)
    await bot.addCPU('Sofia');
    await bot.addCPU('Maya');
    await bot.addCPU('Priya');
    await bot.addCPU('Marcus');
    await bot.addCPU('Kenji');

    // Start with 2 decks (recommended for 6 players)
    await bot.startGame({
      holes: 3,
      decks: 2,
    });

    // Play through all rounds
    const result = await bot.playGame(3);

    expect(result.success).toBe(true);
    expect(result.rounds).toBe(3);

    // Check for issues
    const health = await freezeDetector.runHealthCheck();
    expect(health.healthy).toBe(true);

    console.log(`6-player game completed in ${result.totalTurns} turns`);
  });

  test('animation queue under load', async ({ page }) => {
    const bot = new GolfBot(page);
    const animTracker = new AnimationTracker(page);

    await bot.goto();
    await bot.createGame('AnimBot');
    await bot.addCPU('Maya'); // Fast player
    await bot.addCPU('Sage'); // Sneaky finisher
    await bot.startGame({ holes: 1 });

    await bot.completeInitialFlips();

    let animationCount = 0;
    let stallCount = 0;

    while (await bot.getGamePhase() !== 'round_over' && animationCount < 50) {
      if (await bot.isMyTurn()) {
        // Track animation timing
        animTracker.recordStart('turn');

        await bot.playTurn();

        const result = await animTracker.waitForAnimation('turn', 5000);
        if (!result.completed) {
          stallCount++;
        }

        animationCount++;
      }

      await page.waitForTimeout(100);
    }

    // Check animation timing is reasonable
    const avgDuration = animTracker.getAverageDuration('turn');
    console.log(`Average turn animation: ${avgDuration?.toFixed(0) || 'N/A'}ms`);

    // Stalls should be rare
    expect(stallCount).toBeLessThan(3);

    // Check stall events
    const stalls = animTracker.getStalls();
    if (stalls.length > 0) {
      console.log(`Animation stalls:`, stalls);
    }
  });

  test('websocket reconnection handling', async ({ page }) => {
    const bot = new GolfBot(page);
    const freezeDetector = new FreezeDetector(page);

    await bot.goto();
    await bot.createGame('ReconnectBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    await bot.completeInitialFlips();

    // Play a few turns
    for (let i = 0; i < 3; i++) {
      await bot.waitForMyTurn(10000);
      if (await bot.isMyTurn()) {
        await bot.playTurn();
      }
    }

    // Check WebSocket is healthy
    const wsHealthy = await freezeDetector.checkWebSocket();
    expect(wsHealthy).toBe(true);

    // Note: Actually closing/reopening websocket would require
    // server cooperation or network manipulation
  });

  test('concurrent clicks during animation', async ({ page }) => {
    const bot = new GolfBot(page);

    await bot.goto();
    await bot.createGame('ClickBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    await bot.completeInitialFlips();
    await bot.waitForMyTurn(10000);

    // Draw a card
    const deck = page.locator('#deck');
    await deck.click();
    await page.waitForTimeout(200);

    // Try rapid clicks on multiple elements while animation might be running
    const clickPromises: Promise<void>[] = [];

    for (let i = 0; i < 6; i++) {
      const card = page.locator(`#player-cards .card:nth-child(${i + 1})`);
      clickPromises.push(
        card.click({ timeout: 500 }).catch(() => {})
      );
    }

    // Wait for all clicks to complete or timeout
    await Promise.all(clickPromises);

    // Wait for any animations
    await page.waitForTimeout(2000);

    // Game should still be in a valid state
    const phase = await bot.getGamePhase();
    expect(['playing', 'waiting_for_flip', 'round_over']).toContain(phase);

    // No console errors
    const errors = bot.getConsoleErrors();
    expect(errors.filter(e => e.includes('undefined') || e.includes('null'))).toHaveLength(0);
  });
});

test.describe('Edge Cases', () => {
  test('all cards revealed simultaneously', async ({ page }) => {
    const bot = new GolfBot(page);

    await bot.goto();
    await bot.createGame('EdgeBot');
    await bot.addCPU('Sofia');

    // Start with Speed Golf (flip on discard) to reveal cards faster
    await bot.startGame({
      holes: 1,
      flipMode: 'always',
      initialFlips: 2,
    });

    // Play until we trigger round end
    const result = await bot.playRound(100);
    expect(result.success).toBe(true);

    // Verify game handled the transition
    const phase = await bot.getGamePhase();
    expect(phase).toBe('round_over');
  });

  test('deck reshuffle scenario', async ({ page }) => {
    test.setTimeout(180000); // 3 minutes for longer game

    const bot = new GolfBot(page);

    await bot.goto();
    await bot.createGame('ShuffleBot');

    // Add many players to deplete deck faster
    await bot.addCPU('Sofia');
    await bot.addCPU('Maya');
    await bot.addCPU('Marcus');
    await bot.addCPU('Kenji');

    // Use only 1 deck to force reshuffle
    await bot.startGame({
      holes: 1,
      decks: 1,
    });

    // Play through - deck should reshuffle during game
    const result = await bot.playRound(200);
    expect(result.success).toBe(true);
  });

  test('empty discard pile handling', async ({ page }) => {
    const bot = new GolfBot(page);

    await bot.goto();
    await bot.createGame('EmptyBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    // At game start, discard might be empty briefly
    const initialState = await bot.getGameState();

    // Game should still function
    await bot.completeInitialFlips();
    await bot.waitForMyTurn(10000);

    // Should be able to draw from deck even if discard is empty
    if (await bot.isMyTurn()) {
      const state = await bot.getGameState();
      if (!state.discard.hasCard) {
        // Draw from deck should work
        const deck = page.locator('#deck');
        await deck.click();
        await page.waitForTimeout(500);

        // Should have a held card now
        const afterState = await bot.getGameState();
        expect(afterState.heldCard.visible).toBe(true);
      }
    }
  });

  test('final turn badge timing', async ({ page }) => {
    const bot = new GolfBot(page);

    await bot.goto();
    await bot.createGame('BadgeBot');
    await bot.addCPU('Sofia');
    await bot.startGame({ holes: 1 });

    // Monitor for final turn badge
    let sawFinalTurnBadge = false;
    let turnsAfterBadge = 0;

    while (await bot.getGamePhase() !== 'round_over') {
      const state = await bot.getGameState();

      if (state.isFinalTurn) {
        sawFinalTurnBadge = true;
      }

      if (sawFinalTurnBadge && await bot.isMyTurn()) {
        turnsAfterBadge++;
      }

      if (await bot.isMyTurn()) {
        await bot.playTurn();
      }

      await page.waitForTimeout(100);
    }

    // If final turn happened, we should have had at most 1 turn after badge appeared
    // (this depends on whether we're the one who triggered final turn)
    if (sawFinalTurnBadge) {
      expect(turnsAfterBadge).toBeLessThanOrEqual(2);
    }
  });
});
