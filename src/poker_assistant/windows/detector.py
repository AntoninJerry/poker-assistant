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


def main() -> None:
    """Test script for window detection."""
    print("🔍 Recherche de fenêtres poker...")
    
    # Lister toutes les fenêtres visibles pour debug
    print("\n📋 Toutes les fenêtres visibles:")
    for i, win in enumerate(pwc.getAllWindows()):
        title = win.title or "<sans titre>"
        try:
            x, y, w, h = win.getClientFrame()
            print(f"{i+1:2d}. {title[:50]:<50} | {w}x{h}")
        except Exception:
            print(f"{i+1:2d}. {title[:50]:<50} | [erreur géométrie]")
    
    # Tester la détection
    result = select_best_poker_window()
    
    if result:
        print(f"\n✅ Fenêtre poker détectée:")
        print(f"   Position: {result.left}, {result.top}")
        print(f"   Taille: {result.width}x{result.height}")
        print(f"   Ratio: {result.width/result.height:.2f}")
    else:
        print("\n❌ Aucune fenêtre poker détectée")
        print("💡 Assurez-vous qu'une fenêtre Winamax/PMU/Poker est ouverte")


if __name__ == "__main__":
    main()