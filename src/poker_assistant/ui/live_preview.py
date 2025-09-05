# src/poker_assistant/ui/live_preview.py (overlay v2.4)
# Aperçu temps réel + superposition des ROIs depuis un YAML
# Améliorations UI & ergonomie:
#  - Fenêtre vraiment redimensionnable (minsize, exit plein écran, boutons dédiés)
#  - Affichage CENTRÉ de l'image dans le canvas (plus d'énorme marge à droite)
#  - Mode "Fit à la fenêtre" (contain) par défaut + boutons 100% / Agrandir à l'image / Plein écran / Normal
#  - Alignement stable après redimensionnement (x1/y1 calculés via (x+w)/(y+h))
#  - Base "table_zone" supportée (anchors.table_zone)
#  - Capture robuste: PrintWindow(hwnd) d'abord; sinon ScreenCrop avec anti-miroir
#
# Dépendances : pillow, mss, pywin32, pyyaml
# pip install pillow mss pywin32 pyyaml

from __future__ import annotations

import os
import time
from typing import Optional, Tuple, Dict, Any

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk, ImageGrab

# DPI aware
try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

try:
    import mss  # capture écran rapide
except ImportError:
    mss = None

# Win32
try:
    import win32gui, win32ui, win32con
except Exception:
    win32gui = None
    win32ui = None
    win32con = None

import yaml

# projet
try:
    from ..windows.detector import CandidateWindow
except Exception:
    from windows.detector import CandidateWindow  # fallback exécution directe


# ------------------------- utilitaires fenêtre -------------------------

def _get_client_rect_from_hwnd(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """(left, top, right, bottom) de la ZONE CLIENT de la fenêtre."""
    if not (hwnd and win32gui):
        return None
    try:
        if not win32gui.IsWindow(hwnd):
            return None
        l, t = win32gui.ClientToScreen(hwnd, (0, 0))
        rct = win32gui.GetClientRect(hwnd)
        w = int(rct[2] - rct[0])
        h = int(rct[3] - rct[1])
        if w < 50 or h < 50:
            return None
        return int(l), int(t), int(l + w), int(t + h)
    except Exception:
        return None


def _printwindow_client(hwnd: int) -> Optional[Image.Image]:
    """Essaye de capturer la zone client via PrintWindow (anti-occlusion)."""
    if not (win32gui and win32ui):
        return None
    try:
        rect = _get_client_rect_from_hwnd(hwnd)
        if not rect:
            return None
        L, T, R, B = rect
        W, H = R - L, B - T
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        bmp    = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfcDC, W, H)
        saveDC.SelectObject(bmp)
        ok = win32gui.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)  # 2=PW_RENDERFULLCONTENT
        bmpinfo = bmp.GetInfo()
        bmpstr  = bmp.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)
        # cleanup
        win32gui.DeleteObject(bmp.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        return img if ok == 1 else None
    except Exception:
        return None


def _ensure_target_visible(hwnd: int):
    if not (win32gui and win32con):
        return
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        except Exception:
            pass
    except Exception:
        pass


def _capture_bbox(bbox: Tuple[int, int, int, int]) -> Optional[Image.Image]:
    L, T, R, B = map(int, bbox)
    W, H = max(1, R - L), max(1, B - T)
    try:
        if mss:
            with mss.mss() as sct:
                raw = sct.grab({"left": L, "top": T, "width": W, "height": H})
                return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return ImageGrab.grab(bbox=(L, T, R, B)).convert("RGB")
    except Exception:
        return None


# ------------------------- classe principale -------------------------

class LivePreview(tk.Tk):
    """Aperçu temps réel + overlay ROIs depuis YAML."""

    def __init__(
        self,
        candidate: CandidateWindow,
        yaml_path: Optional[str] = None,
        layout: str = "default",
        relative_to: str = "client",  # "client" ou "table_zone"
        track_move: bool = True,
        target_fps: int = 20,
        scale: float = 1.0,
        stay_on_top: bool = False,
        anti_mirror: bool = True,
        fit_to_window: bool = True,
    ):
        super().__init__()
        if mss is None:
            raise RuntimeError("Le module 'mss' est requis. pip install mss pillow pywin32 pyyaml")

        self.title(f"Aperçu: {candidate.title}")
        self.state("normal")  # s'assurer qu'on n'est pas coincé en plein écran
        self.resizable(True, True)
        self.minsize(900, 560)  # fenêtre confortable par défaut
        if stay_on_top:
            self.attributes("-topmost", True)

        self.candidate = candidate
        self.track_move = track_move
        self.target_frame_time = 1.0 / max(1, int(target_fps))
        self.scale = float(scale)
        self.anti_mirror = tk.BooleanVar(value=anti_mirror)
        self.fit_to_window = tk.BooleanVar(value=fit_to_window)

        self._running = True
        self._photo = None
        self._last_raw_size: Optional[Tuple[int, int]] = None
        self._sct = mss.mss() if mss else None

        # offsets de centrage dans le canvas
        self._offset_x = 0
        self._offset_y = 0

        # Configuration YAML
        self.cfg: Dict[str, Any] = {}
        self.yaml_path = yaml_path
        self.layout_var = tk.StringVar(value=layout)
        self.relative_to_var = tk.StringVar(value=relative_to)

        # UI d'abord
        self._build_ui()

        # Charger YAML ensuite
        if yaml_path and os.path.exists(yaml_path):
            self._load_yaml(yaml_path)

        # Recentrer/redessiner lors d'un resize de fenêtre
        self.bind("<Configure>", lambda e: self._request_redraw())

        # boucle
        self.after(0, self._loop)

    # ------------------------- UI -------------------------
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=6)

        ttk.Button(top, text="Ouvrir YAML…", command=self._choose_yaml).pack(side="left")

        ttk.Label(top, text="Layout:").pack(side="left", padx=(8, 2))
        self.layout_box = ttk.Combobox(top, width=14, textvariable=self.layout_var, state="readonly")
        self.layout_box.pack(side="left")
        self._refresh_layout_choices()
        self.layout_box.bind("<<ComboboxSelected>>", lambda e: self._request_redraw())

        ttk.Label(top, text="Base:").pack(side="left", padx=(8, 2))
        base_box = ttk.Combobox(top, width=12, values=["client", "table_zone"], textvariable=self.relative_to_var, state="readonly")
        base_box.pack(side="left")
        self.relative_to_var.trace("w", lambda *args: self._request_redraw())

        self.show_rectangles = tk.BooleanVar(value=True)
        self.show_labels = tk.BooleanVar(value=True)
        self.show_table_zone = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Rectangles", variable=self.show_rectangles, command=self._request_redraw).pack(side="left", padx=(8, 2))
        ttk.Checkbutton(top, text="Noms", variable=self.show_labels, command=self._request_redraw).pack(side="left", padx=(4, 2))
        ttk.Checkbutton(top, text="Afficher table_zone", variable=self.show_table_zone, command=self._request_redraw).pack(side="left", padx=(4, 2))
        ttk.Checkbutton(top, text="Anti-miroir", variable=self.anti_mirror).pack(side="left", padx=(8, 2))
        ttk.Checkbutton(top, text="Fit à la fenêtre", variable=self.fit_to_window, command=self._request_redraw).pack(side="left", padx=(8, 2))

        ttk.Button(top, text="100%", command=self._set_100).pack(side="left", padx=(6, 2))
        ttk.Button(top, text="Agrandir à l'image", command=self._resize_to_image).pack(side="left", padx=(2, 2))
        ttk.Button(top, text="Plein écran", command=lambda: self.state("zoomed")).pack(side="left", padx=(2, 2))
        ttk.Button(top, text="Normal", command=lambda: self.state("normal")).pack(side="left", padx=(2, 8))

        ttk.Button(top, text="Forcer focus", command=self._force_focus).pack(side="left", padx=(8, 2))

        ttk.Label(top, text="Zoom:").pack(side="left", padx=(8, 2))
        self.scale_var = tk.DoubleVar(value=self.scale)
        ttk.Scale(top, from_=0.3, to=3.0, variable=self.scale_var, command=self._on_zoom_change).pack(side="left", padx=(0, 8))

        self.fps_label = ttk.Label(top, text="0 fps")
        self.fps_label.pack(side="right")

        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0, bg="#0f0f10")
        self.canvas.pack(fill="both", expand=True)

        self.bind("<Escape>", lambda e: self._on_close())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _choose_yaml(self):
        path = filedialog.askopenfilename(title="Sélectionner le YAML de layout", filetypes=[("YAML", "*.yaml *.yml"), ("Tous", "*.*")])
        if path:
            self._load_yaml(path)

    def _load_yaml(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f) or {}
            self.yaml_path = path
            self._refresh_layout_choices()
            self._request_redraw()
        except Exception as e:
            messagebox.showerror("YAML", f"Erreur d'ouverture YAML :\n{e}")

    def _refresh_layout_choices(self):
        layouts = sorted((self.cfg.get("layouts") or {}).keys()) if self.cfg else []
        if not hasattr(self, "layout_box"):
            return
        if not layouts:
            self.layout_box.configure(values=["default"])  # valeur par défaut
            if self.layout_var.get() == "":
                self.layout_var.set("default")
            return
        self.layout_box.configure(values=layouts)
        if self.layout_var.get() not in layouts:
            self.layout_var.set(layouts[0])

    def _on_zoom_change(self, value):
        self.scale = float(value)
        if self.fit_to_window.get():
            self.fit_to_window.set(False)
        self._request_redraw()

    def _set_100(self):
        self.fit_to_window.set(False)
        self.scale = 1.0
        self.scale_var.set(1.0)
        self._request_redraw()

    def _resize_to_image(self):
        if not self._last_raw_size:
            return
        W, H = self._last_raw_size
        eff = self.scale if not self.fit_to_window.get() else 1.0
        w = int(W * eff); h = int(H * eff)
        # Ajouter une marge pour la barre d'outils
        self.update_idletasks()
        chrome_h = max(0, self.winfo_height() - self.canvas.winfo_height())
        chrome_w = max(0, self.winfo_width() - self.canvas.winfo_width())
        w += chrome_w; h += chrome_h
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(max(900, w), sw - 40)
        h = min(max(560, h), sh - 80)
        self.geometry(f"{w}x{h}")

    def _force_focus(self):
        if self.candidate.handle:
            _ensure_target_visible(self.candidate.handle)

    # ------------------------- capture -------------------------
    def _current_bbox(self) -> Tuple[int, int, int, int]:
        if self.track_move and self.candidate.handle:
            rect = _get_client_rect_from_hwnd(self.candidate.handle)
            if rect:
                return rect
        return self.candidate.bbox

    def _intersects_preview(self, bbox: Tuple[int, int, int, int]) -> bool:
        try:
            self.update_idletasks()
            gx, gy = self.winfo_rootx(), self.winfo_rooty()
            gw, gh = max(1, self.winfo_width()), max(1, self.winfo_height())
            L, T, R, B = bbox
            return (gx < R and gx + gw > L and gy < B and gy + gh > T)
        except Exception:
            return False

    def _capture_raw(self) -> Optional[Image.Image]:
        bbox = self._current_bbox()

        # 1) PrintWindow si possible (anti-occlusion/mirror)
        if self.candidate.handle:
            img = _printwindow_client(self.candidate.handle)
            if img is not None:
                return img

        # 2) Screen crop (avec anti-miroir optionnel)
        withdraw = False
        if self.anti_mirror.get() and self._intersects_preview(bbox):
            try:
                self.withdraw(); withdraw = True; self.update_idletasks()
            except Exception:
                pass
        try:
            if self.candidate.handle:
                _ensure_target_visible(self.candidate.handle)
                time.sleep(0.06)
            return _capture_bbox(bbox)
        finally:
            if withdraw:
                try:
                    self.deiconify(); self.update_idletasks()
                except Exception:
                    pass

    # ------------------------- overlay helpers -------------------------
    def _get_anchor_norm(self) -> Tuple[float, float, float, float]:
        """anchors.table_zone si présent, sinon plein client (0,0,1,1)."""
        if not self.cfg:
            return 0.0, 0.0, 1.0, 1.0
        anchors = self.cfg.get("anchors") or {}
        tz = anchors.get("table_zone")
        if tz:
            return float(tz.get("x", 0.0)), float(tz.get("y", 0.0)), float(tz.get("w", 1.0)), float(tz.get("h", 1.0))
        # compat (si table_zone a été rangé dans rois par erreur)
        rois = ((self.cfg.get("layouts") or {}).get(self.layout_var.get(), {}) or {}).get("rois") or {}
        tz = rois.get("table_zone")
        if tz:
            return float(tz.get("x", 0.0)), float(tz.get("y", 0.0)), float(tz.get("w", 1.0)), float(tz.get("h", 1.0))
        return 0.0, 0.0, 1.0, 1.0

    def _iter_roi_rects(self, disp_w: int, disp_h: int):
        if not self.cfg:
            return
        layout = (self.cfg.get("layouts") or {}).get(self.layout_var.get(), {}) or {}
        rois: Dict[str, Dict[str, float]] = layout.get("rois") or {}
        if not rois:
            return

        base = self.relative_to_var.get()
        ax, ay, aw, ah = self._get_anchor_norm()

        # Taille de référence (si jamais quelqu'un a besoin d'un ref size)
        ref_size = self.cfg.get("client_size", {}) or {}
        ref_w = float(ref_size.get("w", disp_w))
        ref_h = float(ref_size.get("h", disp_h))
        scale_x = disp_w / ref_w if ref_w > 0 else 1.0
        scale_y = disp_h / ref_h if ref_h > 0 else 1.0

        for name, r in rois.items():
            if name == "table_zone":
                continue
            try:
                x = float(r["x"]); y = float(r["y"]); w = float(r["w"]); h = float(r["h"])
            except Exception:
                continue

            if base == "table_zone":
                x0 = round((ax + x * aw) * disp_w)
                y0 = round((ay + y * ah) * disp_h)
                x1 = round((ax + (x + w) * aw) * disp_w)
                y1 = round((ay + (y + h) * ah) * disp_h)
            else:  # client
                x0 = round(x * ref_w * scale_x)
                y0 = round(y * ref_h * scale_y)
                x1 = round((x + w) * ref_w * scale_x)
                y1 = round((y + h) * ref_h * scale_y)
            yield name, x0, y0, x1, y1

    # ------------------------- boucle -------------------------
    def _loop(self):
        if not self._running:
            return
        t0 = time.time()

        raw = self._capture_raw()
        if raw is not None and raw.size[0] > 0 and raw.size[1] > 0:
            self._last_raw_size = raw.size
            W, H = raw.size

            # Choisir l'échelle effective
            eff_scale = self.scale
            self.update_idletasks()
            cw = max(1, self.canvas.winfo_width())
            ch = max(1, self.canvas.winfo_height())
            if self.fit_to_window.get():
                eff_scale = max(0.1, min(cw / W, ch / H))
                self.scale_var.set(eff_scale)

            disp_w, disp_h = int(W * eff_scale), int(H * eff_scale)
            img = raw if eff_scale == 1.0 else raw.resize((disp_w, disp_h), Image.NEAREST)

            # Centrage dans le canvas
            self._offset_x = max(0, (cw - disp_w) // 2)
            self._offset_y = max(0, (ch - disp_h) // 2)

            self._photo = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(self._offset_x, self._offset_y, image=self._photo, anchor=tk.NW)
            self.canvas.config(scrollregion=(0, 0, max(cw, disp_w), max(ch, disp_h)))

            # Dessiner overlays
            self._draw_overlays(disp_w, disp_h)

            # FPS
            self._update_fps()

        # cadence
        elapsed = time.time() - t0
        delay = max(20, int((self.target_frame_time - elapsed) * 1000))
        self.after(delay, self._loop)

    def _draw_overlays(self, disp_w: int, disp_h: int):
        try:
            ox, oy = self._offset_x, self._offset_y
            if self.show_table_zone.get():
                ax, ay, aw, ah = self._get_anchor_norm()
                ax0 = int(ax * disp_w) + ox; ay0 = int(ay * disp_h) + oy
                ax1 = int((ax + aw) * disp_w) + ox; ay1 = int((ay + ah) * disp_h) + oy
                self.canvas.create_rectangle(ax0, ay0, ax1, ay1, outline="#ffaa00", width=2, dash=(6, 4))
                self.canvas.create_text(ax0 + 4, ay0 + 12, anchor=tk.W, text="table_zone", fill="#ffaa00", font=("Segoe UI", 9, "bold"))

            if self.show_rectangles.get():
                for name, x0, y0, x1, y1 in self._iter_roi_rects(disp_w, disp_h):
                    x0 += ox; y0 += oy; x1 += ox; y1 += oy
                    self.canvas.create_rectangle(x0, y0, x1, y1, outline="#00d0ff", width=2)
                    if self.show_labels.get():
                        self.canvas.create_text(x0 + 4, y0 + 12, anchor=tk.W, text=name, fill="#00d0ff", font=("Segoe UI", 9, "bold"))
        except Exception as e:
            print(f"Debug: Erreur overlays: {e}")

    def _update_fps(self):
        try:
            dt_prev = getattr(self, "_last_ts", 0.0)
            self._last_ts = time.time()
            if dt_prev:
                fps = 1.0 / (self._last_ts - dt_prev)
                self.fps_label.config(text=f"{fps:.1f} fps")
        except Exception:
            pass

    # ------------------------- divers -------------------------
    def _request_redraw(self):
        # rien à faire ici: la boucle principale rafraîchit en continu; cette
        # fonction existe pour harmoniser les callbacks et éviter les recaptures inutiles
        pass

    def _on_close(self):
        self._running = False
        try:
            if self._sct:
                self._sct.close()
        finally:
            self.after(100, self.destroy)


# ------------------------- fonction d'entrée -------------------------

def show_live_preview(
    candidate: CandidateWindow,
    yaml_path: Optional[str] = None,
    layout: str = "default",
    relative_to: str = "client",
    track_move: bool = True,
    target_fps: int = 20,
    scale: float = 1.0,
    stay_on_top: bool = False,
    anti_mirror: bool = True,
    fit_to_window: bool = True,
):
    app = LivePreview(
        candidate=candidate,
        yaml_path=yaml_path,
        layout=layout,
        relative_to=relative_to,
        track_move=track_move,
        target_fps=target_fps,
        scale=scale,
        stay_on_top=stay_on_top,
        anti_mirror=anti_mirror,
        fit_to_window=fit_to_window,
    )
    app.mainloop()


if __name__ == "__main__":
    try:
        from windows.detector import detect_poker_tables
        cands = detect_poker_tables("winamax")
        if cands:
            show_live_preview(cands[0], yaml_path="rooms/winamax.yaml", relative_to="table_zone")
        else:
            print("Aucune table détectée")
    except Exception as e:
        print("Test manuel: import detector indisponible:", e)
