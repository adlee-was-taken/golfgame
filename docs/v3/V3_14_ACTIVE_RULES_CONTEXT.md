# V3-14: Active Rules Context

## Overview

The active rules bar shows which house rules are in effect, but doesn't highlight when a rule is relevant to the current action. This feature adds contextual highlighting to help players understand rule effects.

**Dependencies:** None
**Dependents:** None

---

## Goals

1. Highlight relevant rules during specific actions
2. Brief explanatory tooltip when rule affects play
3. Help players learn how rules work
4. Don't clutter the interface
5. Fade after the moment passes

---

## Current State

From `app.js`:
```javascript
updateActiveRulesBar() {
    const rules = this.gameState.active_rules || [];
    if (rules.length === 0) {
        this.activeRulesList.innerHTML = '<span class="rule-tag standard">Standard</span>';
    } else {
        // Show rule tags
    }
}
```

Rules are listed but never highlighted contextually.

---

## Design

### Contextual Highlighting Moments

| Moment | Relevant Rule(s) | Highlight Text |
|--------|------------------|----------------|
| Discard from deck | flip_mode: always | "Must flip a card!" |
| Player knocks | knock_penalty | "+10 if not lowest!" |
| Player knocks | knock_bonus | "-5 for going out first" |
| Pair negative cards | negative_pairs_keep_value | "Pairs keep -4!" |
| Draw Joker | lucky_swing | "Worth -5!" |
| Round end | underdog_bonus | "-3 for lowest score" |
| Score = 21 | blackjack | "Blackjack! Score → 0" |
| Four Jacks | wolfpack | "-20 Wolfpack bonus!" |

### Visual Treatment

```
Normal:     [Speed Golf] [Knock Penalty]

Highlighted: [Speed Golf ← Must flip!] [Knock Penalty]
                 ↑
            Pulsing, expanded
```

---

## Implementation

### Rule Highlight Method

```javascript
highlightRule(ruleKey, message, duration = 3000) {
    const ruleTag = this.activeRulesList.querySelector(
        `[data-rule="${ruleKey}"]`
    );

    if (!ruleTag) return;

    // Add highlight class
    ruleTag.classList.add('rule-highlighted');

    // Add message
    const messageEl = document.createElement('span');
    messageEl.className = 'rule-message';
    messageEl.textContent = message;
    ruleTag.appendChild(messageEl);

    // Remove after duration
    setTimeout(() => {
        ruleTag.classList.remove('rule-highlighted');
        messageEl.remove();
    }, duration);
}
```

### Integration Points

```javascript
// In handleMessage or state change handlers

// 1. Speed Golf - must flip after discard
case 'can_flip':
    if (!data.optional && this.gameState.flip_mode === 'always') {
        this.highlightRule('flip_mode', 'Must flip a card!');
    }
    break;

// 2. Knock penalty warning
knockEarly() {
    if (this.gameState.knock_penalty) {
        this.highlightRule('knock_penalty', '+10 if not lowest!', 4000);
    }
    // ... rest of knock logic
}

// 3. Lucky swing Joker
case 'card_drawn':
    if (data.card.rank === '★' && this.gameState.lucky_swing) {
        this.highlightRule('lucky_swing', 'Worth -5!');
    }
    break;

// 4. Blackjack at round end
showScoreboard(scores, isFinal, rankings) {
    // Check for blackjack
    for (const [playerId, score] of Object.entries(scores)) {
        if (score === 0 && this.wasOriginallyBlackjack(playerId)) {
            this.highlightRule('blackjack', 'Blackjack! 21 → 0');
        }
    }
    // ... rest of scoreboard logic
}
```

### Update Rule Rendering

Add data attributes for targeting:

```javascript
updateActiveRulesBar() {
    const rules = this.gameState.active_rules || [];

    if (rules.length === 0) {
        this.activeRulesList.innerHTML = '<span class="rule-tag standard">Standard</span>';
        return;
    }

    this.activeRulesList.innerHTML = rules
        .map(rule => {
            const key = this.getRuleKey(rule);
            return `<span class="rule-tag" data-rule="${key}">${rule}</span>`;
        })
        .join('');
}

getRuleKey(ruleName) {
    // Convert display name to key
    const mapping = {
        'Speed Golf': 'flip_mode',
        'Endgame Flip': 'flip_mode',
        'Knock Penalty': 'knock_penalty',
        'Knock Bonus': 'knock_bonus',
        'Super Kings': 'super_kings',
        'Ten Penny': 'ten_penny',
        'Lucky Swing': 'lucky_swing',
        'Eagle Eye': 'eagle_eye',
        'Underdog': 'underdog_bonus',
        'Tied Shame': 'tied_shame',
        'Blackjack': 'blackjack',
        'Wolfpack': 'wolfpack',
        'Flip Action': 'flip_as_action',
        '4 of a Kind': 'four_of_a_kind',
        'Negative Pairs': 'negative_pairs_keep_value',
        'One-Eyed Jacks': 'one_eyed_jacks',
        'Knock Early': 'knock_early',
    };
    return mapping[ruleName] || ruleName.toLowerCase().replace(/\s+/g, '_');
}
```

### CSS

```css
/* Rule tag base */
.rule-tag {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    background: rgba(255, 255, 255, 0.15);
    border-radius: 12px;
    font-size: 0.8em;
    transition: all 0.3s ease;
}

/* Highlighted rule */
.rule-tag.rule-highlighted {
    background: rgba(244, 164, 96, 0.3);
    box-shadow: 0 0 10px rgba(244, 164, 96, 0.4);
    animation: rule-pulse 0.5s ease-out;
}

@keyframes rule-pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
}

/* Message that appears */
.rule-message {
    margin-left: 8px;
    padding-left: 8px;
    border-left: 1px solid rgba(255, 255, 255, 0.3);
    font-weight: bold;
    color: #f4a460;
    animation: message-fade-in 0.3s ease-out;
}

@keyframes message-fade-in {
    0% { opacity: 0; transform: translateX(-5px); }
    100% { opacity: 1; transform: translateX(0); }
}

/* Ensure bar is visible when highlighted */
#active-rules-bar:has(.rule-highlighted) {
    background: rgba(0, 0, 0, 0.4);
}
```

---

## Rule-Specific Triggers

### Flip Mode (Speed Golf/Endgame)

```javascript
// When player must flip
if (this.waitingForFlip && !this.flipIsOptional) {
    this.highlightRule('flip_mode', 'Flip a face-down card!');
}
```

### Knock Penalty/Bonus

```javascript
// When someone triggers final turn
if (newState.phase === 'final_turn' && oldState?.phase !== 'final_turn') {
    if (this.gameState.knock_penalty) {
        this.highlightRule('knock_penalty', '+10 if beaten!');
    }
    if (this.gameState.knock_bonus) {
        this.highlightRule('knock_bonus', '-5 for going out!');
    }
}
```

### Negative Pairs

```javascript
// When pair of 2s or Jokers is formed
checkForNewPairs(oldState, newState, playerId) {
    // ... pair detection ...
    if (nowPaired && this.gameState.negative_pairs_keep_value) {
        const isNegativePair = cardRank === '2' || cardRank === '★';
        if (isNegativePair) {
            this.highlightRule('negative_pairs_keep_value', 'Keeps -4!');
        }
    }
}
```

### Score Bonuses (Round End)

```javascript
// In showScoreboard
if (this.gameState.underdog_bonus) {
    const lowestPlayer = findLowest(scores);
    this.highlightRule('underdog_bonus', `${lowestPlayer} gets -3!`);
}

if (this.gameState.tied_shame) {
    const ties = findTies(scores);
    if (ties.length > 0) {
        this.highlightRule('tied_shame', '+5 for ties!');
    }
}
```

---

## Test Scenarios

1. **Speed Golf mode** - "Must flip" highlighted when discarding
2. **Knock with penalty** - Warning shown
3. **Draw Lucky Swing Joker** - "-5" highlighted
4. **Blackjack score** - Celebration when 21 → 0
5. **No active rules** - No highlights
6. **Multiple rules trigger** - All relevant ones highlight

---

## Acceptance Criteria

- [ ] Rules have data attributes for targeting
- [ ] Relevant rule highlights during specific actions
- [ ] Highlight message explains the effect
- [ ] Highlight auto-fades after duration
- [ ] Multiple rules can highlight simultaneously
- [ ] Works for all major house rules
- [ ] Doesn't interfere with gameplay flow

---

## Implementation Order

1. Add `data-rule` attributes to rule tags
2. Implement `getRuleKey()` mapping
3. Implement `highlightRule()` method
4. Add CSS for highlight animation
5. Add trigger points for each major rule
6. Test with various rule combinations
7. Tune timing and messaging

---

## Notes for Agent

- **CSS vs anime.js**: CSS is appropriate for rule tag highlights (simple UI feedback)
- Keep highlight messages very short (3-5 words)
- Don't highlight on every single action, just key moments
- The goal is education, not distraction
- Consider: First-time highlight only? (Too complex for V3)
- Make sure the bar is visible when highlighting (expand if collapsed)
