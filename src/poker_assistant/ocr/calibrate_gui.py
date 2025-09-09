# src/poker_assistant/ocr/calibrate_gui.py (v2.1)
# Outil de calibration des zones (ROI) pour tables de poker
# Flux : détection/selection fenêtre -> capture INTÉRIEUR fenêtre -> dessin ROIs -> YAML
# Correctifs majeurs :
#  - PrintWindow d'abord (anti-occlusion). Si non supporté par la room (DirectX/GL),
#    on FORCE l'affichage de la fenêtre cible, on masque temporairement l'outil,
#    puis on capture l'écran recadré (MSS). => fini les captures de l'éditeur.
#  - Bouton "Forcer focus & recapturer" + indicateur du mode de capture utilisé.
#  - Coordonnées normalisées, layouts multiples (ex: history_open pour Winamax).
#
# Dépendances: pillow, pywin32, mss, pyyaml  (opencv-python facultatif)
# pip install pillow pywin32 mss pyyaml

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from PIL import Image, ImageTk, ImageGrab

# --- DPI aware : coordonnées correctes ---
try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

# --- Win32 ---
try:
    import win32gui, win32ui, win32con
except Exception:
    win32gui = None
    win32ui = None
    win32con = None

import mss
import yaml

# Import projet
try:
    from ..windows.detector import CandidateWindow
    from ..ui.room_selector import choose_table
except Exception:
    # fallback si exécuté directement
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from src.poker_assistant.windows.detector import CandidateWindow  # type: ignore
    from src.poker_assistant.ui.room_selector import choose_table  # type: ignore

PKG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROOMS_DIR = os.path.join(PKG_DIR, "rooms")


# -----------------------------
# Données & utilitaires
# -----------------------------

@dataclass
class ROI:
    name: str
    x: float
    y: float
    w: float
    h: float

    def to_yaml(self):
        return {"x": float(self.x), "y": float(self.y), "w": float(self.w), "h": float(self.h)}


PRESET_NAMES: List[str] = [
    # Board
    "board_card1", "board_card2", "board_card3", "board_card4", "board_card5",
    # Hero
    "hero_cards_left", "hero_cards_right", "hero_stack", "hero_name", "hero_action_buttons",
    # Pot & info
    "pot_combined", "hand_number", "room_timer",
    # Villains (exemple 6-max)
    "v1_stack", "v1_name", "v1_bet", "v2_stack", "v2_name", "v2_bet",
    "v3_stack", "v3_name", "v3_bet", "v4_stack", "v4_name", "v4_bet", "v5_stack", "v5_name", "v5_bet",
]


# -----------------------------
# Capture fenêtre : helpers
# -----------------------------

def get_client_rect_on_screen(hwnd: int) -> Tuple[int, int, int, int]:
    """(L,T,R,B) de la zone **client** en coordonnées écran."""
    if not win32gui:
        raise RuntimeError("win32gui indisponible")
    cl = win32gui.GetClientRect(hwnd)
    w = int(cl[2] - cl[0])
    h = int(cl[3] - cl[1])
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    return int(left), int(top), int(left + w), int(top + h)


def try_printwindow_client(hwnd: int) -> tuple[Optional[Image.Image], bool]:
    """Tente PrintWindow sur la zone client. Retourne (image, ok_printwindow)."""
    if not (win32gui and win32ui):
        return None, False
    try:
        L, T, R, B = get_client_rect_on_screen(hwnd)
        W, H = max(1, R - L), max(1, B - T)
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        bmp    = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfcDC, W, H)
        saveDC.SelectObject(bmp)
        # 2 = PW_RENDERFULLCONTENT (si supporté)
        ok = win32gui.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
        bmpinfo = bmp.GetInfo()
        bmpstr  = bmp.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr, "raw", "BGRX", 0, 1
        )
        # cleanup
        win32gui.DeleteObject(bmp.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        return (img if ok == 1 else None), ok == 1
    except Exception:
        return None, False


def ensure_target_visible(hwnd: int):
    """Met la fenêtre cible devant et restaurée pour capture écran fiable."""
    if not (win32gui and win32con):
        return
    try:
        # Restaurer si minimisée
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        # Mettre au premier plan (peut échouer selon focus policy, mais on tente)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        # Légèrement topmost puis non-topmost pour la remonter
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        except Exception:
            pass
    except Exception:
        pass


def grab_bbox_image(bbox: Tuple[int, int, int, int]) -> Image.Image:
    L, T, R, B = map(int, bbox)
    W, H = max(1, R - L), max(1, B - T)
    with mss.mss() as sct:
        raw = sct.grab({"left": L, "top": T, "width": W, "height": H})
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def capture_window_auto(hwnd: int, hide_widget: Optional[tk.Tk] = None) -> tuple[Image.Image, str]:
    """Capture robuste : PrintWindow si possible, sinon écran recadré après avoir forcé la room au premier plan.
    Retourne (image, mode) où mode ∈ {"PrintWindow", "ScreenCrop"}.
    """
    # 1) PrintWindow (anti-occlusion). Certaines rooms ne le supportent pas -> ok=False
    img, ok = try_printwindow_client(hwnd)
    if ok and img is not None:
        return img, "PrintWindow"

    # 2) Fallback: screen crop. On masque l’outil pour éviter le miroir.
    if hide_widget is not None:
        try:
            hide_widget.withdraw()
            hide_widget.update_idletasks()
        except Exception:
            pass
    ensure_target_visible(hwnd)
    time.sleep(0.15)  # petit délai pour que la fenêtre remonte
    try:
        bbox = get_client_rect_on_screen(hwnd)
        img2 = grab_bbox_image(bbox)
    finally:
        if hide_widget is not None:
            try:
                hide_widget.deiconify()
                hide_widget.update_idletasks()
            except Exception:
                pass
    return img2, "ScreenCrop"


# -----------------------------
# Calibrator UI
# -----------------------------

class CalibratorApp(tk.Tk):
    def __init__(self, cand: CandidateWindow):
        super().__init__()
        self.title(f"Calibration ROIs — {cand.room_guess or '?'} — {cand.title}")
        self.geometry("1200x800")

        self.cand = cand
        self.room = cand.room_guess or "room"
        self.layout_name = tk.StringVar(value="default")  # ex: default / history_open
        self.zoom = tk.DoubleVar(value=1.0)
        self.snap = tk.BooleanVar(value=True)  # snap grille 5 px
        self.cap_mode = tk.StringVar(value="?")  # indicateur du mode de capture

        # Capture image client-area (robuste)
        self.base_img = None  # PIL.Image
        self.base_w = 0
        self.base_h = 0
        self._load_image_from_window(first_time=True)

        # Données par layout
        self.layouts: Dict[str, Dict[str, ROI]] = {"default": {}, "history_open": {}}

        # Selection/édition
        self.current_layout_rois: Dict[str, ROI] = self.layouts[self.layout_name.get()]
        self.active_roi_id: Optional[str] = None
        self.drag_start: Optional[Tuple[int, int]] = None
        self.new_rect_preview_id: Optional[int] = None

        self._build_ui()
        self._bind_events()
        self._redraw()

    # ---------- Capture ----------
    def _load_image_from_window(self, first_time: bool = False):
        try:
            if getattr(self.cand, "handle", None):
                img, mode = capture_window_auto(self.cand.handle, hide_widget=self)
                self.cap_mode.set(mode)
            else:
                img = grab_bbox_image(self.cand.bbox)
                self.cap_mode.set("ScreenCrop")
        except Exception:
            img = grab_bbox_image(self.cand.bbox)
            self.cap_mode.set("ScreenCrop")
        self.base_img = img
        self.base_w, self.base_h = img.size

    # ---------- UI construction ----------
    def _build_ui(self):
        # Left: Canvas
        left = ttk.Frame(self)
        left.pack(side="left", fill="both", expand=True)

        toolbar = ttk.Frame(left)
        toolbar.pack(side="top", fill="x")

        ttk.Label(toolbar, text="Layout:").pack(side="left")
        layout_combo = ttk.Combobox(toolbar, values=["default", "history_open"], textvariable=self.layout_name, state="readonly", width=14)
        layout_combo.pack(side="left", padx=6)
        layout_combo.bind("<<ComboboxSelected>>", lambda e: self._on_layout_change())

        ttk.Checkbutton(toolbar, text="Snap 5px", variable=self.snap).pack(side="left", padx=6)

        ttk.Label(toolbar, text="Zoom").pack(side="left")
        zoom_scale = ttk.Scale(toolbar, from_=0.5, to=2.0, variable=self.zoom, command=lambda _=None: self._redraw())
        zoom_scale.pack(side="left", fill="x", expand=True, padx=6)

        refresh_btn = ttk.Button(toolbar, text="Re-capturer fenêtre", command=self._refresh_capture)
        refresh_btn.pack(side="left", padx=6)

        force_btn = ttk.Button(toolbar, text="Forcer focus & recapturer", command=self._force_focus_and_capture)
        force_btn.pack(side="left", padx=6)

        save_btn = ttk.Button(toolbar, text="Enregistrer YAML (Ctrl+S)", command=self._on_save)
        save_btn.pack(side="right")

        # Mode de capture
        ttk.Label(toolbar, textvariable=self.cap_mode).pack(side="right", padx=8)
        ttk.Label(toolbar, text="Mode:").pack(side="right")

        # Canvas image
        self.canvas = tk.Canvas(left, bg="#111")
        self.canvas.pack(fill="both", expand=True)

        # Right: panneau ROIs
        right = ttk.Frame(self)
        right.pack(side="right", fill="y")
        ttk.Label(right, text="ROIs (layout courant)").pack(anchor="w", padx=8, pady=(8, 0))

        self.roi_list = tk.Listbox(right, height=25)
        self.roi_list.pack(fill="y", padx=8, pady=4)
        self.roi_list.bind("<<ListboxSelect>>", lambda e: self._on_list_select())
        self.roi_list.bind("<Double-Button-1>", lambda e: self._rename_selected())

        btns = ttk.Frame(right)
        btns.pack(fill="x", padx=8)
        ttk.Button(btns, text="Renommer", command=self._rename_selected).pack(side="left", expand=True, fill="x")
        ttk.Button(btns, text="Supprimer", command=self._delete_selected).pack(side="left", expand=True, fill="x", padx=6)

        ttk.Label(right, text="Presets").pack(anchor="w", padx=8, pady=(12, 0))
        self.preset_combo = ttk.Combobox(right, values=PRESET_NAMES, state="readonly")
        self.preset_combo.pack(fill="x", padx=8)
        ttk.Label(right, text="(Choisis un preset, puis dessine au canvas)").pack(anchor="w", padx=8)

        ttk.Separator(right).pack(fill="x", padx=8, pady=12)

        ttk.Label(right, text="Aide").pack(anchor="w", padx=8)
        help_txt = (
            "Clic & glisser pour créer un ROI\n"
            "Shift = snap 5px\n"
            "Clique sur un ROI pour le sélectionner\n"
            "Double-clic = renommer\n"
            "Suppr = supprimer\n"
            "Ctrl+S = sauvegarder YAML"
        )
        tk.Message(right, text=help_txt, width=220).pack(anchor="w", padx=8, pady=(0, 12))

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.bind("<Delete>", lambda e: self._delete_selected())
        self.bind("<Control-s>", lambda e: self._on_save())

    # ---------- Layout change ----------
    def _on_layout_change(self):
        name = self.layout_name.get()
        if name not in self.layouts:
            self.layouts[name] = {}
        self.current_layout_rois = self.layouts[name]
        self.active_roi_id = None
        self._refresh_list()
        self._redraw()

    # ---------- Capture refresh ----------
    def _refresh_capture(self):
        self._load_image_from_window()
        self._redraw()

    def _force_focus_and_capture(self):
        # Force explicitement la remontée de la room et recapture
        self._load_image_from_window()
        self._redraw()

    # ---------- Coord helpers ----------
    def _img_to_canvas(self, x: float, y: float) -> Tuple[float, float]:
        s = self.zoom.get()
        return x * s, y * s

    def _canvas_to_img(self, x: float, y: float) -> Tuple[float, float]:
        s = self.zoom.get()
        return x / s, y / s

    def _snap_px(self, v: float) -> float:
        return round(v / 5.0) * 5.0

    # ---------- ROI utils ----------
    def _add_roi(self, name: str, x: float, y: float, w: float, h: float):
        # Normalisation [0..1]
        rx, ry = x / self.base_w, y / self.base_h
        rw, rh = w / self.base_w, h / self.base_h
        self.current_layout_rois[name] = ROI(name, rx, ry, rw, rh)
        self.active_roi_id = name
        self._refresh_list()
        self._redraw()

    def _rename_selected(self):
        sel = self._get_selected_name()
        if not sel:
            return
        new_name = simpledialog.askstring("Renommer ROI", "Nouveau nom:", initialvalue=sel)
        if not new_name or new_name == sel:
            return
        if new_name in self.current_layout_rois:
            messagebox.showerror("Erreur", "Un ROI avec ce nom existe déjà.")
            return
        roi = self.current_layout_rois.pop(sel)
        roi.name = new_name
        self.current_layout_rois[new_name] = roi
        self.active_roi_id = new_name
        self._refresh_list()
        self._redraw()

    def _delete_selected(self):
        sel = self._get_selected_name()
        if not sel:
            return
        self.current_layout_rois.pop(sel, None)
        self.active_roi_id = None
        self._refresh_list()
        self._redraw()

    def _get_selected_name(self) -> Optional[str]:
        try:
            idx = self.roi_list.curselection()
            if not idx:
                return self.active_roi_id
            return self.roi_list.get(idx[0])
        except Exception:
            return self.active_roi_id

    def _refresh_list(self):
        self.roi_list.delete(0, tk.END)
        for name in sorted(self.current_layout_rois.keys()):
            self.roi_list.insert(tk.END, name)
        # Reselection
        if self.active_roi_id:
            try:
                names = list(sorted(self.current_layout_rois.keys()))
                if self.active_roi_id in names:
                    self.roi_list.selection_set(names.index(self.active_roi_id))
            except Exception:
                pass

    def _on_list_select(self):
        sel = self._get_selected_name()
        self.active_roi_id = sel
        self._redraw()

    # ---------- Mouse interactions ----------
    def _on_mouse_down(self, event):
        # Click dans canvas -> selection d'un ROI si on clique dedans, sinon création
        x_img, y_img = self._canvas_to_img(event.x, event.y)
        # selection existante ?
        hit_name = None
        for name, roi in self.current_layout_rois.items():
            rx, ry, rw, rh = roi.x * self.base_w, roi.y * self.base_h, roi.w * self.base_w, roi.h * self.base_h
            if rx <= x_img <= rx + rw and ry <= y_img <= ry + rh:
                hit_name = name
                break
        if hit_name:
            self.active_roi_id = hit_name
            self.drag_start = (int(x_img), int(y_img))
        else:
            self.active_roi_id = None
            self.drag_start = (int(x_img), int(y_img))
            if self.new_rect_preview_id:
                self.canvas.delete(self.new_rect_preview_id)
            self.new_rect_preview_id = None
        self._redraw()

    def _on_mouse_move(self, event):
        if not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = self._canvas_to_img(event.x, event.y)
        if self.snap.get() or (event.state & 0x0001):  # Shift pressed -> snap
            x1, y1 = self._snap_px(x1), self._snap_px(y1)
            x0, y0 = self._snap_px(x0), self._snap_px(y0)
        # prévisualisation
        if self.new_rect_preview_id:
            self.canvas.delete(self.new_rect_preview_id)
        zx0, zy0 = self._img_to_canvas(x0, y0)
        zx1, zy1 = self._img_to_canvas(x1, y1)
        self.new_rect_preview_id = self.canvas.create_rectangle(zx0, zy0, zx1, zy1, outline="red", width=2)

    def _on_mouse_up(self, event):
        if not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = self._canvas_to_img(event.x, event.y)
        if self.snap.get() or (event.state & 0x0001):
            x1, y1 = self._snap_px(x1), self._snap_px(y1)
            x0, y0 = self._snap_px(x0), self._snap_px(y0)
        self.drag_start = None

        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w < 5 or h < 5:
            # trop petit -> ignore
            if self.new_rect_preview_id:
                self.canvas.delete(self.new_rect_preview_id)
                self.new_rect_preview_id = None
            return

        # Nom via preset ou prompt
        preset = self.preset_combo.get().strip() if self.preset_combo.get() else ""
        if preset and preset not in self.current_layout_rois:
            name = preset
        else:
            name = simpledialog.askstring("Nom ROI", "Nom de la ROI (ex: hero_stack, pot_value):")
            if not name:
                if self.new_rect_preview_id:
                    self.canvas.delete(self.new_rect_preview_id)
                    self.new_rect_preview_id = None
                return
            if name in self.current_layout_rois:
                messagebox.showerror("Erreur", "Un ROI avec ce nom existe déjà.")
                return

        self._add_roi(name, x, y, w, h)
        if self.new_rect_preview_id:
            self.canvas.delete(self.new_rect_preview_id)
            self.new_rect_preview_id = None

    # ---------- Dessin ----------
    def _redraw(self):
        self.canvas.delete("all")
        if not self.base_img:
            return
        # image redimensionnée selon zoom
        s = self.zoom.get()
        disp_w = int(self.base_w * s)
        disp_h = int(self.base_h * s)
        disp_img = self.base_img.resize((disp_w, disp_h), Image.NEAREST)
        self._tkimg = ImageTk.PhotoImage(disp_img)
        self.canvas.create_image(0, 0, image=self._tkimg, anchor=tk.NW)

        # dessiner ROIs
        for name, roi in self.current_layout_rois.items():
            rx, ry = roi.x * self.base_w, roi.y * self.base_h
            rw, rh = roi.w * self.base_w, roi.h * self.base_h
            x0, y0 = self._img_to_canvas(rx, ry)
            x1, y1 = self._img_to_canvas(rx + rw, ry + rh)
            color = "#00ff88" if name == self.active_roi_id else "#00d0ff"
            self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=2)
            self.canvas.create_text(x0 + 4, y0 + 12, anchor=tk.W, text=name, fill=color, font=("Segoe UI", 9, "bold"))

        # redimension canvas
        self.canvas.config(scrollregion=(0, 0, disp_w, disp_h))

    # ---------- Sauvegarde ----------
    def _on_save(self):
        os.makedirs(ROOMS_DIR, exist_ok=True)
        # Ecrire screenshot de référence
        screenshot_path = os.path.join(ROOMS_DIR, f"{self.room}_reference.png")
        try:
            self.base_img.save(screenshot_path)
        except Exception as e:
            messagebox.showwarning("Attention", f"Impossible d'enregistrer le screenshot: {e}")

        data = {
            "room": self.room,
            "version": 2,
            "scaling": {"mode": "normalized", "dpi_compensation": True},
            "client_size": {"w": self.base_w, "h": self.base_h},
            "anchors": {"table_bounds": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}},
            "layouts": {},
            "screenshot": os.path.relpath(screenshot_path, PKG_DIR).replace("\\", "/"),
            "templates": {"confirmators": []},
        }
        for layout_name, rois in self.layouts.items():
            data["layouts"][layout_name] = {
                "rois": {name: roi.to_yaml() for name, roi in rois.items()}
            }

        path = os.path.join(ROOMS_DIR, f"{self.room}.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        messagebox.showinfo("OK", f"YAML sauvegardé:\n{path}")


# -----------------------------
# Entrée principale
# -----------------------------

def run_calibrator(room_hint: Optional[str] = None):
    cand: CandidateWindow | None = choose_table(room_hint)
    if not cand:
        print("Aucune table pour calibrage.")
        return
    app = CalibratorApp(cand)
    app.mainloop()


if __name__ == "__main__":
    # Permet: python calibrate_gui.py winamax
    hint = sys.argv[1] if len(sys.argv) > 1 else None
    run_calibrator(hint)
