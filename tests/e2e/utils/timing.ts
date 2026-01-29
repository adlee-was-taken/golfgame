/**
 * Animation timing constants from animation-queue.js
 * Used to wait for animations to complete before asserting state
 */
export const TIMING = {
  // Core animation durations (from CSS/animation-queue.js)
  flipDuration: 540,
  moveDuration: 270,
  pauseAfterFlip: 144,
  pauseAfterDiscard: 550,
  pauseBeforeNewCard: 150,
  pauseAfterSwapComplete: 400,
  pauseBetweenAnimations: 90,

  // Derived waits for test actions
  get flipComplete() {
    return this.flipDuration + this.pauseAfterFlip + 100;
  },
  get swapComplete() {
    return this.flipDuration + this.pauseAfterFlip + this.moveDuration +
           this.pauseAfterDiscard + this.pauseBeforeNewCard +
           this.moveDuration + this.pauseAfterSwapComplete + 200;
  },
  get drawComplete() {
    return this.moveDuration + this.pauseBeforeNewCard + 100;
  },

  // Safety margins for network/processing
  networkBuffer: 200,
  safetyMargin: 300,

  // Longer waits
  turnTransition: 500,
  cpuThinkingMin: 400,
  cpuThinkingMax: 1200,
  roundOverDelay: 1000,
};

/**
 * Wait for animation queue to drain
 */
export async function waitForAnimations(page: import('@playwright/test').Page, timeout = 5000): Promise<void> {
  await page.waitForFunction(
    () => {
      const game = (window as any).game;
      if (!game?.animationQueue) return true;
      return !game.animationQueue.isAnimating();
    },
    { timeout }
  );
}

/**
 * Wait for WebSocket to be ready
 */
export async function waitForWebSocket(page: import('@playwright/test').Page, timeout = 5000): Promise<void> {
  await page.waitForFunction(
    () => {
      const game = (window as any).game;
      return game?.ws?.readyState === WebSocket.OPEN;
    },
    { timeout }
  );
}

/**
 * Wait a fixed time plus safety margin
 */
export function safeWait(duration: number): number {
  return duration + TIMING.safetyMargin;
}
