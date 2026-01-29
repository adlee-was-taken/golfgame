/**
 * GolfBot - Main orchestrator for the test bot
 * Controls browser and coordinates game actions
 */

import { Page, expect } from '@playwright/test';
import { StateParser, GamePhase, ParsedGameState } from './state-parser';
import { AIBrain, GameOptions } from './ai-brain';
import { Actions, ActionResult } from './actions';
import { SELECTORS } from '../utils/selectors';
import { TIMING, waitForAnimations } from '../utils/timing';

/**
 * Options for starting a game
 */
export interface StartGameOptions {
  holes?: number;
  decks?: number;
  initialFlips?: number;
  flipMode?: 'never' | 'always' | 'endgame';
  knockPenalty?: boolean;
  jokerMode?: 'none' | 'standard' | 'lucky-swing' | 'eagle-eye';
}

/**
 * Result of a turn
 */
export interface TurnResult {
  success: boolean;
  action: string;
  details?: Record<string, unknown>;
  error?: string;
}

/**
 * GolfBot - automated game player for testing
 */
export class GolfBot {
  private stateParser: StateParser;
  private actions: Actions;
  private brain: AIBrain;
  private screenshots: { label: string; buffer: Buffer }[] = [];
  private consoleErrors: string[] = [];
  private turnCount = 0;

  constructor(
    private page: Page,
    aiOptions: GameOptions = {}
  ) {
    this.stateParser = new StateParser(page);
    this.actions = new Actions(page);
    this.brain = new AIBrain(aiOptions);

    // Capture console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        this.consoleErrors.push(msg.text());
      }
    });

    page.on('pageerror', err => {
      this.consoleErrors.push(err.message);
    });
  }

  /**
   * Navigate to the game
   */
  async goto(url?: string): Promise<void> {
    await this.page.goto(url || '/');
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Create a new game room
   */
  async createGame(playerName: string): Promise<string> {
    // Enter name
    const nameInput = this.page.locator(SELECTORS.lobby.playerNameInput);
    await nameInput.fill(playerName);

    // Click create room
    const createBtn = this.page.locator(SELECTORS.lobby.createRoomBtn);
    await createBtn.click();

    // Wait for waiting room
    await this.page.waitForSelector(SELECTORS.screens.waiting, {
      state: 'visible',
      timeout: 10000,
    });

    // Get room code
    const roomCodeEl = this.page.locator(SELECTORS.waiting.roomCode);
    const roomCode = await roomCodeEl.textContent() || '';

    return roomCode.trim();
  }

  /**
   * Join an existing game room
   */
  async joinGame(roomCode: string, playerName: string): Promise<void> {
    // Enter name
    const nameInput = this.page.locator(SELECTORS.lobby.playerNameInput);
    await nameInput.fill(playerName);

    // Enter room code
    const codeInput = this.page.locator(SELECTORS.lobby.roomCodeInput);
    await codeInput.fill(roomCode);

    // Click join
    const joinBtn = this.page.locator(SELECTORS.lobby.joinRoomBtn);
    await joinBtn.click();

    // Wait for waiting room
    await this.page.waitForSelector(SELECTORS.screens.waiting, {
      state: 'visible',
      timeout: 10000,
    });
  }

  /**
   * Add a CPU player
   */
  async addCPU(profileName?: string): Promise<void> {
    // Click add CPU button
    const addBtn = this.page.locator(SELECTORS.waiting.addCpuBtn);
    await addBtn.click();

    // Wait for modal
    await this.page.waitForSelector(SELECTORS.waiting.cpuModal, {
      state: 'visible',
      timeout: 5000,
    });

    // Select profile if specified
    if (profileName) {
      const profileCard = this.page.locator(
        `${SELECTORS.waiting.cpuProfilesGrid} .profile-card:has-text("${profileName}")`
      );
      await profileCard.click();
    } else {
      // Select first available profile
      const firstProfile = this.page.locator(
        `${SELECTORS.waiting.cpuProfilesGrid} .profile-card:not(.unavailable)`
      ).first();
      await firstProfile.click();
    }

    // Click add button
    const addSelectedBtn = this.page.locator(SELECTORS.waiting.addSelectedCpusBtn);
    await addSelectedBtn.click();

    // Wait for modal to close
    await this.page.waitForSelector(SELECTORS.waiting.cpuModal, {
      state: 'hidden',
      timeout: 5000,
    });

    await this.page.waitForTimeout(500);
  }

  /**
   * Start the game
   */
  async startGame(options: StartGameOptions = {}): Promise<void> {
    // Set game options if host
    const hostSettings = this.page.locator(SELECTORS.waiting.hostSettings);

    if (await hostSettings.isVisible()) {
      if (options.holes) {
        await this.page.selectOption(SELECTORS.waiting.numRounds, String(options.holes));
      }
      if (options.decks) {
        await this.page.selectOption(SELECTORS.waiting.numDecks, String(options.decks));
      }
      if (options.initialFlips !== undefined) {
        await this.page.selectOption(SELECTORS.waiting.initialFlips, String(options.initialFlips));
      }

      // Advanced options require opening the details section first
      if (options.flipMode) {
        const advancedSection = this.page.locator('.advanced-options-section');
        if (await advancedSection.isVisible()) {
          // Check if it's already open
          const isOpen = await advancedSection.evaluate(el => el.hasAttribute('open'));
          if (!isOpen) {
            await advancedSection.locator('summary').click();
            await this.page.waitForTimeout(300);
          }
        }
        await this.page.selectOption(SELECTORS.waiting.flipMode, options.flipMode);
      }
    }

    // Click start game
    const startBtn = this.page.locator(SELECTORS.waiting.startGameBtn);
    await startBtn.click();

    // Wait for game screen
    await this.page.waitForSelector(SELECTORS.screens.game, {
      state: 'visible',
      timeout: 10000,
    });

    await waitForAnimations(this.page);
  }

  /**
   * Get current game phase
   */
  async getGamePhase(): Promise<GamePhase> {
    return this.stateParser.getPhase();
  }

  /**
   * Get full game state
   */
  async getGameState(): Promise<ParsedGameState> {
    return this.stateParser.getState();
  }

  /**
   * Check if it's bot's turn
   */
  async isMyTurn(): Promise<boolean> {
    return this.stateParser.isMyTurn();
  }

  /**
   * Wait for bot's turn
   */
  async waitForMyTurn(timeout: number = 30000): Promise<boolean> {
    return this.actions.waitForMyTurn(timeout);
  }

  /**
   * Wait for any animation to complete
   */
  async waitForAnimation(): Promise<void> {
    await waitForAnimations(this.page);
  }

  /**
   * Play a complete turn
   */
  async playTurn(): Promise<TurnResult> {
    this.turnCount++;
    const state = await this.getGameState();

    // Handle initial flip phase
    if (state.phase === 'initial_flip') {
      return this.handleInitialFlip(state);
    }

    // Handle waiting for flip after discard
    if (state.phase === 'waiting_for_flip') {
      return this.handleWaitingForFlip(state);
    }

    // Regular turn
    if (!state.heldCard.visible) {
      // Need to draw
      return this.handleDraw(state);
    } else {
      // Have a card, need to swap or discard
      return this.handleSwapOrDiscard(state);
    }
  }

  /**
   * Handle initial flip phase
   */
  private async handleInitialFlip(state: ParsedGameState): Promise<TurnResult> {
    const myCards = state.myPlayer?.cards || [];
    const faceDownPositions = myCards.filter(c => !c.faceUp).map(c => c.position);

    if (faceDownPositions.length === 0) {
      return { success: true, action: 'initial_flip_complete' };
    }

    // Choose cards to flip
    const toFlip = this.brain.chooseInitialFlips(myCards);

    for (const pos of toFlip) {
      if (faceDownPositions.includes(pos)) {
        const result = await this.actions.flipCard(pos);
        if (!result.success) {
          return { success: false, action: 'initial_flip', error: result.error };
        }
      }
    }

    return {
      success: true,
      action: 'initial_flip',
      details: { positions: toFlip },
    };
  }

  /**
   * Handle draw phase
   */
  private async handleDraw(state: ParsedGameState): Promise<TurnResult> {
    const myCards = state.myPlayer?.cards || [];
    const discardTop = state.discard.topCard;

    // Decide: discard or deck
    const takeDiscard = this.brain.shouldTakeDiscard(discardTop, myCards);

    let result: ActionResult;
    let source: string;

    if (takeDiscard && state.discard.clickable) {
      result = await this.actions.drawFromDiscard();
      source = 'discard';
    } else {
      result = await this.actions.drawFromDeck();
      source = 'deck';
    }

    if (!result.success) {
      return { success: false, action: 'draw', error: result.error };
    }

    // Wait for held card to be visible
    await this.page.waitForTimeout(500);

    // Now handle swap or discard
    const newState = await this.getGameState();

    // If held card still not visible, wait a bit more and retry
    if (!newState.heldCard.visible) {
      await this.page.waitForTimeout(500);
      const retryState = await this.getGameState();
      return this.handleSwapOrDiscard(retryState, source === 'discard');
    }

    return this.handleSwapOrDiscard(newState, source === 'discard');
  }

  /**
   * Handle swap or discard decision
   */
  private async handleSwapOrDiscard(
    state: ParsedGameState,
    mustSwap: boolean = false
  ): Promise<TurnResult> {
    const myCards = state.myPlayer?.cards || [];
    const heldCard = state.heldCard.card;

    if (!heldCard) {
      return { success: false, action: 'swap_or_discard', error: 'No held card' };
    }

    // Decide: swap position or discard
    const swapPos = this.brain.chooseSwapPosition(heldCard, myCards, mustSwap);

    if (swapPos !== null) {
      // Swap
      const result = await this.actions.swapCard(swapPos);
      return {
        success: result.success,
        action: 'swap',
        details: { position: swapPos, card: heldCard },
        error: result.error,
      };
    } else {
      // Discard
      const result = await this.actions.discardDrawn();

      if (!result.success) {
        return { success: false, action: 'discard', error: result.error };
      }

      // Check if we need to flip
      await this.page.waitForTimeout(200);
      const afterState = await this.getGameState();

      if (afterState.phase === 'waiting_for_flip') {
        return this.handleWaitingForFlip(afterState);
      }

      return {
        success: true,
        action: 'discard',
        details: { card: heldCard },
      };
    }
  }

  /**
   * Handle waiting for flip after discard
   */
  private async handleWaitingForFlip(state: ParsedGameState): Promise<TurnResult> {
    const myCards = state.myPlayer?.cards || [];

    // Check if flip is optional
    if (state.canSkipFlip) {
      if (this.brain.shouldSkipFlip(myCards)) {
        const result = await this.actions.skipFlip();
        return {
          success: result.success,
          action: 'skip_flip',
          error: result.error,
        };
      }
    }

    // Choose a card to flip
    const pos = this.brain.chooseFlipPosition(myCards);
    const result = await this.actions.flipCard(pos);

    return {
      success: result.success,
      action: 'flip',
      details: { position: pos },
      error: result.error,
    };
  }

  /**
   * Take a screenshot with label
   */
  async takeScreenshot(label: string): Promise<Buffer> {
    const buffer = await this.page.screenshot();
    this.screenshots.push({ label, buffer });
    return buffer;
  }

  /**
   * Get all collected screenshots
   */
  getScreenshots(): { label: string; buffer: Buffer }[] {
    return this.screenshots;
  }

  /**
   * Get console errors collected
   */
  getConsoleErrors(): string[] {
    return this.consoleErrors;
  }

  /**
   * Clear console errors
   */
  clearConsoleErrors(): void {
    this.consoleErrors = [];
  }

  /**
   * Check if the UI appears frozen (animation stuck)
   */
  async isFrozen(timeout: number = 3000): Promise<boolean> {
    try {
      await waitForAnimations(this.page, timeout);
      return false;
    } catch {
      return true;
    }
  }

  /**
   * Get turn count
   */
  getTurnCount(): number {
    return this.turnCount;
  }

  /**
   * Play through initial flip phase completely
   */
  async completeInitialFlips(): Promise<void> {
    let phase = await this.getGamePhase();
    let attempts = 0;
    const maxAttempts = 10;

    while (phase === 'initial_flip' && attempts < maxAttempts) {
      if (await this.isMyTurn()) {
        await this.playTurn();
      }
      await this.page.waitForTimeout(500);
      phase = await this.getGamePhase();
      attempts++;
    }
  }

  /**
   * Play through entire round
   */
  async playRound(maxTurns: number = 100): Promise<{ success: boolean; turns: number }> {
    let turns = 0;

    while (turns < maxTurns) {
      const phase = await this.getGamePhase();

      if (phase === 'round_over' || phase === 'game_over') {
        return { success: true, turns };
      }

      if (await this.isMyTurn()) {
        const result = await this.playTurn();
        if (!result.success) {
          console.warn(`Turn ${turns} failed:`, result.error);
        }
        turns++;
      }

      await this.page.waitForTimeout(200);

      // Check for frozen state
      if (await this.isFrozen()) {
        return { success: false, turns };
      }
    }

    return { success: false, turns };
  }

  /**
   * Play through entire game (all rounds)
   */
  async playGame(maxRounds: number = 18): Promise<{
    success: boolean;
    rounds: number;
    totalTurns: number;
  }> {
    let rounds = 0;
    let totalTurns = 0;

    while (rounds < maxRounds) {
      const phase = await this.getGamePhase();

      if (phase === 'game_over') {
        return { success: true, rounds, totalTurns };
      }

      // Complete initial flips first
      await this.completeInitialFlips();

      // Play the round
      const roundResult = await this.playRound();
      totalTurns += roundResult.turns;
      rounds++;

      if (!roundResult.success) {
        return { success: false, rounds, totalTurns };
      }

      // Check for game over
      let newPhase = await this.getGamePhase();
      if (newPhase === 'game_over') {
        return { success: true, rounds, totalTurns };
      }

      // Check if this was the final round
      const state = await this.getGameState();
      const isLastRound = state.currentRound >= state.totalRounds;

      // If last round just ended, wait for game_over or trigger it
      if (newPhase === 'round_over' && isLastRound) {
        // Wait a few seconds for auto-transition or countdown
        for (let i = 0; i < 10; i++) {
          await this.page.waitForTimeout(1000);
          newPhase = await this.getGamePhase();
          if (newPhase === 'game_over') {
            return { success: true, rounds, totalTurns };
          }
        }

        // Game might require clicking Next Hole to show Final Results
        // Try clicking the button to trigger the transition
        const nextResult = await this.actions.nextRound();

        // Wait for Final Results modal to appear
        for (let i = 0; i < 10; i++) {
          await this.page.waitForTimeout(1000);
          newPhase = await this.getGamePhase();
          if (newPhase === 'game_over') {
            return { success: true, rounds, totalTurns };
          }
        }
      }

      // Start next round if available
      if (newPhase === 'round_over') {
        await this.page.waitForTimeout(1000);
        const nextResult = await this.actions.nextRound();
        if (!nextResult.success) {
          // Maybe we're not the host, wait for host to start
          await this.page.waitForTimeout(5000);
        }
      }
    }

    return { success: true, rounds, totalTurns };
  }
}
