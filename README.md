# Golf Card Game

A multiplayer online 6-card Golf card game with AI opponents and extensive house rules support.

## Features

- **Multiplayer:** 2-6 players via WebSocket
- **AI Opponents:** 8 unique CPU personalities with distinct play styles
- **House Rules:** 15+ optional rule variants
- **Game Logging:** SQLite logging for AI decision analysis
- **Comprehensive Testing:** 80+ tests for rules and AI behavior

## Quick Start

### 1. Install Dependencies

```bash
cd server
pip install -r requirements.txt
```

### 2. Start the Server

```bash
cd server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Open the Game

Open `http://localhost:8000` in your browser.

## How to Play

**6-Card Golf** is a card game where you try to get the **lowest score** across multiple rounds (holes).

- Each player has 6 cards in a 2×3 grid (most start face-down)
- On your turn: **draw** a card, then **swap** it with one of yours or **discard** it
- **Column pairs** (same rank top & bottom) score **0 points** — very powerful!
- When any player reveals all 6 cards, everyone else gets one final turn
- Lowest total score after all rounds wins

**For detailed rules, card values, and house rule explanations, see the in-game Rules page or [server/RULES.md](server/RULES.md).**

## AI Personalities

| Name | Style | Description |
|------|-------|-------------|
| Sofia | Calculated & Patient | Conservative, low risk |
| Maya | Aggressive Closer | Goes out early |
| Priya | Pair Hunter | Holds cards hoping for pairs |
| Marcus | Steady Eddie | Balanced, consistent |
| Kenji | Risk Taker | High variance plays |
| Diego | Chaotic Gambler | Unpredictable |
| River | Adaptive Strategist | Adjusts to game state |
| Sage | Sneaky Finisher | Aggressive end-game |

## House Rules

The game supports 15+ optional house rules including:

- **Flip Modes** - Standard, Speed Golf (must flip after discard), Suspense (optional flip near endgame)
- **Point Modifiers** - Super Kings (-2), Ten Penny (10=1), Lucky Swing Joker (-5)
- **Bonuses & Penalties** - Knock bonus/penalty, Underdog bonus, Tied Shame, Blackjack (21→0)
- **Joker Variants** - Standard, Eagle Eye (paired Jokers = -8)

See the in-game Rules page or [server/RULES.md](server/RULES.md) for complete explanations.

## Development

### Project Structure

```
golfgame/
├── server/
│   ├── main.py              # FastAPI WebSocket server
│   ├── game.py              # Core game logic
│   ├── ai.py                # AI decision making
│   ├── room.py              # Room/lobby management
│   ├── game_log.py          # SQLite logging
│   ├── game_analyzer.py     # Decision analysis CLI
│   ├── simulate.py          # AI-vs-AI simulation
│   ├── score_analysis.py    # Score distribution analysis
│   ├── test_game.py         # Game rules tests
│   ├── test_analyzer.py     # Analyzer tests
│   ├── test_maya_bug.py     # Bug regression tests
│   ├── test_house_rules.py  # House rules testing
│   └── RULES.md             # Rules documentation
├── client/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── README.md
```

### Running Tests

```bash
cd server
pytest test_game.py test_analyzer.py test_maya_bug.py -v
```

### AI Simulation

```bash
# Run 50 games with 4 AI players
python simulate.py 50 4

# Run detailed single game
python simulate.py detail 4

# Analyze AI decisions for blunders
python game_analyzer.py blunders

# Score distribution analysis
python score_analysis.py 100 4

# Test all house rules
python test_house_rules.py 40
```

### AI Performance

From testing (1000+ games):
- **0 blunders** detected in simulation
- **Median score:** 12 points
- **Score range:** -4 to 34 (typical)
- Personalities influence style without compromising competence

## Technology Stack

- **Backend:** Python 3.12+, FastAPI, WebSockets
- **Frontend:** Vanilla HTML/CSS/JavaScript
- **Database:** SQLite (optional, for game logging)
- **Testing:** pytest

## License

MIT
