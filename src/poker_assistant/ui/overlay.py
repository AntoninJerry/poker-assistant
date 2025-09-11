# -*- coding: utf-8 -*-
import sys
import time
import threading
import ctypes
from dataclasses import dataclass
from typing import Optional, List, Dict, Protocol, Tuple

import customtkinter as ctk

# === Modèle d'état (on réutilise ton modèle si déjà présent) ==================
try:
    # Si ton modèle existe déjà, on l'importe.
    from poker_assistant.state.model import HandState, Street  # type: ignore
except Exception:
    # Sinon, on met un mini fallback pour que l'UI fonctionne.
    Street = str  # type: ignore

    @dataclass
    class HandState:
        street: Street
        hero_cards: List[str]
        board: List[str]
        pot: Optional[float]
        to_call: Optional[float]
        hero_stack: Optional[float]
        bb: float
        hero_name: Optional[str] = None
        history: List[Dict] = None
        ts_ms: Optional[int] = None

# === Interface du fournisseur de données ======================================
class HUDDataProvider(Protocol):
    def ready(self) -> bool: ...
    def get_state(self) -> Optional[HandState]: ...
    def get_policy(self, state: HandState) -> Dict: ...

# === Mini utilitaires d'affichage =============================================
SUIT_MAP = {"h": "♥", "d": "♦", "c": "♣", "s": "♠"}

def pretty_card(c: str) -> str:
    if not c or c == "??" or len(c) < 2:
        return "??"
    r, s = c[0], c[1].lower()
    return f"{r}{SUIT_MAP.get(s, s)}"

def join_cards(arr: List[str]) -> str:
    return " ".join(pretty_card(c) for c in arr if c and c != "??")

def fmt_money(x: Optional[float]) -> str:
    if x is None: return "—"
    if x >= 1000: return f"{x/1000:.1f}k"
    return f"{x:.2f}"

# === Composants UI =============================================================
class LoadingSpinner(ctk.CTkLabel):
    FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    def __init__(self, master, text="Initialisation…", **kw):
        super().__init__(master, text="", **kw)
        self._idx = 0
        self._label = ctk.CTkLabel(master, text=text, font=("Inter", 14))
        self._label.pack(pady=(6,0))
        self._running = False
        self.configure(font=("Inter", 28))

    def start(self):
        self._running = True
        self._animate()

    def stop(self):
        self._running = False

    def _animate(self):
        if not self._running: return
        self._idx = (self._idx + 1) % len(self.FRAMES)
        self.configure(text=self.FRAMES[self._idx])
        self.after(100, self._animate)

class ConfidenceBar(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        ctk.CTkLabel(self, text="Confiance", font=("Inter", 12)).pack(anchor="w")
        self._bar = ctk.CTkProgressBar(self, width=220, height=10)
        self._bar.set(0.0)
        self._bar.pack(fill="x", pady=(2,0))

    def set(self, conf: float):
        conf = max(0.0, min(1.0, conf or 0.0))
        self._bar.set(conf)

class StatusPill(ctk.CTkLabel):
    def set(self, text: str, conf: float):
        # couleur selon confiance
        if conf >= 0.75: color = ("#1f6f43", "#1f6f43")   # vert
        elif conf >= 0.5: color = ("#8a6d1e", "#8a6d1e") # ambre
        else: color = ("#7a1f1f", "#7a1f1f")             # rouge
        self.configure(text=text, fg_color=color, corner_radius=999, padx=10, pady=4)

# === Fenêtre HUD ===============================================================
class PokerHUD(ctk.CTk):
    """HUD overlay discret, draggable, top-most, avec animation de chargement."""
    def __init__(self, provider: HUDDataProvider, title: str = "Poker HUD", alpha: float = 0.92):
        super().__init__()
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("dark-blue")

        self.title(title)
        self.geometry("+80+80")
        self.overrideredirect(True)   # frameless
        self.wm_attributes("-topmost", True)
        self.wm_attributes("-alpha", alpha)

        # pour drag
        self._drag = {"x": 0, "y": 0}
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)

        # toggles
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<F8>", self._toggle_visibility)
        self.bind("<F7>", self._toggle_click_through)
        
        # Empêcher la fermeture accidentelle au clic
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._provider = provider
        self._click_through = False
        self._after_id = None
        # Gestion sûre des jobs after()
        self._jobs = set()
        
        def _schedule(delay_ms, fn):
            jid = self.after(delay_ms, fn)
            self._jobs.add(jid)
            return jid
        
        def _cancel_all_jobs():
            for jid in list(self._jobs):
                try:
                    self.after_cancel(jid)
                except Exception:
                    pass
                finally:
                    self._jobs.discard(jid)
        
        # expose helpers
        self._schedule = _schedule
        self._cancel_all_jobs = _cancel_all_jobs
        self._last_seen_ts: float = 0.0

        # ---- Conteneur principal
        self._main_container = ctk.CTkFrame(self, corner_radius=16, border_width=1)
        self._main_container.pack(padx=8, pady=8, fill="both", expand=True)

        # ---- Loading view
        self._loading_frame = ctk.CTkFrame(self._main_container)
        self._loading_spinner = LoadingSpinner(self._loading_frame, text="Initialisation du pipeline…")
        self._loading_spinner.pack(pady=(14, 6))
        ctk.CTkLabel(self._loading_frame, text="Merci de patienter", font=("Inter", 12), text_color="#aaa").pack()
        self._loading_frame.pack(fill="both", expand=True)
        self._loading_spinner.start()

        # ---- Main view (masquée au début)
        self._main = ctk.CTkFrame(self._main_container)
        # header
        self._hdr = ctk.CTkFrame(self._main, fg_color="transparent")
        self._title_lbl = ctk.CTkLabel(self._hdr, text=title, font=("Inter SemiBold", 14))
        self._pill = StatusPill(self._hdr, text="", font=("Inter", 12), corner_radius=999, padx=8, pady=2)
        self._close_btn = ctk.CTkButton(self._hdr, text="×", width=30, height=30, 
                                       command=self._on_close, font=("Inter", 16))
        self._title_lbl.pack(side="left")
        ctk.CTkLabel(self._hdr, text="  ").pack(side="left")
        self._pill.pack(side="left")
        ctk.CTkLabel(self._hdr, text=" " * 2).pack(side="left")
        self._close_btn.pack(side="right")
        self._hdr.pack(fill="x", padx=8, pady=(6, 4))

        # cartes + infos
        self._cards = ctk.CTkFrame(self._main, fg_color="transparent")
        self._hero_lbl = ctk.CTkLabel(self._cards, text="Hero: —", font=("JetBrains Mono", 16))
        self._board_lbl = ctk.CTkLabel(self._cards, text="Board: —", font=("JetBrains Mono", 16))
        self._hero_lbl.pack(anchor="w")
        self._board_lbl.pack(anchor="w", pady=(2,0))
        self._cards.pack(fill="x", padx=8)

        # montants
        self._money = ctk.CTkFrame(self._main, fg_color="transparent")
        self._pot_lbl = ctk.CTkLabel(self._money, text="Pot: —", font=("Inter", 13))
        self._call_lbl = ctk.CTkLabel(self._money, text="À payer: —", font=("Inter", 13))
        self._stack_lbl = ctk.CTkLabel(self._money, text="Stack: —", font=("Inter", 13))
        self._pot_lbl.grid(row=0, column=0, sticky="w", padx=(0,16))
        self._call_lbl.grid(row=0, column=1, sticky="w", padx=(0,16))
        self._stack_lbl.grid(row=0, column=2, sticky="w")
        self._money.pack(fill="x", padx=8, pady=(4,2))

        # action
        self._action = ctk.CTkFrame(self._main, fg_color=("gray12","gray10"), corner_radius=12)
        self._action_lbl = ctk.CTkLabel(self._action, text="—", font=("Inter Bold", 18))
        self._size_lbl = ctk.CTkLabel(self._action, text="", font=("Inter", 14))
        self._bar = ConfidenceBar(self._action)
        self._action_lbl.pack(anchor="w")
        self._size_lbl.pack(anchor="w")
        self._bar.pack(fill="x", pady=(6,2))
        self._action.pack(fill="x", padx=8, pady=(6,8))

        self._main.pack_forget()  # masqué au début

        # boucle de monitoring
        self._poll_provider()
        
        # Empêcher la fermeture automatique - l'utilisateur doit fermer manuellement
        print("🎮 Overlay ouvert - Utilisez Échap pour fermer ou F8 pour basculer la visibilité")

    # ---- Drag window
    def _on_click(self, e):
        self._drag["x"] = e.x
        self._drag["y"] = e.y

    def _on_drag(self, e):
        x = self.winfo_x() + (e.x - self._drag["x"])
        y = self.winfo_y() + (e.y - self._drag["y"])
        self.geometry(f"+{x}+{y}")

    # ---- Visibility & click-through
    def _toggle_visibility(self, *_):
        vis = self.wm_attributes("-alpha")
        self.wm_attributes("-alpha", 0.18 if vis > 0.5 else 0.92)

    def _toggle_click_through(self, *_):
        # Windows only: WS_EX_TRANSPARENT
        try:
            if sys.platform != "win32": return
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            current = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if not self._click_through:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current | WS_EX_LAYERED | WS_EX_TRANSPARENT)
                self._click_through = True
            else:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current & ~WS_EX_TRANSPARENT)
                self._click_through = False
        except Exception:
            pass

    # ---- Provider polling
    def _poll_provider(self):
        try:
            if not self._provider.ready():
                return  # <-- pas d'after ici

            # bascule loading -> main une seule fois
            if self._loading_frame.winfo_ismapped():
                self._loading_spinner.stop()
                self._loading_frame.pack_forget()
                self._main.pack(fill="both", expand=True)

            # 1) snapshot mailbox (non bloquant)
            snap = None
            snap_ts = None
            if hasattr(self._provider, "get_snapshot"):
                try:
                    if hasattr(self._provider, "get_snapshot_with_ts"):
                        snap, snap_ts = self._provider.get_snapshot_with_ts()
                    else:
                        snap = self._provider.get_snapshot()
                except Exception:
                    snap = None

            if snap:
                st = snap.get("state")
                pol = snap.get("policy") or {}
            else:
                st = self._provider.get_state()
                pol = self._provider.get_cached_policy() if hasattr(self._provider, "get_cached_policy") else {}

            if st is not None:
                # Skip render si timestamp identique
                if snap_ts is None:
                    snap_ts = getattr(self._provider, "last_snapshot_ts", None)
                if isinstance(snap_ts, float) and snap_ts == self._last_seen_ts:
                    return
                if isinstance(snap_ts, float):
                    self._last_seen_ts = snap_ts
                self._render(st, pol)
        except Exception as e:
            print(f"⚠️ Erreur polling HUD: {e}")
        finally:
            # ✅ un seul after planifié par tick
            try:
                self._after_id = self._schedule(120, self._poll_provider)
            except Exception:
                pass

    # ---- Rendering
    def _render(self, st: HandState, pol: Dict):
        # Debug: afficher ce qui est reçu
        print(f"🎨 Rendu HUD - Hero: {st.hero_cards}, Board: {st.board}, Policy: {pol}")
        
        # cartes
        hero_text = join_cards(st.hero_cards or [])
        board_text = join_cards(st.board or [])
        self._hero_lbl.configure(text=f"Hero: {hero_text}")
        self._board_lbl.configure(text=f"Board: {board_text}")

        # montants
        self._pot_lbl.configure(text=f"Pot: {fmt_money(st.pot)}")
        self._call_lbl.configure(text=f"À payer: {fmt_money(st.to_call)}")
        self._stack_lbl.configure(text=f"Stack: {fmt_money(st.hero_stack)}")

        # action
        action = (pol.get("action") or "—").upper()
        conf   = float(pol.get("confidence") or 0.0)
        size   = pol.get("size_bb")
        reason = pol.get("reason") or ""

        pill_text = f"{self._street_text(st)} • {st.hero_name or '—'}"
        self._pill.set(pill_text, conf)

        if action == "RAISE" and size:
            self._action_lbl.configure(text="RAISE")
            self._size_lbl.configure(text=f"{size:.1f} bb  •  {reason}")
        else:
            self._action_lbl.configure(text=action)
            self._size_lbl.configure(text=reason)
        self._bar.set(conf)
    
    def _street_text(self, st: "HandState") -> str:
        try:
            v = st.street
            if v is None:
                return "—"
            # Enum ? -> .value ; sinon str
            s = v.value if hasattr(v, "value") else str(v)
            return s.upper()
        except Exception:
            return "—"
    
    def _on_close(self):
        """Gestion propre de la fermeture."""
        try:
            if self._after_id is not None:
                self.after_cancel(self._after_id)
            # Annule tous les jobs planifiés
            self._cancel_all_jobs()
        except Exception:
            pass
        print("👋 Fermeture de l'overlay HUD")
        self.destroy()
