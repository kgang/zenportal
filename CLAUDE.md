- Keep files under 500 lines
- Split large modules into `core/` subdirectories
- Progressive disclosure: essential code first, details extracted

## Widget ID Rules (Prevent DuplicateIds Errors)

**NEVER** use `id=` for widgets that are dynamically mounted in methods called multiple times.

✅ **CORRECT** - Use CSS classes for dynamic widgets:
```python
def _update_list(self):
    container.remove_children()
    if not items:
        container.mount(Static("no items", classes="empty-list"))  # ✓ classes
    for i, item in enumerate(items):
        container.mount(Item(item, id=f"item-{i}"))  # ✓ unique per iteration
```

❌ **WRONG** - Static IDs cause duplicates:
```python
def _update_list(self):
    container.remove_children()
    if not items:
        container.mount(Static("no items", id="empty-list"))  # ✗ reused ID!
```

**When to use `id=` vs `classes=`:**
- `id=` - Unique widgets mounted once (in `compose()` only)
- `classes=` - Reusable widgets or anything mounted in update/refresh methods
- Dynamic lists - Use `id=f"prefix-{i}"` with loop index for uniqueness
