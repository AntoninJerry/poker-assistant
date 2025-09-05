"""Window detector for poker tables using pygetwindow (stable)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import pygetwindow as gw
except ImportError:
    # Fallback to pywinctl if pygetwindow not available
    import pywinctl as gw


@dataclass
class CandidateWindow:
    handle: int
    title: str
    process: str
    bbox: Tuple[int, int, int, int]  # (left, top, right, bottom)
    room_guess: Optional[str]
    score: float  # score global de confiance [0..1]


# Config de filtrage
WHITELIST_PROCESS_SUBSTR = ("winamax", "pmu")
WHITELIST_TITLE_SUBSTR = ("table", "winamax", "pmu")
BLACKLIST_TITLE_SUBSTR = (
    # Lobby/Home
    "lobby",
    "home", 
    "accueil",
    "main",
    "principal",
    
    # Cashier/Shop
    "cashier",
    "caisse",
    "shop",
    "boutique",
    "store",
    "magasin",
    
    # Settings
    "réglages",
    "paramètres",
    "settings",
    "preferences",
    "préférences",
    "config",
    "configuration",
    
    # Tournament types (not cash tables)
    "tournoi",
    "tournament",
    "sng",
    "sit & go",
    "spin & go",
    "zoom",
    "fast",
    "speed",
    "mtt",
    "multi-table",
    "satellite",
    "qualifier",
    "qualification",
    "freeroll",
    "freerolls",
    
    # UI elements
    "leaderboard",
    "classement",
    "ranking",
    "stats",
    "statistiques",
    "history",
    "historique",
    "notes",
    "chat",
    "messages",
    "support",
    "aide",
    "help",
    "faq",
    "rules",
    "règles",
    "terms",
    "conditions",
    "privacy",
    "confidentialité",
    "about",
    "à propos",
    
    # System dialogs
    "dialog",
    "dialogue",
    "popup",
    "modal",
    "alert",
    "warning",
    "error",
    "erreur",
    "info",
    "information",
    "confirm",
    "confirmation",
    
    # Development tools
    "editor",
    "code",
    "pycharm",
    "visual studio",
    "vscode",
    "sublime",
    "atom",
    "notepad",
    "notepad++",
)


def _norm(s: str) -> str:
    """Normalize string for comparison."""
    return s.lower().strip() if s else ""


def detect_poker_tables(room_preference: Optional[str] = None) -> List[CandidateWindow]:
    """
    Detect poker table windows using pygetwindow.
    Returns list of candidate windows sorted by score (descending).
    """
    candidates: List[CandidateWindow] = []
    
    # Get all windows (compatible with both pygetwindow and pywinctl)
    try:
        windows = gw.getAllWindows()
    except AttributeError:
        # pywinctl uses different method
        windows = gw.getAllWindows()
    
    for window in windows:
        try:
            title = window.title or ""
            proc_name = ""
            
            # Try to get process name from title or window object
            if hasattr(window, '_hWnd'):
                try:
                    import psutil
                    import win32process
                    _, pid = win32process.GetWindowThreadProcessId(window._hWnd)
                    proc = psutil.Process(pid)
                    proc_name = proc.name()
                except:
                    # Fallback: extract from title or use empty
                    proc_name = ""
            elif hasattr(window, 'getAppName'):
                # pywinctl method
                try:
                    proc_name = window.getAppName() or ""
                except:
                    proc_name = ""
            
            title_norm = _norm(title)
            proc_norm = _norm(proc_name)
            
            # Check whitelist
            proc_match = any(p in proc_norm for p in WHITELIST_PROCESS_SUBSTR)
            title_match = any(t in title_norm for t in WHITELIST_TITLE_SUBSTR)
            
            if not proc_match and not title_match:
                continue
                
            # Check blacklist
            if any(b in title_norm for b in BLACKLIST_TITLE_SUBSTR):
                continue
            
            # Check size
            width = window.width
            height = window.height
            if width < 400 or height < 300:
                continue
            
            # Determine room guess
            if "winamax" in proc_norm or "winamax" in title_norm:
                room_guess = "winamax"
                room_score = 0.8
            elif "pmu" in proc_norm or "pmu" in title_norm:
                room_guess = "pmu" 
                room_score = 0.8
            else:
                room_guess = None
                room_score = 0.0
            
            # Apply room preference penalty
            if room_preference and room_guess and room_guess != room_preference:
                room_score *= 0.6
            
            # Calculate final score with better table detection
            base_score = 0.3
            
            # Bonus for table-related keywords
            table_keywords = ("table", "cash", "ring", "hold'em", "holdem", "texas", "omaha", "poker")
            table_bonus = 0.3 if any(t in title_norm for t in table_keywords) else 0.0
            
            # Bonus for process match
            proc_bonus = 0.2 if proc_match else 0.0
            
            # Bonus for room match
            room_bonus = 0.2 * room_score
            
            # Penalty for suspicious titles (lobby-like)
            lobby_keywords = ("lobby", "home", "accueil", "main", "principal", "tournoi", "tournament")
            lobby_penalty = -0.4 if any(l in title_norm for l in lobby_keywords) else 0.0
            
            # Size bonus (tables are usually larger)
            size_bonus = 0.1 if width > 800 and height > 600 else 0.0
            
            score = max(0.0, min(1.0, base_score + table_bonus + proc_bonus + room_bonus + lobby_penalty + size_bonus))
            
            # Create candidate (compatible with both libraries)
            handle = 0
            if hasattr(window, '_hWnd'):
                handle = window._hWnd
            elif hasattr(window, 'getHandle'):
                handle = window.getHandle()
            
            candidate = CandidateWindow(
                handle=handle,
                title=title,
                process=proc_name,
                bbox=(window.left, window.top, window.left + width, window.top + height),
                room_guess=room_guess,
                score=score,
            )
            
            candidates.append(candidate)
            
        except Exception:
            continue
    
    # Sort by score (descending)
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
