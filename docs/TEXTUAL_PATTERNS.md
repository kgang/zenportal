# Textual Patterns Reference

Quick reference for the Textual patterns used in Zen Portal.

## App Structure

```python
from textual.app import App, ComposeResult
from textual.binding import Binding

class ZenPortal(App):
    TITLE = "Zen Portal"
    CSS = """..."""           # Inline TCSS
    COMMANDS = {ZenCommands}  # Command palette providers
    BINDINGS = [...]          # Global key bindings

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("content")
        yield Footer()
```

## Modal Screens

```python
from textual.screen import ModalScreen

class HelpScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        yield Static(HELP_TEXT)

    def on_key(self, event) -> None:
        self.dismiss()  # Any key closes
```

### Modal with Return Value

```python
class AIPromptScreen(ModalScreen[str | None]):
    def _plant_seed(self) -> None:
        self.dismiss(plant.id)  # Return value to caller

    def key_escape(self) -> None:
        self.dismiss(None)  # Cancel
```

## Widgets

### Static with Custom Render

```python
class StatusBar(Static):
    def render(self) -> str:
        return f"{self.duration}m"
```

### Reactive Properties

```python
from textual.reactive import reactive

class StatusBar(Static):
    duration = reactive(0)

    def render(self) -> str:
        return f"{self.duration}m"  # Auto-rerenders on change
```

## Actions

### Binding to Action

```python
BINDINGS = [
    ("r", "request_reflection", "Reflect"),
    Binding("ctrl+a", "ai_prompt", "AI"),
]

def action_request_reflection(self) -> None:
    ...

def action_ai_prompt(self) -> None:
    ...
```

## Command Palette

```python
from textual.command import Provider, Hit, Hits

class ZenCommands(Provider):
    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, description, callback in commands:
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, name, callback, help=description)
```

## Notifications

```python
self.notify("message", timeout=5)
self.notify("warning", severity="warning")
self.notify("info", severity="information")
```

## CSS Variables

Textual provides design tokens:

```css
$background         /* App background */
$surface            /* Elevated surfaces */
$primary            /* Primary accent */
$text               /* Primary text */
$text-muted         /* Secondary text */
```
