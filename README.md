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

## Game Rules

See [server/RULES.md](server/RULES.md) for complete rules documentation.

### Basic Scoring

| Card | Points |
|------|--------|
| Ace | 1 |
| 2 | **-2** |
| 3-10 | Face value |
| Jack, Queen | 10 |
| King | **0** |
| Joker | -2 *(optional)* |

**Column pairs** (same rank in a column) score **0 points**.

### Turn Structure

1. Draw from deck OR take from discard pile
2. **If from deck:** Swap with a card OR discard and flip a face-down card
3. **If from discard:** Must swap (cannot re-discard)

### Ending

When a player reveals all 6 cards, others get one final turn. Lowest score wins.

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

### Point Modifiers
- `super_kings` - Kings worth -2 (instead of 0)
- `ten_penny` - 10s worth 1 (instead of 10)
- `lucky_swing` - Single Joker worth -5
- `eagle_eye` - Paired Jokers score -8

### Bonuses & Penalties
- `knock_bonus` - First to go out gets -5
- `underdog_bonus` - Lowest scorer gets -3
- `knock_penalty` - +10 if you go out but aren't lowest
- `tied_shame` - +5 penalty for tied scores
- `blackjack` - Score of exactly 21 becomes 0

### Gameplay Options
- `flip_mode` - What happens when discarding from deck:
  - `never` - Standard (no flip)
  - `always` - Speed Golf (must flip after discard)
  - `endgame` - Suspense (optional flip when any player has ≤1 face-down card)
- `use_jokers` - Add Jokers to deck
- `eagle_eye` - Paired Jokers score -8 instead of canceling

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
