"""Status bar showing phase, turn info, and action prompts."""

from __future__ import annotations

from textual.widgets import Static

from tui_client.models import GameState


class StatusBarWidget(Static):
    """Top status bar with round, phase, and turn info."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._state: GameState | None = None
        self._player_id: str | None = None
        self._extra: str = ""

    def update_state(self, state: GameState, player_id: str | None = None) -> None:
        self._state = state
        self._player_id = player_id
        self._refresh()

    def set_extra(self, text: str) -> None:
        self._extra = text
        self._refresh()

    def _refresh(self) -> None:
        if not self._state:
            self.update("Connecting...")
            return

        state = self._state
        parts = []

        # Round info
        parts.append(f"Round {state.current_round}/{state.total_rounds}")

        # Phase
        phase_display = {
            "waiting": "Waiting",
            "initial_flip": "[bold white on #6a0dad] Flip Phase [/bold white on #6a0dad]",
            "playing": "Playing",
            "final_turn": "[bold white on #c62828] FINAL TURN [/bold white on #c62828]",
            "round_over": "[white on #555555] Round Over [/white on #555555]",
            "game_over": "[bold white on #b8860b] Game Over [/bold white on #b8860b]",
        }.get(state.phase, state.phase)
        parts.append(phase_display)

        # Turn info (skip during initial flip - it's misleading)
        if state.current_player_id and state.players and state.phase != "initial_flip":
            if state.current_player_id == self._player_id:
                parts.append("[bold white on #2e7d32] YOUR TURN [/bold white on #2e7d32]")
            else:
                for p in state.players:
                    if p.id == state.current_player_id:
                        parts.append(f"[white on #555555] {p.name}'s Turn [/white on #555555]")
                        break

        # Finisher indicator
        if state.finisher_id:
            for p in state.players:
                if p.id == state.finisher_id:
                    parts.append(f"[bold white on #b8860b] {p.name} finished! [/bold white on #b8860b]")
                    break

        # Active rules
        if state.active_rules:
            parts.append(f"Rules: {', '.join(state.active_rules)}")

        text = " │ ".join(parts)
        if self._extra:
            text += f"  {self._extra}"

        self.update(text)
