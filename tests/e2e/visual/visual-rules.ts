/**
 * Visual rules - expected visual states for different game phases
 */

import { ScreenshotValidator } from './screenshot-validator';

/**
 * Expected visual states for game start
 */
export async function validateGameStart(
  validator: ScreenshotValidator
): Promise<{ passed: boolean; failures: string[] }> {
  const failures: string[] = [];

  // All cards should be visible (face up or down)
  for (let i = 0; i < 6; i++) {
    const result = await validator.expectCount(
      `#player-cards .card:nth-child(${i + 1})`,
      1
    );
    if (!result.passed) {
      failures.push(`Card ${i} not present`);
    }
  }

  // Status message should indicate game phase
  const statusResult = await validator.expectVisible('#status-message');
  if (!statusResult.passed) {
    failures.push('Status message not visible');
  }

  // Deck should be visible
  const deckResult = await validator.expectVisible('#deck');
  if (!deckResult.passed) {
    failures.push('Deck not visible');
  }

  // Discard should be visible
  const discardResult = await validator.expectVisible('#discard');
  if (!discardResult.passed) {
    failures.push('Discard not visible');
  }

  return { passed: failures.length === 0, failures };
}

/**
 * Expected visual states after initial flip
 */
export async function validateAfterInitialFlip(
  validator: ScreenshotValidator,
  expectedFaceUp: number = 2
): Promise<{ passed: boolean; failures: string[] }> {
  const failures: string[] = [];

  // Count face-up cards
  const faceUpResult = await validator.expectCount(
    '#player-cards .card.card-front',
    expectedFaceUp
  );
  if (!faceUpResult.passed) {
    failures.push(`Expected ${expectedFaceUp} face-up cards, got ${faceUpResult.actual}`);
  }

  // Count face-down cards
  const faceDownResult = await validator.expectCount(
    '#player-cards .card.card-back',
    6 - expectedFaceUp
  );
  if (!faceDownResult.passed) {
    failures.push(`Expected ${6 - expectedFaceUp} face-down cards, got ${faceDownResult.actual}`);
  }

  return { passed: failures.length === 0, failures };
}

/**
 * Expected visual states during player's turn (draw phase)
 */
export async function validateDrawPhase(
  validator: ScreenshotValidator
): Promise<{ passed: boolean; failures: string[] }> {
  const failures: string[] = [];

  // Deck should be clickable
  const deckResult = await validator.expectDeckClickable();
  if (!deckResult.passed) {
    failures.push('Deck should be clickable');
  }

  // Held card should NOT be visible yet
  const heldResult = await validator.expectHeldCardHidden();
  if (!heldResult.passed) {
    failures.push('Held card should not be visible before draw');
  }

  // Discard button should be hidden
  const discardBtnResult = await validator.expectNotVisible('#discard-btn');
  if (!discardBtnResult.passed) {
    failures.push('Discard button should be hidden before draw');
  }

  return { passed: failures.length === 0, failures };
}

/**
 * Expected visual states after drawing a card
 */
export async function validateAfterDraw(
  validator: ScreenshotValidator
): Promise<{ passed: boolean; failures: string[] }> {
  const failures: string[] = [];

  // Held card should be visible (floating)
  const heldResult = await validator.expectHeldCardVisible();
  if (!heldResult.passed) {
    failures.push('Held card should be visible after draw');
  }

  // Player cards should be clickable
  const clickableResult = await validator.expectCount(
    '#player-cards .card.clickable',
    6
  );
  if (!clickableResult.passed) {
    failures.push('All player cards should be clickable');
  }

  return { passed: failures.length === 0, failures };
}

/**
 * Expected visual states for round over
 */
export async function validateRoundOver(
  validator: ScreenshotValidator
): Promise<{ passed: boolean; failures: string[] }> {
  const failures: string[] = [];

  // All player cards should be face-up
  const faceUpResult = await validator.expectCount(
    '#player-cards .card.card-front',
    6
  );
  if (!faceUpResult.passed) {
    failures.push('All cards should be face-up at round end');
  }

  // Next round button OR new game button should be visible
  const nextRoundResult = await validator.expectVisible('#next-round-btn');
  const newGameResult = await validator.expectVisible('#new-game-btn');

  if (!nextRoundResult.passed && !newGameResult.passed) {
    failures.push('Neither next round nor new game button visible');
  }

  // Game buttons container should be visible
  const gameButtonsResult = await validator.expectVisible('#game-buttons');
  if (!gameButtonsResult.passed) {
    failures.push('Game buttons should be visible');
  }

  return { passed: failures.length === 0, failures };
}

/**
 * Expected visual states for final turn
 */
export async function validateFinalTurn(
  validator: ScreenshotValidator
): Promise<{ passed: boolean; failures: string[] }> {
  const failures: string[] = [];

  // Final turn badge should be visible
  const badgeResult = await validator.expectFinalTurnBadge();
  if (!badgeResult.passed) {
    failures.push('Final turn badge should be visible');
  }

  return { passed: failures.length === 0, failures };
}

/**
 * Expected visual states during opponent's turn
 */
export async function validateOpponentTurn(
  validator: ScreenshotValidator,
  opponentIndex: number
): Promise<{ passed: boolean; failures: string[] }> {
  const failures: string[] = [];

  // Opponent should have current-turn highlight
  const turnResult = await validator.expectOpponentCurrentTurn(opponentIndex);
  if (!turnResult.passed) {
    failures.push(`Opponent ${opponentIndex} should have current-turn class`);
  }

  // Deck should NOT be clickable (not our turn)
  const deckResult = await validator.expectNoClass('#deck', 'clickable');
  if (!deckResult.passed) {
    failures.push('Deck should not be clickable during opponent turn');
  }

  return { passed: failures.length === 0, failures };
}

/**
 * Validate responsive layout at specific width
 */
export async function validateResponsiveLayout(
  validator: ScreenshotValidator,
  width: number
): Promise<{ passed: boolean; failures: string[] }> {
  const failures: string[] = [];

  // Core elements should still be visible
  const elements = [
    '#deck',
    '#discard',
    '#player-cards',
    '#status-message',
  ];

  for (const selector of elements) {
    const result = await validator.expectVisible(selector);
    if (!result.passed) {
      failures.push(`${selector} not visible at ${width}px width`);
    }
  }

  return { passed: failures.length === 0, failures };
}
