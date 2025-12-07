"""Central CSS definitions for zen-portal design system."""

# Modal base styles - all modals inherit these
MODAL_CSS = """
/* Modal base positioning */
.modal-base {
    align: center middle;
}

/* Dialog container base - truly elastic height */
.modal-base #dialog {
    height: auto;
    max-height: 90%;
    padding: 1 2;
    background: $surface;
    border: round $surface-lighten-1;
    overflow-y: auto;
}

/* Modal size variants - responsive with min/max bounds */
.modal-sm #dialog {
    width: 50vw;
    min-width: 40;
    max-width: 50;
}

.modal-md #dialog {
    width: 60vw;
    min-width: 50;
    max-width: 65;
}

.modal-lg #dialog {
    width: 70vw;
    min-width: 60;
    max-width: 80;
}

.modal-xl #dialog {
    width: 80vw;
    min-width: 70;
    max-width: 90;
}
"""

# Elastic container system for proper content-based sizing
CONTAINER_CSS = """
/* Elastic containers shrink to fit content */
.elastic {
    height: auto;
    min-height: 0;
}

/* Hidden containers take no space */
.hidden {
    display: none;
}

/* Collapsible contents - elastic by default */
Collapsible Contents {
    height: auto;
    min-height: 0;
}

/* Vertical containers inside collapsibles */
Collapsible Vertical {
    height: auto;
    min-height: 0;
}
"""

# Common UI patterns shared across components
COMMON_CSS = """
/* Dialog title - centered, muted */
.dialog-title {
    text-align: center;
    width: 100%;
    margin-bottom: 1;
    color: $text-muted;
}

/* Field labels - consistent spacing */
.field-label {
    margin-top: 1;
    color: $text-disabled;
}

/* Dialog hint text - bottom of modals */
.dialog-hint {
    text-align: center;
    color: $text-disabled;
    margin-top: 1;
}

/* List containers - viewport-relative heights */
.list-container {
    height: auto;
    padding: 0;
    overflow-y: auto;
}

.list-sm {
    max-height: 20vh;
    min-height: 5;
}

.list-md {
    max-height: 30vh;
    min-height: 8;
}

.list-lg {
    max-height: 50vh;
    min-height: 12;
}

/* Standard list row styling */
.list-row {
    height: 1;
    padding: 0 1;
}

.list-row:hover {
    background: $surface-lighten-1;
}

.list-row.selected {
    background: $surface-lighten-1;
}

/* Empty list placeholder */
.empty-list {
    color: $text-disabled;
    padding: 2;
    text-align: center;
}
"""

# Notification styles - zen minimalism
NOTIFICATION_CSS = """
/* Notification rack - full width container, content aligned right */
ZenNotificationRack {
    height: auto;
    width: 100%;
    align-horizontal: right;
}

/* Base notification styling */
ZenNotification {
    width: auto;
    height: 3;
    padding: 0 2;
    margin-right: 1;
    content-align: center middle;
    text-align: center;
    background: $surface;
    border: round $surface-lighten-1;
    color: $text-muted;
}

/* Severity variants */
ZenNotification.-success {
    border: round $surface-lighten-1;
    color: $text-muted;
}

ZenNotification.-warning {
    border: round $warning-darken-2;
    color: $warning;
}

ZenNotification.-error {
    border: round $error-darken-2;
    color: $error;
}

/* Fade animation */
ZenNotification {
    opacity: 1;
}

ZenNotification.-dismissing {
    opacity: 0;
}
"""

# Command palette - zen styling
COMMAND_PALETTE_CSS = """
/* Zen command palette - minimal chrome */
CommandPalette {
    background: $surface;
    border: round $surface-lighten-1;
}

CommandPalette > Input {
    background: $surface;
    border: none;
    padding: 0 1;
}

CommandPalette > Vertical > OptionList {
    background: $surface;
    border: none;
}

CommandPalette > Vertical > OptionList > .option-list--option-highlighted {
    background: $surface-lighten-1;
}

CommandPalette > Vertical > OptionList > .option-list--option {
    padding: 0 1;
}
"""

# Combined base CSS for import
BASE_CSS = MODAL_CSS + CONTAINER_CSS + COMMON_CSS + NOTIFICATION_CSS + COMMAND_PALETTE_CSS
