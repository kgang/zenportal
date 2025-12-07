"""Help screen - multi-page zen-inspired documentation.

Page 1: Quick reference (keyboard shortcuts)
Page 2: Session lifecycle and worktrees
Page 3: Tips and advanced usage
"""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


# Page 1: Quick reference
# Note: Use \[ to escape brackets so Rich doesn't interpret them as markup tags
PAGE_1 = """

                              zen portal

              a contemplative space for AI sessions


      navigation                      sessions

      j / k      up / down            n        new
      h / l      left / right         p        pause
      f          focus / expand       x        kill
      r          refresh              d        clean
      s          stream               v        revive
      ^i         info mode            e        rename

      attach                          worktrees

      a          attach tmux          w        open worktree
      o          attach existing      W        view all


      other                           states

      c          config               ●  active     ○  complete
      ?          help                 ◐  paused     ·  ended
      q          quit


                              \\[1/3]  n:next  q:close"""


# Page 2: Session lifecycle and worktrees
# Note: Use \[ to escape brackets so Rich doesn't interpret them as markup tags
PAGE_2 = """

                           session lifecycle


      creating

      \\[n]  new session
           Choose type: Claude, Codex, Gemini, or Shell
           Sessions can use git worktrees for isolation


      ending

      \\[p]  pause     stop session, keep worktree
      \\[x]  kill      stop session, remove worktree
      \\[d]  clean     remove from list


      continuing

      \\[v]  revive    restart session in same worktree
      \\[w]  worktree  open shell in session's worktree


      worktrees

      \\[W]  view all worktrees in repository
           Create shells or delete from list


                              \\[2/3]  n:next  q:close"""


# Page 3: Tips and advanced usage
# Note: Use \[ to escape brackets so Rich doesn't interpret [s] as strikethrough, [i] as italic
PAGE_3 = """

                             tips & tricks


      new session \\[n]

      new       create fresh session
      attach    adopt existing tmux session
      resume    continue Claude conversation

      Use ^t to switch tabs, j/k to navigate lists


      view modes

      \\[r]   refresh output
      \\[s]   toggle auto-refresh (streaming)
      \\[^i]  toggle info mode


      interaction

      \\[i]   send keys to session (without attaching)
      \\[a]   attach to tmux directly
      \\[e]   rename session


                              \\[3/3]  q:close"""


PAGES = [PAGE_1, PAGE_2, PAGE_3]


class HelpScreen(ModalScreen):
    """Multi-page help overlay."""

    DEFAULT_CSS = """
    /* Component-specific: help content styling */
    HelpScreen #help-content {
        color: $text-muted;
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
        self.add_class("modal-base", "modal-md")
        with Vertical(id="dialog"):
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
