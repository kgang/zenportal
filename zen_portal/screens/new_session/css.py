"""CSS styles for NewSessionModal."""

NEW_SESSION_CSS = """
/* Component-specific: tabs and form layout */
NewSessionModal TabbedContent {
    height: auto;
    min-height: 0;
}

NewSessionModal TabPane {
    padding: 1 0;
    height: auto;
    min-height: 0;
}

NewSessionModal .field-input {
    width: 100%;
    margin-bottom: 0;
}

NewSessionModal #type-select, #model-select {
    width: 100%;
}

NewSessionModal #options-row {
    width: 100%;
    height: auto;
    margin-top: 1;
}

NewSessionModal .list-container {
    height: auto;
    max-height: 30vh;
    min-height: 8;
    padding: 0;
    overflow-y: auto;
}

NewSessionModal #advanced-config {
    margin-top: 1;
    height: auto;
}

NewSessionModal #advanced-config CollapsibleTitle {
    padding: 0 1;
    color: $text-disabled;
}

NewSessionModal #advanced-config Contents {
    height: auto;
    min-height: 0;
    padding: 0;
}

NewSessionModal #advanced-config Vertical {
    height: auto;
    min-height: 0;
}

NewSessionModal #default-dir-row {
    height: auto;
}

NewSessionModal #dir-path-row {
    width: 100%;
    height: auto;
}

NewSessionModal #dir-path-input {
    width: 1fr;
}

NewSessionModal #browse-btn {
    width: auto;
    min-width: 8;
    margin-left: 1;
}

NewSessionModal #dir-browser {
    display: none;
    margin-top: 1;
}

NewSessionModal #dir-browser.visible {
    display: block;
}

NewSessionModal Select.hidden {
    display: none;
}

NewSessionModal #shell-options {
    margin-top: 1;
    height: auto;
}

NewSessionModal #shell-options.hidden {
    display: none;
}

NewSessionModal #billing-section {
    margin-top: 0;
    height: auto;
    min-height: 0;
}

NewSessionModal #billing-section.hidden {
    display: none;
}

NewSessionModal #proxy-config {
    height: auto;
    min-height: 0;
    margin-top: 1;
}

NewSessionModal #proxy-config.hidden {
    display: none;
    height: 0;
}

NewSessionModal .proxy-row {
    width: 100%;
    height: auto;
    min-height: 0;
    margin-bottom: 1;
}

NewSessionModal .proxy-label {
    color: $text-muted;
    height: 1;
}

NewSessionModal .proxy-input {
    width: 100%;
}

NewSessionModal .proxy-status {
    height: 1;
    margin-top: 1;
}

NewSessionModal .proxy-status-ok {
    color: $success;
}

NewSessionModal .proxy-status-warning {
    color: $warning;
}

NewSessionModal .proxy-status-error {
    color: $error;
}

NewSessionModal .proxy-hint {
    color: $text-disabled;
    height: auto;
}

NewSessionModal ModelSelector {
    width: 100%;
    margin-bottom: 0;
}

NewSessionModal ModelSelector #model-input {
    border: tall $surface-lighten-1;
}

NewSessionModal ModelSelector #dropdown {
    border: round $surface-lighten-1;
    background: $surface;
}

NewSessionModal #conflict-hint {
    height: 1;
    color: $text-disabled;
    margin-top: 0;
}

NewSessionModal #conflict-hint.warning {
    color: $warning;
}

NewSessionModal #conflict-hint.error {
    color: $error;
}
"""
