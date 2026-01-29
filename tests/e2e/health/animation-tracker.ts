/**
 * Animation tracker - monitors animation completion and timing
 */

import { Page } from '@playwright/test';
import { TIMING } from '../utils/timing';

/**
 * Animation event
 */
export interface AnimationEvent {
  type: 'start' | 'complete' | 'stall';
  animationType?: string;
  duration?: number;
  timestamp: number;
}

/**
 * AnimationTracker - tracks animation states
 */
export class AnimationTracker {
  private events: AnimationEvent[] = [];
  private animationStartTime: number | null = null;

  constructor(private page: Page) {}

  /**
   * Record animation start
   */
  recordStart(type?: string): void {
    this.animationStartTime = Date.now();
    this.events.push({
      type: 'start',
      animationType: type,
      timestamp: this.animationStartTime,
    });
  }

  /**
   * Record animation complete
   */
  recordComplete(type?: string): void {
    const now = Date.now();
    const duration = this.animationStartTime
      ? now - this.animationStartTime
      : undefined;

    this.events.push({
      type: 'complete',
      animationType: type,
      duration,
      timestamp: now,
    });

    this.animationStartTime = null;
  }

  /**
   * Record animation stall
   */
  recordStall(type?: string): void {
    const now = Date.now();
    const duration = this.animationStartTime
      ? now - this.animationStartTime
      : undefined;

    this.events.push({
      type: 'stall',
      animationType: type,
      duration,
      timestamp: now,
    });
  }

  /**
   * Check if animation queue is animating
   */
  async isAnimating(): Promise<boolean> {
    try {
      return await this.page.evaluate(() => {
        const game = (window as any).game;
        return game?.animationQueue?.isAnimating() ?? false;
      });
    } catch {
      return false;
    }
  }

  /**
   * Get animation queue length
   */
  async getQueueLength(): Promise<number> {
    try {
      return await this.page.evaluate(() => {
        const game = (window as any).game;
        return game?.animationQueue?.queue?.length ?? 0;
      });
    } catch {
      return 0;
    }
  }

  /**
   * Wait for animation to complete with tracking
   */
  async waitForAnimation(
    type: string,
    timeoutMs: number = 5000
  ): Promise<{ completed: boolean; duration: number }> {
    this.recordStart(type);
    const startTime = Date.now();

    try {
      await this.page.waitForFunction(
        () => {
          const game = (window as any).game;
          if (!game?.animationQueue) return true;
          return !game.animationQueue.isAnimating();
        },
        { timeout: timeoutMs }
      );

      const duration = Date.now() - startTime;
      this.recordComplete(type);
      return { completed: true, duration };
    } catch {
      const duration = Date.now() - startTime;
      this.recordStall(type);
      return { completed: false, duration };
    }
  }

  /**
   * Wait for specific animation type by watching DOM changes
   */
  async waitForFlipAnimation(timeoutMs: number = 2000): Promise<boolean> {
    return this.waitForAnimationClass('flipping', timeoutMs);
  }

  async waitForSwapAnimation(timeoutMs: number = 3000): Promise<boolean> {
    return this.waitForAnimationClass('swap-animation', timeoutMs);
  }

  /**
   * Wait for animation class to appear and disappear
   */
  private async waitForAnimationClass(
    className: string,
    timeoutMs: number
  ): Promise<boolean> {
    try {
      // Wait for class to appear
      await this.page.waitForSelector(`.${className}`, {
        state: 'attached',
        timeout: timeoutMs / 2,
      });

      // Wait for class to disappear (animation complete)
      await this.page.waitForSelector(`.${className}`, {
        state: 'detached',
        timeout: timeoutMs / 2,
      });

      return true;
    } catch {
      return false;
    }
  }

  /**
   * Get animation events
   */
  getEvents(): AnimationEvent[] {
    return [...this.events];
  }

  /**
   * Get stall events
   */
  getStalls(): AnimationEvent[] {
    return this.events.filter(e => e.type === 'stall');
  }

  /**
   * Get average animation duration by type
   */
  getAverageDuration(type?: string): number | null {
    const completed = this.events.filter(e =>
      e.type === 'complete' &&
      e.duration !== undefined &&
      (!type || e.animationType === type)
    );

    if (completed.length === 0) return null;

    const total = completed.reduce((sum, e) => sum + (e.duration || 0), 0);
    return total / completed.length;
  }

  /**
   * Check if animations are within expected timing
   */
  validateTiming(
    type: string,
    expectedMs: number,
    tolerancePercent: number = 50
  ): { valid: boolean; actual: number | null } {
    const avgDuration = this.getAverageDuration(type);

    if (avgDuration === null) {
      return { valid: true, actual: null };
    }

    const tolerance = expectedMs * (tolerancePercent / 100);
    const minOk = expectedMs - tolerance;
    const maxOk = expectedMs + tolerance;

    return {
      valid: avgDuration >= minOk && avgDuration <= maxOk,
      actual: avgDuration,
    };
  }

  /**
   * Clear tracked events
   */
  clear(): void {
    this.events = [];
    this.animationStartTime = null;
  }
}
