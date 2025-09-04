"""Poker table window detection for Windows.

Uses pywinctl to enumerate windows and select the best poker table client rect,
excluding lobbies and text-heavy UIs.
"""

from dataclasses import dataclass

import pywinctl as pwc

EXCLUDE_KEYWORDS = [
    "lobby",
    "home",
    "accueil",
    "shop",
    "boutique",
    "caisse",
]

INCLUDE_KEYWORDS = ["winamax", "pmu", "poker"]


@dataclass
class ClientRect:
    left: int
    top: int
    width: int
    height: int


def _score_window_title(title: str) -> int:
    t = title.lower()
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return -100
    score = 0
    for k in INCLUDE_KEYWORDS:
        if k in t:
            score += 10
    return score


def _get_client_rect(win: pwc.Window) -> ClientRect | None:
    try:
        # pywinctl provides client area geometry via getClientFrame()
        x, y, w, h = win.getClientFrame()
        if w <= 0 or h <= 0:
            return None
        return ClientRect(left=int(x), top=int(y), width=int(w), height=int(h))
    except Exception:
        return None


def select_best_poker_window() -> ClientRect | None:
    """Return client rect of the best matching poker table window, if any."""
    best_score = -9999
    best_rect: ClientRect | None = None

    for win in pwc.getAllWindows():
        title = win.title or ""
        score = _score_window_title(title)
        if score <= 0:
            continue
        rect = _get_client_rect(win)
        if rect is None:
            continue

        # Heuristic: prefer 16:9-ish sizes and mid-to-large areas
        aspect = rect.width / max(rect.height, 1)
        if 1.2 <= aspect <= 2.0:
            score += 2
        if rect.width * rect.height > 400 * 400:
            score += 2

        if score > best_score:
            best_score = score
            best_rect = rect

    return best_rect
