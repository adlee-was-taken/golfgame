"""Scoreboard overlay for round/game over."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static


class ScoreboardScreen(ModalScreen[str]):
    """Modal overlay showing round or game scores."""

    def __init__(
        self,
        scores: list[dict],
        title: str = "Round Over",
        is_game_over: bool = False,
        is_host: bool = False,
        round_num: int = 1,
        total_rounds: int = 1,
    ):
        super().__init__()
        self._scores = scores
        self._title = title
        self._is_game_over = is_game_over
        self._is_host = is_host
        self._round_num = round_num
        self._total_rounds = total_rounds

    def compose(self) -> ComposeResult:
        with Container(id="scoreboard-container"):
            yield Static(self._title, id="scoreboard-title")
            yield DataTable(id="scoreboard-table")
            with Horizontal(id="scoreboard-buttons"):
                if self._is_game_over:
                    yield Button("Back to Lobby", id="btn-lobby", variant="primary")
                elif self._is_host:
                    yield Button("Next Round", id="btn-next-round", variant="primary")
                else:
                    yield Button("Waiting for host...", id="btn-waiting", disabled=True)

    def on_mount(self) -> None:
        table = self.query_one("#scoreboard-table", DataTable)

        if self._is_game_over:
            table.add_columns("Rank", "Player", "Total", "Rounds Won")
            for i, s in enumerate(self._scores, 1):
                table.add_row(
                    str(i),
                    s.get("name", "?"),
                    str(s.get("total", 0)),
                    str(s.get("rounds_won", 0)),
                )
        else:
            table.add_columns("Player", "Round Score", "Total", "Rounds Won")
            for s in self._scores:
                table.add_row(
                    s.get("name", "?"),
                    str(s.get("score", 0)),
                    str(s.get("total", 0)),
                    str(s.get("rounds_won", 0)),
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next-round":
            self.dismiss("next_round")
        elif event.button.id == "btn-lobby":
            self.dismiss("lobby")
