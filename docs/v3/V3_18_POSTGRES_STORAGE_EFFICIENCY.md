# V3.18: PostgreSQL Game Data Storage Efficiency

**Status:** Planning
**Priority:** Medium
**Category:** Infrastructure / Performance

## Problem

Per-move game logging stores full `hand_state` and `visible_opponents` JSONB on every move. For a typical 6-player, 9-hole game this generates significant redundant data since most of each player's hand doesn't change between moves.

## Areas to Investigate

### 1. Delta Encoding for Move Data

Store only what changed from the previous move instead of full state snapshots.

- First move of each round stores full state (baseline)
- Subsequent moves store only changed positions (e.g., `{"player_0": {"pos_2": "5H"}}`)
- Replay reconstruction applies deltas sequentially
- Trade-off: simpler queries vs. storage savings

### 2. PostgreSQL TOAST and Compression

- TOAST already compresses large JSONB values automatically
- Measure actual on-disk size vs. logical size for typical game data
- Consider whether explicit compression (e.g., storing gzipped blobs) adds meaningful savings over TOAST

### 3. Retention Policy

- Archive completed games older than N days to a separate table or cold storage
- Configurable retention period via env var (e.g., `GAME_LOG_RETENTION_DAYS`)
- Keep aggregate stats even after pruning raw move data

### 4. Move Logging Toggle

- Env var `GAME_LOGGING_ENABLED=true|false` to disable move-level logging entirely
- Useful for non-analysis environments (dev, load testing)
- Game outcomes and stats would still be recorded

### 5. Batch Inserts

- Buffer moves in memory and flush periodically instead of per-move INSERT
- Reduces database round-trips during active games
- Risk: data loss if server crashes mid-game (acceptable for non-critical move logs)

## Measurements Needed

Before optimizing, measure current impact:

- Average JSONB size per move (bytes)
- Average moves per game
- Total storage per game (moves + overhead)
- Query patterns: how often is per-move data actually read?

## Dependencies

- None (independent infrastructure improvement)
