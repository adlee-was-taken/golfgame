"""Bordered player container with name, score, and state indicators."""

from __future__ import annotations

import re

# Border colors matching web UI palette
_BORDER_NORMAL = "#555555"
_BORDER_TURN_LOCAL = "#f4a460"    # sandy orange — your turn (matches opponent turn)
_BORDER_TURN_OPPONENT = "#f4a460"  # sandy orange — opponent's turn
_BORDER_KNOCKER = "#ff6b35"        # red-orange — went out
_NAME_COLOR = "#e0e0e0"


def _visible_len(text: str) -> int:
    """Length of text with Rich markup tags stripped."""
    return len(re.sub(r"\[.*?\]", "", text))


def render_player_box(
    name: str,
    score: int | None,
    total_score: int,
    content_lines: list[str],
    *,
    is_current_turn: bool = False,
    is_knocker: bool = False,
    is_dealer: bool = False,
    is_local: bool = False,
) -> list[str]:
    """Render a bordered player container with name/score header.

    Every line in the returned list has the same visible width (``box_width``).

    Layout::

        ╭─ Name ────── 15 ─╮
        │ ┌───┐ ┌───┐ ┌───┐│
        │ │ A │ │░░░│ │ 7 ││
        │ │ ♠ │ │░░░│ │ ♦ ││
        │ └───┘ └───┘ └───┘│
        │ ┌───┐ ┌───┐ ┌───┐│
        │ │ 4 │ │ 5 │ │ Q ││
        │ │ ♣ │ │ ♥ │ │ ♦ ││
        │ └───┘ └───┘ └───┘│
        ╰──────────────────╯
    """
    # Pick border color based on state
    if is_knocker:
        bc = _BORDER_KNOCKER
    elif is_current_turn and is_local:
        bc = _BORDER_TURN_LOCAL
    elif is_current_turn:
        bc = _BORDER_TURN_OPPONENT
    else:
        bc = _BORDER_NORMAL

    # Build display name
    display_name = name
    if is_dealer:
        display_name = f"Ⓓ {display_name}"
    # Score text
    score_val = f"{score}" if score is not None else f"{total_score}"
    score_text = f"{score_val}"

    # Compute box width.  Every line is exactly box_width visible chars.
    # Content row: │ <space> <content> <pad> │  =>  box_width = vis(content) + 4
    max_vis = max((_visible_len(line) for line in content_lines), default=17)
    name_part = f" {display_name} "
    score_part = f" {score_text} "
    # Top row:  ╭─ <name_part> <fill> <score_part> ─╮
    #           = 4 + len(name_part) + fill + len(score_part)
    min_top = 4 + len(name_part) + 1 + len(score_part)  # fill>=1
    box_width = max(max_vis + 4, 21, min_top)

    # Possibly truncate name if it still doesn't fit
    fill_len = box_width - 4 - len(name_part) - len(score_part)
    if fill_len < 1:
        max_name = box_width - 4 - len(score_part) - 4
        display_name = display_name[: max(3, max_name)] + "…"
        name_part = f" {display_name} "
        fill_len = box_width - 4 - len(name_part) - len(score_part)

    fill = "─" * max(1, fill_len)

    # Top border
    top = (
        f"[{bc}]╭─[/]"
        f"[bold {_NAME_COLOR}]{name_part}[/]"
        f"[{bc}]{fill}[/]"
        f"[bold]{score_part}[/]"
        f"[{bc}]─╮[/]"
    )

    result = [top]

    # Content lines
    inner = box_width - 2  # chars between │ and │
    for line in content_lines:
        vis_len = _visible_len(line)
        right_pad = max(0, inner - 1 - vis_len)
        result.append(
            f"[{bc}]│[/] {line}{' ' * right_pad}[{bc}]│[/]"
        )

    # Bottom border
    if is_knocker:
        out_label = " OUT "
        left_fill = 1
        right_fill = inner - left_fill - len(out_label)
        result.append(
            f"[{bc}]╰{'─' * left_fill}[/]"
            f"[bold {bc}]{out_label}[/]"
            f"[{bc}]{'─' * max(1, right_fill)}╯[/]"
        )
    else:
        result.append(f"[{bc}]╰{'─' * inner}╯[/]")

    return result
