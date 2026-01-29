/**
 * DOM selector constants for the Golf game
 * Extracted from client/index.html and client/app.js
 */

export const SELECTORS = {
  // Screens
  screens: {
    lobby: '#lobby-screen',
    waiting: '#waiting-screen',
    game: '#game-screen',
    rules: '#rules-screen',
  },

  // Lobby elements
  lobby: {
    playerNameInput: '#player-name',
    roomCodeInput: '#room-code',
    createRoomBtn: '#create-room-btn',
    joinRoomBtn: '#join-room-btn',
    error: '#lobby-error',
  },

  // Waiting room elements
  waiting: {
    roomCode: '#display-room-code',
    copyCodeBtn: '#copy-room-code',
    shareBtn: '#share-room-link',
    playersList: '#players-list',
    hostSettings: '#host-settings',
    startGameBtn: '#start-game-btn',
    leaveRoomBtn: '#leave-room-btn',
    addCpuBtn: '#add-cpu-btn',
    removeCpuBtn: '#remove-cpu-btn',
    cpuModal: '#cpu-select-modal',
    cpuProfilesGrid: '#cpu-profiles-grid',
    cancelCpuBtn: '#cancel-cpu-btn',
    addSelectedCpusBtn: '#add-selected-cpus-btn',
    // Settings
    numDecks: '#num-decks',
    numRounds: '#num-rounds',
    initialFlips: '#initial-flips',
    flipMode: '#flip-mode',
    knockPenalty: '#knock-penalty',
  },

  // Game screen elements
  game: {
    // Header
    currentRound: '#current-round',
    totalRounds: '#total-rounds',
    statusMessage: '#status-message',
    finalTurnBadge: '#final-turn-badge',
    muteBtn: '#mute-btn',
    leaveGameBtn: '#leave-game-btn',
    activeRulesBar: '#active-rules-bar',

    // Table
    opponentsRow: '#opponents-row',
    playerArea: '.player-area',
    playerCards: '#player-cards',
    playerHeader: '#player-header',
    yourScore: '#your-score',

    // Deck and discard
    deckArea: '.deck-area',
    deck: '#deck',
    discard: '#discard',
    discardContent: '#discard-content',
    discardBtn: '#discard-btn',
    skipFlipBtn: '#skip-flip-btn',
    knockEarlyBtn: '#knock-early-btn',

    // Held card
    heldCardSlot: '#held-card-slot',
    heldCardDisplay: '#held-card-display',
    heldCardFloating: '#held-card-floating',
    heldCardFloatingContent: '#held-card-floating-content',

    // Scoreboard
    scoreboard: '#scoreboard',
    scoreTable: '#score-table tbody',
    standingsList: '#standings-list',
    nextRoundBtn: '#next-round-btn',
    newGameBtn: '#new-game-btn',
    gameButtons: '#game-buttons',

    // Card layer for animations
    cardLayer: '#card-layer',
  },

  // Card-related selectors
  cards: {
    // Player's own cards (0-5)
    playerCard: (index: number) => `#player-cards .card:nth-child(${index + 1})`,
    playerCardSlot: (index: number) => `#player-cards .card-slot:nth-child(${index + 1})`,

    // Opponent cards
    opponentArea: (index: number) => `.opponent-area:nth-child(${index + 1})`,
    opponentCard: (oppIndex: number, cardIndex: number) =>
      `.opponent-area:nth-child(${oppIndex + 1}) .card-grid .card:nth-child(${cardIndex + 1})`,

    // Card states
    faceUp: '.card-front',
    faceDown: '.card-back',
    clickable: '.clickable',
    selected: '.selected',
  },

  // CSS classes for state detection
  classes: {
    active: 'active',
    hidden: 'hidden',
    clickable: 'clickable',
    selected: 'selected',
    faceUp: 'card-front',
    faceDown: 'card-back',
    red: 'red',
    black: 'black',
    joker: 'joker',
    currentTurn: 'current-turn',
    roundWinner: 'round-winner',
    yourTurnToDraw: 'your-turn-to-draw',
    hasCard: 'has-card',
    pickedUp: 'picked-up',
    disabled: 'disabled',
  },

  // Animation-related
  animations: {
    swapAnimation: '#swap-animation',
    swapCardFromHand: '#swap-card-from-hand',
    animCard: '.anim-card',
    realCard: '.real-card',
  },
};

/**
 * Build a selector for a card in the player's grid
 */
export function playerCardSelector(position: number): string {
  return SELECTORS.cards.playerCard(position);
}

/**
 * Build a selector for a clickable card
 */
export function clickableCardSelector(position: number): string {
  return `${SELECTORS.cards.playerCard(position)}.${SELECTORS.classes.clickable}`;
}

/**
 * Build a selector for an opponent's card
 */
export function opponentCardSelector(opponentIndex: number, cardPosition: number): string {
  return SELECTORS.cards.opponentCard(opponentIndex, cardPosition);
}
