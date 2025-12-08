"""Fuzzy matching utility for command palette.

Simple, focused fuzzy matching with scoring:
- Exact match: highest score
- Prefix match: high score
- Contains match: medium score
- Fuzzy (subsequence) match: scored by gaps
"""

from __future__ import annotations


def fuzzy_match(query: str, text: str) -> tuple[bool, int]:
    """Check if query fuzzy-matches text and return score.

    Returns:
        (matches, score) - Higher score = better match.
        Score of 0 means no match.
    """
    if not query:
        return True, 0

    query_lower = query.lower()
    text_lower = text.lower()

    # Exact match - highest priority
    if query_lower == text_lower:
        return True, 10000

    # Prefix match - high priority
    if text_lower.startswith(query_lower):
        return True, 5000 + len(query)

    # Word boundary match - medium-high priority
    words = text_lower.split()
    for word in words:
        if word.startswith(query_lower):
            return True, 3000 + len(query)

    # Contains match - medium priority
    if query_lower in text_lower:
        # Earlier position = higher score
        pos = text_lower.index(query_lower)
        return True, 2000 - pos

    # Fuzzy subsequence match
    score = _subsequence_score(query_lower, text_lower)
    if score > 0:
        return True, score

    return False, 0


def _subsequence_score(query: str, text: str) -> int:
    """Score a fuzzy subsequence match.

    Characters must appear in order but not consecutively.
    Consecutive matches score higher.
    """
    if not query:
        return 1000

    query_idx = 0
    consecutive = 0
    score = 0
    last_match_idx = -2  # -2 so first match isn't "consecutive"

    for i, char in enumerate(text):
        if query_idx < len(query) and char == query[query_idx]:
            # Match found
            if i == last_match_idx + 1:
                consecutive += 1
                score += 10 * consecutive  # Bonus for consecutive
            else:
                consecutive = 0
                score += 1

            last_match_idx = i
            query_idx += 1

    # All query chars matched?
    if query_idx == len(query):
        return 500 + score
    return 0


def rank_commands(query: str, items: list[tuple[str, str]]) -> list[tuple[str, str, int]]:
    """Rank items by fuzzy match quality.

    Args:
        query: Search string
        items: List of (id, label) tuples

    Returns:
        List of (id, label, score) sorted by score descending.
        Only includes matching items.
    """
    if not query:
        # No query = return all with neutral score
        return [(id_, label, 0) for id_, label in items]

    results: list[tuple[str, str, int]] = []
    for id_, label in items:
        matches, score = fuzzy_match(query, label)
        if matches and score > 0:
            results.append((id_, label, score))

    # Sort by score descending, then alphabetically
    results.sort(key=lambda x: (-x[2], x[1].lower()))
    return results
