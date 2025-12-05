"""Help screen - multi-page zen-inspired documentation.

Page 1: Quick reference (keyboard shortcuts)
Page 2: Session lifecycle and worktrees
Page 3: Tips and advanced usage
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static


# Page 1: Quick reference
# Note: Use \[ to escape brackets so Rich doesn't interpret them as markup tags
PAGE_1 = """

                              zen portal

               a contemplative space for Claude Code


      navigate                        sessions

      k / up     move up              n        new session
      j / down   move down            o        attach existing
      r          refresh              p        pause
      s          stream               x        kill
      ^i         info mode            d        clean
                                      v        revive
      attach                          w        worktree (session)
                                      W        worktrees (all)
      a          attach tmux          i        insert

      other

      c          config               states
      ?          help
      q          quit                 ●  active     ○  complete
                                      ◐  paused     ·  ended


                            \\[1/3]  n:next  p:prev  q:close"""


# Page 2: Session lifecycle and worktrees
# Note: Use \[ to escape brackets so Rich doesn't interpret them as markup tags
PAGE_2 = """

                         session lifecycle


      creating sessions

      Press \\[n] to create a new session. Choose:
        - Claude session: starts Claude Code in a tmux pane
        - Shell session: starts a plain shell

      Sessions can use git worktrees for isolated development.


      ending sessions

      \\[p] Pause    Ends tmux but PRESERVES the worktree.
                   Code changes remain on disk.

      \\[x] Kill     Ends tmux and REMOVES the worktree.
                   Use when done with the branch.


      working with worktrees

      \\[w]          Opens shell in the selected session's worktree.
                   Use to continue working on paused code.

      \\[W]          Browse ALL worktrees in your repository.
                   Open shells or delete worktrees directly.

      \\[v] Revive   Restarts Claude, resuming the conversation.

      \\[d] Clean    Removes session from list and deletes worktree.


                            \\[2/3]  n:next  p:prev  q:close"""


# Page 3: Tips and advanced usage
# Note: Use \[ to escape brackets so Rich doesn't interpret [s] as strikethrough, [i] as italic
PAGE_3 = """

                         tips & advanced usage


      the new session dialog \\[n]

      Three tabs for different session creation modes:
        new      Create fresh Claude or shell session
        attach   Adopt an existing external tmux session
        resume   Continue a previous Claude conversation

      Directory browser: press \\[f] to focus, h/j/k/l to navigate.


      view modes

      \\[r]  Refresh output/info panel
      \\[s]  Toggle streaming (auto-refresh)
      \\[^i] Toggle info mode (show session metadata)


      insert & attach

      \\[i] Send keys to active session without attaching.
      \\[a] Leave zen portal and attach directly to tmux.
      \\[o] Quick attach - directly opens attach modal.


                            \\[3/3]  n:next  p:prev  q:close"""


PAGES = [PAGE_1, PAGE_2, PAGE_3]


class HelpScreen(ModalScreen):
    """Multi-page help overlay."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen > Static {
        width: 70;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $surface-lighten-1;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
        ("space", "next_page", "Next"),
        ("n", "next_page", "Next"),
        ("p", "prev_page", "Prev"),
        ("b", "prev_page", "Prev"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._page_index = 0

    def compose(self) -> ComposeResult:
        yield Static(PAGES[self._page_index], id="help-content")

    def _update_page(self) -> None:
        """Update displayed page."""
        content = self.query_one("#help-content", Static)
        content.update(PAGES[self._page_index])

    def action_close(self) -> None:
        self.dismiss()

    def action_next_page(self) -> None:
        if self._page_index < len(PAGES) - 1:
            self._page_index += 1
            self._update_page()

    def action_prev_page(self) -> None:
        if self._page_index > 0:
            self._page_index -= 1
            self._update_page()

    def on_key(self, event) -> None:
        """Handle generic keys that aren't bound."""
        # Let bound keys work normally
        if event.key in ("escape", "q", "space", "n", "p", "b"):
            return
        # Any other key cycles to next page, or closes on last page
        if self._page_index < len(PAGES) - 1:
            self._page_index += 1
            self._update_page()
            event.stop()
        else:
            self.dismiss()
