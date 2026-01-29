/**
 * Freeze detector - monitors for UI responsiveness issues
 */

import { Page } from '@playwright/test';
import { SELECTORS } from '../utils/selectors';
import { TIMING } from '../utils/timing';

/**
 * Health check result
 */
export interface HealthCheck {
  healthy: boolean;
  issues: HealthIssue[];
}

export interface HealthIssue {
  type: 'animation_stall' | 'websocket_closed' | 'console_error' | 'unresponsive';
  message: string;
  timestamp: number;
}

/**
 * FreezeDetector - monitors UI health
 */
export class FreezeDetector {
  private issues: HealthIssue[] = [];
  private consoleErrors: string[] = [];
  private wsState: number | null = null;

  constructor(private page: Page) {
    // Monitor console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const text = msg.text();
        this.consoleErrors.push(text);
        this.addIssue('console_error', text);
      }
    });

    page.on('pageerror', err => {
      this.consoleErrors.push(err.message);
      this.addIssue('console_error', err.message);
    });
  }

  /**
   * Add a health issue
   */
  private addIssue(type: HealthIssue['type'], message: string): void {
    this.issues.push({
      type,
      message,
      timestamp: Date.now(),
    });
  }

  /**
   * Clear recorded issues
   */
  clearIssues(): void {
    this.issues = [];
    this.consoleErrors = [];
  }

  /**
   * Get all recorded issues
   */
  getIssues(): HealthIssue[] {
    return [...this.issues];
  }

  /**
   * Get recent issues (within timeframe)
   */
  getRecentIssues(withinMs: number = 10000): HealthIssue[] {
    const cutoff = Date.now() - withinMs;
    return this.issues.filter(i => i.timestamp > cutoff);
  }

  /**
   * Check for animation stall
   */
  async checkAnimationStall(timeoutMs: number = 5000): Promise<boolean> {
    try {
      await this.page.waitForFunction(
        () => {
          const game = (window as any).game;
          if (!game?.animationQueue) return true;
          return !game.animationQueue.isAnimating();
        },
        { timeout: timeoutMs }
      );
      return false; // No stall
    } catch {
      this.addIssue('animation_stall', `Animation did not complete within ${timeoutMs}ms`);
      return true; // Stalled
    }
  }

  /**
   * Check WebSocket health
   */
  async checkWebSocket(): Promise<boolean> {
    try {
      const state = await this.page.evaluate(() => {
        const game = (window as any).game;
        return game?.ws?.readyState;
      });

      this.wsState = state;

      // WebSocket.OPEN = 1
      if (state !== 1) {
        const stateNames: Record<number, string> = {
          0: 'CONNECTING',
          1: 'OPEN',
          2: 'CLOSING',
          3: 'CLOSED',
        };
        this.addIssue('websocket_closed', `WebSocket is ${stateNames[state] || 'UNKNOWN'}`);
        return false;
      }

      return true;
    } catch (error) {
      this.addIssue('websocket_closed', `Failed to check WebSocket: ${error}`);
      return false;
    }
  }

  /**
   * Check if element is responsive to clicks
   */
  async checkClickResponsiveness(
    selector: string,
    timeoutMs: number = 2000
  ): Promise<boolean> {
    try {
      const el = this.page.locator(selector);
      if (!await el.isVisible()) {
        return true; // Element not visible is not necessarily an issue
      }

      // Check if element is clickable
      await el.click({ timeout: timeoutMs, trial: true });
      return true;
    } catch {
      this.addIssue('unresponsive', `Element ${selector} not responsive`);
      return false;
    }
  }

  /**
   * Run full health check
   */
  async runHealthCheck(): Promise<HealthCheck> {
    const animationOk = !(await this.checkAnimationStall());
    const wsOk = await this.checkWebSocket();

    const healthy = animationOk && wsOk && this.consoleErrors.length === 0;

    return {
      healthy,
      issues: this.getRecentIssues(),
    };
  }

  /**
   * Monitor game loop for issues
   * Returns when an issue is detected or timeout
   */
  async monitorUntilIssue(
    timeoutMs: number = 60000,
    checkIntervalMs: number = 500
  ): Promise<HealthIssue | null> {
    const startTime = Date.now();

    while (Date.now() - startTime < timeoutMs) {
      // Check animation
      const animStall = await this.checkAnimationStall(3000);
      if (animStall) {
        return this.issues[this.issues.length - 1];
      }

      // Check WebSocket
      const wsOk = await this.checkWebSocket();
      if (!wsOk) {
        return this.issues[this.issues.length - 1];
      }

      // Check for new console errors
      if (this.consoleErrors.length > 0) {
        return this.issues[this.issues.length - 1];
      }

      await this.page.waitForTimeout(checkIntervalMs);
    }

    return null;
  }

  /**
   * Get console errors
   */
  getConsoleErrors(): string[] {
    return [...this.consoleErrors];
  }
}
