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

# Import de la reconnaissance
try:
    from poker_assistant.ocr.recognition_integration import RecognitionIntegration
    import cv2
    import numpy as np
    RECOGNITION_AVAILABLE = True
except ImportError:
    RECOGNITION_AVAILABLE = False
    print("⚠️ Module de reconnaissance non disponible")

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
        relative_to: str = "client",  # forcé en client pour cohérence
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
        self._last_raw: Optional[Image.Image] = None  # Stockage du dernier raw pour export instantané
        self._sct = mss.mss() if mss else None

        # offsets de centrage dans le canvas
        self._offset_x = 0
        self._offset_y = 0

        # Configuration YAML
        self.cfg: Dict[str, Any] = {}
        self.yaml_path = yaml_path
        self.layout_var = tk.StringVar(value=layout)
        self.relative_to_var = tk.StringVar(value="client")

        # Intégration de la reconnaissance
        self.recognition_integration: Optional[RecognitionIntegration] = None
        if RECOGNITION_AVAILABLE and yaml_path:
            try:
                self.recognition_integration = RecognitionIntegration(
                    yaml_path=yaml_path,
                    templates_dir="assets/templates"
                )
                print("✅ Module de reconnaissance intégré")
            except Exception as e:
                print(f"⚠️ Erreur intégration reconnaissance: {e}")
                self.recognition_integration = None

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
        self.show_card_zones = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Rectangles", variable=self.show_rectangles, command=self._request_redraw).pack(side="left", padx=(8, 2))
        ttk.Checkbutton(top, text="Noms", variable=self.show_labels, command=self._request_redraw).pack(side="left", padx=(4, 2))
        ttk.Checkbutton(top, text="Afficher table_zone", variable=self.show_table_zone, command=self._request_redraw).pack(side="left", padx=(4, 2))
        ttk.Checkbutton(top, text="Zones Cartes", variable=self.show_card_zones, command=self._request_redraw).pack(side="left", padx=(4, 2))
        ttk.Checkbutton(top, text="Anti-miroir", variable=self.anti_mirror).pack(side="left", padx=(8, 2))
        ttk.Checkbutton(top, text="Fit à la fenêtre", variable=self.fit_to_window, command=self._request_redraw).pack(side="left", padx=(8, 2))

        ttk.Button(top, text="100%", command=self._set_100).pack(side="left", padx=(6, 2))
        ttk.Button(top, text="Agrandir à l'image", command=self._resize_to_image).pack(side="left", padx=(2, 2))
        ttk.Button(top, text="Plein écran", command=lambda: self.state("zoomed")).pack(side="left", padx=(2, 2))
        ttk.Button(top, text="Normal", command=lambda: self.state("normal")).pack(side="left", padx=(2, 8))

        ttk.Button(top, text="Forcer focus", command=self._force_focus).pack(side="left", padx=(8, 2))
        ttk.Button(top, text="Exporter cartes (PNG)", command=self._export_cards).pack(side="left", padx=(8, 2))
        ttk.Button(top, text="Exporter les templates", command=self._export_templates).pack(side="left", padx=(8, 2))
        
        # Contrôles de reconnaissance
        if self.recognition_integration:
            ttk.Button(top, text="🔍 Reconnaissance", command=self._toggle_recognition).pack(side="left", padx=(8, 2))

        ttk.Label(top, text="Zoom:").pack(side="left", padx=(8, 2))
        self.scale_var = tk.DoubleVar(value=self.scale)
        ttk.Scale(top, from_=0.3, to=3.0, variable=self.scale_var, command=self._on_zoom_change).pack(side="left", padx=(0, 8))

        # Panneau de reconnaissance
        if self.recognition_integration:
            self._build_recognition_panel()

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
        try:
            bbox = self._current_bbox()
            if not bbox or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                return None

            # 1) PrintWindow si possible (anti-occlusion/mirror)
            if self.candidate.handle:
                img = _printwindow_client(self.candidate.handle)
                if img is not None and img.size[0] > 0 and img.size[1] > 0:
                    self._last_raw = img  # Stocke pour l'export
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
                    time.sleep(0.1)  # Délai augmenté pour la stabilisation
                img = _capture_bbox(bbox)
                if img is not None and img.size[0] > 0 and img.size[1] > 0:
                    self._last_raw = img  # Stocke pour l'export
                    return img
                return None
            finally:
                if withdraw:
                    try:
                        self.deiconify(); self.update_idletasks()
                    except Exception:
                        pass
        except Exception as e:
            print(f"Debug: Erreur capture: {e}")
            return None

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
        
        # Contrôle de fréquence pour éviter le clignotement
        current_time = time.time()
        if hasattr(self, '_last_update_time'):
            time_since_last = current_time - self._last_update_time
            if time_since_last < 0.2:  # Minimum 200ms entre les mises à jour
                self.after(100, self._loop)
                return
        
        self._last_update_time = current_time
        t0 = time.time()

        # Compteur d'échecs consécutifs
        if not hasattr(self, '_consecutive_failures'):
            self._consecutive_failures = 0

        raw = self._capture_raw()
        if raw is not None and raw.size[0] > 0 and raw.size[1] > 0:
            # Reset du compteur d'échecs en cas de succès
            self._consecutive_failures = 0
            self._last_raw_size = raw.size
            W, H = raw.size
            
            # Intégration de la reconnaissance
            if self.recognition_integration and self.recognition_integration.recognition_enabled:
                # Convertit l'image PIL en numpy array pour OpenCV
                frame_array = np.array(raw)
                frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)
                
                # Envoie le frame au pipeline de reconnaissance
                self.recognition_integration.process_frame(frame_bgr)
                
                # Met à jour l'affichage de la reconnaissance
                self._update_recognition_display()

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
            new_offset_x = max(0, (cw - disp_w) // 2)
            new_offset_y = max(0, (ch - disp_h) // 2)
            
            # Vérifie si l'image ou la position ont changé pour éviter les redraws inutiles
            image_changed = (not hasattr(self, '_last_image_hash') or 
                           hash(img.tobytes()) != self._last_image_hash)
            position_changed = (not hasattr(self, '_offset_x') or 
                              self._offset_x != new_offset_x or 
                              self._offset_y != new_offset_y)
            
            if image_changed or position_changed:
                self._offset_x = new_offset_x
                self._offset_y = new_offset_y
                self._last_image_hash = hash(img.tobytes())
                
                self._photo = ImageTk.PhotoImage(img)
                self.canvas.delete("all")
                self.canvas.create_image(self._offset_x, self._offset_y, image=self._photo, anchor=tk.NW)
                self.canvas.config(scrollregion=(0, 0, max(cw, disp_w), max(ch, disp_h)))

            # Dessiner overlays (toujours mis à jour)
            self._draw_overlays(disp_w, disp_h)

            # FPS
            self._update_fps()
        else:
            # Échec de capture - incrémente le compteur
            self._consecutive_failures += 1
            
            # Si trop d'échecs consécutifs, pause plus longue
            if self._consecutive_failures > 10:
                print(f"⚠️ {self._consecutive_failures} échecs consécutifs - pause de 2 secondes")
                self.after(2000, self._loop)  # Pause de 2 secondes
                return
            elif self._consecutive_failures > 5:
                print(f"⚠️ {self._consecutive_failures} échecs consécutifs - pause de 1 seconde")
                self.after(1000, self._loop)  # Pause de 1 seconde
                return

        # cadence - délai minimum augmenté pour éviter le clignotement
        elapsed = time.time() - t0
        delay = max(200, int((self.target_frame_time - elapsed) * 1000))  # Minimum 200ms
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
            
            # Dessine les zones de rank et suit des cartes
            if self.show_card_zones.get():
                self._draw_card_zones(disp_w, disp_h, ox, oy)
        except Exception as e:
            print(f"Debug: Erreur overlays: {e}")

    def _draw_card_zones(self, disp_w: int, disp_h: int, ox: int, oy: int):
        """Dessine les zones de rank et suit des cartes."""
        try:
            if not self.cfg or 'card_zones' not in self.cfg:
                return
            
            card_zones = self.cfg['card_zones']
            if not card_zones:
                return
            
            # Parcourt toutes les cartes avec leurs zones
            for card_name, zones in card_zones.items():
                # Trouve la ROI de la carte dans le layout
                card_roi = self._get_card_roi(card_name)
                if not card_roi:
                    continue
                
                # Convertit la ROI de la carte en pixels
                card_x0, card_y0, card_x1, card_y1 = self._roi_to_pixels_legacy(card_roi, disp_w, disp_h)
                
                # Dessine chaque zone de la carte
                for zone_name, zone_config in zones.items():
                    zone_type = zone_config.get('type', 'unknown')
                    zone_x = zone_config.get('x', 0)
                    zone_y = zone_config.get('y', 0)
                    zone_w = zone_config.get('w', 0)
                    zone_h = zone_config.get('h', 0)
                    
                    # Calcule les coordonnées absolues de la zone
                    zone_abs_x0 = card_x0 + int(zone_x * (card_x1 - card_x0))
                    zone_abs_y0 = card_y0 + int(zone_y * (card_y1 - card_y0))
                    zone_abs_x1 = card_x0 + int((zone_x + zone_w) * (card_x1 - card_x0))
                    zone_abs_y1 = card_y0 + int((zone_y + zone_h) * (card_y1 - card_y0))
                    
                    # Applique l'offset du canvas
                    zone_abs_x0 += ox
                    zone_abs_y0 += oy
                    zone_abs_x1 += ox
                    zone_abs_y1 += oy
                    
                    # Couleur selon le type
                    if zone_type == 'rank':
                        color = "#ff4444"  # Rouge pour les rangs
                        label_color = "#ff6666"
                    elif zone_type == 'suit':
                        color = "#44ff44"  # Vert pour les couleurs
                        label_color = "#66ff66"
                    else:
                        color = "#888888"  # Gris pour autres types
                        label_color = "#aaaaaa"
                    
                    # Dessine le rectangle de la zone
                    self.canvas.create_rectangle(
                        zone_abs_x0, zone_abs_y0, zone_abs_x1, zone_abs_y1,
                        outline=color, width=2, dash=(3, 3)
                    )
                    
                    # Ajoute le label si activé
                    if self.show_labels.get():
                        label_text = f"{zone_type}"
                        self.canvas.create_text(
                            zone_abs_x0 + 2, zone_abs_y0 + 2,
                            anchor=tk.NW, text=label_text,
                            fill=label_color, font=("Segoe UI", 8, "bold")
                        )
                        
        except Exception as e:
            print(f"Debug: Erreur zones cartes: {e}")

    def _get_card_roi(self, card_name: str) -> Optional[Dict[str, float]]:
        """Récupère la ROI d'une carte depuis le layout."""
        try:
            if not self.cfg or 'layouts' not in self.cfg:
                return None
            
            layout = self.cfg['layouts'].get(self.layout_var.get(), {})
            rois = layout.get('rois', {})
            
            if card_name in rois:
                return rois[card_name]
            else:
                return None
        except Exception:
            return None

    def _roi_to_pixels_legacy(self, roi_config: Dict[str, float], disp_w: int, disp_h: int) -> Tuple[int, int, int, int]:
        """Convertit une ROI en coordonnées pixels."""
        try:
            x = roi_config.get('x', 0)
            y = roi_config.get('y', 0)
            w = roi_config.get('w', 0)
            h = roi_config.get('h', 0)
            
            if self.relative_to_var.get() == "table_zone":
                # Coordonnées relatives à table_zone
                ax, ay, aw, ah = self._get_anchor_norm()
                x0 = int((ax + x * aw) * disp_w)
                y0 = int((ay + y * ah) * disp_h)
                x1 = int((ax + (x + w) * aw) * disp_w)
                y1 = int((ay + (y + h) * ah) * disp_h)
            else:
                # Coordonnées relatives au client
                client_size = self.cfg.get('client_size', {'w': 1376, 'h': 1040})
                ref_w, ref_h = client_size['w'], client_size['h']
                scale_x = disp_w / ref_w
                scale_y = disp_h / ref_h
                
                x0 = int(x * ref_w * scale_x)
                y0 = int(y * ref_h * scale_y)
                x1 = int((x + w) * ref_w * scale_x)
                y1 = int((y + h) * ref_h * scale_y)
            
            return x0, y0, x1, y1
        except Exception:
            return 0, 0, 0, 0

    def _update_fps(self):
        try:
            dt_prev = getattr(self, "_last_ts", 0.0)
            self._last_ts = time.time()
            if dt_prev:
                fps = 1.0 / (self._last_ts - dt_prev)
                self.fps_label.config(text=f"{fps:.1f} fps")
        except Exception:
            pass

    # ------------------------- export cartes -------------------------
    def _export_cards(self):
        """Exporte les cartes détectées en PNG dans un sous-dossier daté."""
        try:
            # Recapture ou utilise la dernière image
            if self._last_raw is None:
                self._capture_raw()
            
            if self._last_raw is None:
                messagebox.showerror("Export", "Aucune image disponible pour l'export")
                return
            
            # Détecte les ROIs de cartes
            card_rois = self._get_card_rois()
            if not card_rois:
                messagebox.showwarning("Export", "Aucune carte détectée dans le YAML")
                return
            
            # Crée le dossier d'export
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_dir = f"exported_cards_{timestamp}"
            os.makedirs(export_dir, exist_ok=True)
            
            # Exporte chaque carte
            exported_count = 0
            for roi_name, roi_px in card_rois.items():
                try:
                    # Applique l'inflate si défini
                    inflated_roi = self._apply_roi_inflate(roi_name, roi_px)
                    
                    # Crop la carte
                    card_img = self._crop_roi(self._last_raw, inflated_roi)
                    if card_img is None:
                        continue
                    
                    # Sauvegarde
                    filename = f"{roi_name}.png"
                    filepath = os.path.join(export_dir, filename)
                    card_img.save(filepath, "PNG")
                    exported_count += 1
                    
                except Exception as e:
                    print(f"Erreur export {roi_name}: {e}")
                    continue
            
            if exported_count > 0:
                messagebox.showinfo("Export", f"{exported_count} cartes exportées dans:\n{os.path.abspath(export_dir)}")
            else:
                messagebox.showwarning("Export", "Aucune carte n'a pu être exportée")
                
        except Exception as e:
            messagebox.showerror("Export", f"Erreur lors de l'export:\n{e}")

    def _export_templates(self):
        """Exporte les templates de rangs et couleurs selon les zones calibrées."""
        try:
            # Vérifie que les zones de cartes sont disponibles
            if not self.cfg or 'card_zones' not in self.cfg:
                messagebox.showerror("Export Templates", "Aucune zone de carte calibrée trouvée dans le YAML")
                return
            
            card_zones = self.cfg['card_zones']
            if not card_zones:
                messagebox.showerror("Export Templates", "Aucune zone de carte trouvée dans le YAML")
                return
            
            # Recapture ou utilise la dernière image
            if self._last_raw is None:
                self._capture_raw()
            
            if self._last_raw is None:
                messagebox.showerror("Export Templates", "Aucune image disponible pour l'export")
                return
            
            # Détermine la room et le layout
            room_name = "winamax"  # Pour l'instant, on ne nourrit que Winamax
            layout_name = self.layout_var.get()
            
            # Crée la structure de dossiers selon la nouvelle arborescence
            base_dir = "assets"
            templates_dir = os.path.join(base_dir, "templates", room_name, layout_name)
            ranks_dir = os.path.join(templates_dir, "ranks")
            suits_dir = os.path.join(templates_dir, "suits")
            
            # Crée tous les dossiers nécessaires
            os.makedirs(ranks_dir, exist_ok=True)
            os.makedirs(suits_dir, exist_ok=True)
            
            # Compteurs pour les noms de fichiers incrémentaux
            rank_counter = self._get_next_template_number(ranks_dir, "rank")
            suit_counter = self._get_next_template_number(suits_dir, "suit")
            
            exported_ranks = 0
            exported_suits = 0
            
            # Parcourt toutes les cartes avec leurs zones
            for card_name, zones in card_zones.items():
                # Trouve la ROI de la carte dans le layout
                card_roi = self._get_card_roi(card_name)
                if not card_roi:
                    continue
                
                # Convertit la ROI de la carte en pixels
                card_x0, card_y0, card_x1, card_y1 = self._roi_to_pixels_legacy(card_roi, self._last_raw.width, self._last_raw.height)
                
                # Dessine chaque zone de la carte
                for zone_name, zone_config in zones.items():
                    zone_type = zone_config.get('type', 'unknown')
                    zone_x = zone_config.get('x', 0)
                    zone_y = zone_config.get('y', 0)
                    zone_w = zone_config.get('w', 0)
                    zone_h = zone_config.get('h', 0)
                    
                    # Calcule les coordonnées absolues de la zone
                    zone_abs_x0 = card_x0 + int(zone_x * (card_x1 - card_x0))
                    zone_abs_y0 = card_y0 + int(zone_y * (card_y1 - card_y0))
                    zone_abs_x1 = card_x0 + int((zone_x + zone_w) * (card_x1 - card_x0))
                    zone_abs_y1 = card_y0 + int((zone_y + zone_h) * (card_y1 - card_y0))
                    
                    # Vérifie que la zone est valide
                    if zone_abs_x1 <= zone_abs_x0 or zone_abs_y1 <= zone_abs_y0:
                        continue
                    
                    # Crop la zone
                    try:
                        zone_img = self._last_raw.crop((zone_abs_x0, zone_abs_y0, zone_abs_x1, zone_abs_y1))
                        
                        # Sauvegarde selon le type avec noms incrémentaux
                        if zone_type == 'rank':
                            filename = f"rank_{rank_counter:03d}.png"
                            filepath = os.path.join(ranks_dir, filename)
                            zone_img.save(filepath, "PNG")
                            exported_ranks += 1
                            rank_counter += 1
                            
                        elif zone_type == 'suit':
                            filename = f"suit_{suit_counter:03d}.png"
                            filepath = os.path.join(suits_dir, filename)
                            zone_img.save(filepath, "PNG")
                            exported_suits += 1
                            suit_counter += 1
                            
                    except Exception as e:
                        print(f"Erreur export zone {zone_name} ({zone_type}): {e}")
                        continue
            
            # Message de confirmation
            total_exported = exported_ranks + exported_suits
            if total_exported > 0:
                message = f"Templates exportés avec succès!\n\n"
                message += f"🔴 Rangs: {exported_ranks} templates\n"
                message += f"🟢 Couleurs: {exported_suits} templates\n"
                message += f"📁 Dossier: {os.path.abspath(templates_dir)}\n\n"
                message += f"💡 Structure: assets/templates/{room_name}/{layout_name}/\n"
                message += "🔄 Export incrémental activé - les clics suivants ajouteront des templates"
                messagebox.showinfo("Export Templates", message)
            else:
                messagebox.showwarning("Export Templates", "Aucun template n'a pu être exporté")
                
        except Exception as e:
            messagebox.showerror("Export Templates", f"Erreur lors de l'export des templates: {e}")

    def _build_recognition_panel(self):
        """Construit le panneau d'affichage de la reconnaissance."""
        # Panneau de reconnaissance
        recognition_frame = ttk.LabelFrame(self, text="🎯 Reconnaissance de Cartes", padding=8)
        recognition_frame.pack(fill="x", padx=6, pady=(0, 6))
        
        # État du jeu
        self.game_state_label = ttk.Label(recognition_frame, text="🔍 Détection...", font=("Arial", 10, "bold"))
        self.game_state_label.pack(anchor="w")
        
        # Cartes hero
        self.hero_cards_label = ttk.Label(recognition_frame, text="Hero: ?? ??", font=("Arial", 9))
        self.hero_cards_label.pack(anchor="w")
        
        # Cartes du board
        self.board_cards_label = ttk.Label(recognition_frame, text="Board: ?? ?? ?? ?? ??", font=("Arial", 9))
        self.board_cards_label.pack(anchor="w")
        
        # Confiance
        self.confidence_label = ttk.Label(recognition_frame, text="Confiance: --", font=("Arial", 8))
        self.confidence_label.pack(anchor="w")
        
        # Statut
        self.recognition_status_label = ttk.Label(recognition_frame, text="🔴 Désactivé", font=("Arial", 8))
        self.recognition_status_label.pack(anchor="w")

    def _toggle_recognition(self):
        """Active/désactive la reconnaissance."""
        if not self.recognition_integration:
            return
        
        if self.recognition_integration.recognition_enabled:
            # Désactive la reconnaissance
            self.recognition_integration.recognition_enabled = False
            self.recognition_integration.stop_recognition()
            print("🔴 Reconnaissance désactivée")
        else:
            # Active la reconnaissance
            self.recognition_integration.recognition_enabled = True
            self.recognition_integration.start_recognition()
            print("🟢 Reconnaissance activée")

    def _update_recognition_display(self):
        """Met à jour l'affichage de la reconnaissance."""
        if not self.recognition_integration:
            return
        
        # Met à jour les labels
        self.game_state_label.config(text=self.recognition_integration.get_game_state_display())
        self.hero_cards_label.config(text=f"Hero: {self.recognition_integration.get_hero_cards_display()}")
        self.board_cards_label.config(text=f"Board: {self.recognition_integration.get_board_cards_display()}")
        self.confidence_label.config(text=self.recognition_integration.get_confidence_display())
        self.recognition_status_label.config(text=self.recognition_integration.get_recognition_status())

    def _get_next_template_number(self, directory: str, prefix: str) -> int:
        """Retourne le prochain numéro disponible pour les templates."""
        try:
            if not os.path.exists(directory):
                return 1
            
            # Liste tous les fichiers avec le préfixe donné
            existing_files = [f for f in os.listdir(directory) if f.startswith(prefix) and f.endswith('.png')]
            
            if not existing_files:
                return 1
            
            # Extrait les numéros existants
            numbers = []
            for filename in existing_files:
                try:
                    # Format attendu: prefix_XXX.png
                    number_part = filename.replace(f"{prefix}_", "").replace(".png", "")
                    numbers.append(int(number_part))
                except ValueError:
                    continue
            
            if not numbers:
                return 1
            
            # Retourne le prochain numéro disponible
            return max(numbers) + 1
            
        except Exception:
            return 1
    
    def _get_card_rois(self) -> Dict[str, Tuple[int, int, int, int]]:
        """Retourne les ROIs de cartes en pixels."""
        card_rois = {}
        
        # Récupère le layout actuel
        layout_name = self.layout_var.get()
        layouts = self.cfg.get("layouts", {})
        if layout_name not in layouts:
            return card_rois
        
        layout = layouts[layout_name]
        rois = layout.get("rois", {})
        
        # Détecte les cartes par type ou regex sur le nom
        for roi_name, roi_config in rois.items():
            # Vérifie si c'est une carte par type
            if isinstance(roi_config, dict) and roi_config.get("type") == "card":
                roi_px = self._roi_to_pixels(roi_config)
                if roi_px:
                    card_rois[roi_name] = roi_px
            # Sinon vérifie par regex sur le nom
            elif self._is_card_roi_name(roi_name):
                roi_px = self._roi_to_pixels(roi_config)
                if roi_px:
                    card_rois[roi_name] = roi_px
        
        return card_rois
    
    def _is_card_roi_name(self, name: str) -> bool:
        """Détermine si un nom de ROI correspond à une carte."""
        import re
        # Patterns pour détecter les cartes
        card_patterns = [
            r'board_card\d+',  # board_card1, board_card2, etc.
            r'hero_cards_(left|right)',  # hero_cards_left, hero_cards_right
            r'.*card.*',  # tout nom contenant "card"
        ]
        
        for pattern in card_patterns:
            if re.search(pattern, name, re.IGNORECASE):
                return True
        return False
    
    def _roi_to_pixels(self, roi_config: Dict[str, Any]) -> Optional[Tuple[int, int, int, int]]:
        """Convertit une ROI normalisée en pixels selon la base choisie."""
        try:
            if isinstance(roi_config, dict):
                x = roi_config.get("x", 0.0)
                y = roi_config.get("y", 0.0)
                w = roi_config.get("w", 0.0)
                h = roi_config.get("h", 0.0)
            else:
                # Format tuple/list
                x, y, w, h = roi_config
            
            # Convertit selon la base
            base = self.relative_to_var.get()
            if base == "table_zone":
                # Convertit via table_zone
                anchor_x, anchor_y, anchor_w, anchor_h = self._get_anchor_pixels()
                px_x = int(anchor_x + x * anchor_w)
                px_y = int(anchor_y + y * anchor_h)
                px_w = int(w * anchor_w)
                px_h = int(h * anchor_h)
            else:
                # Convertit via client
                client_w, client_h = self._get_client_size()
                px_x = int(x * client_w)
                px_y = int(y * client_h)
                px_w = int(w * client_w)
                px_h = int(h * client_h)
            
            return (px_x, px_y, px_w, px_h)
            
        except Exception as e:
            print(f"Erreur conversion ROI: {e}")
            return None
    
    def _get_anchor_pixels(self) -> Tuple[int, int, int, int]:
        """Retourne les coordonnées de table_zone en pixels."""
        try:
            anchors = self.cfg.get("anchors", {})
            table_zone = anchors.get("table_zone", {})
            
            x = table_zone.get("x", 0.0)
            y = table_zone.get("y", 0.0)
            w = table_zone.get("w", 1.0)
            h = table_zone.get("h", 1.0)
            
            client_w, client_h = self._get_client_size()
            px_x = int(x * client_w)
            px_y = int(y * client_h)
            px_w = int(w * client_w)
            px_h = int(h * client_h)
            
            return (px_x, px_y, px_w, px_h)
            
        except Exception:
            # Fallback: utilise tout le client
            client_w, client_h = self._get_client_size()
            return (0, 0, client_w, client_h)
    
    def _get_client_size(self) -> Tuple[int, int]:
        """Retourne la taille du client en pixels."""
        try:
            client_size = self.cfg.get("client_size", {})
            w = client_size.get("w", 1376)
            h = client_size.get("h", 1040)
            return (w, h)
        except Exception:
            return (1376, 1040)  # Valeur par défaut
    
    def _apply_roi_inflate(self, roi_name: str, roi_px: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        """Applique un inflate à une ROI si défini dans le YAML."""
        try:
            # Cherche une configuration d'inflate pour cette ROI
            layout_name = self.layout_var.get()
            layouts = self.cfg.get("layouts", {})
            if layout_name not in layouts:
                return roi_px
            
            layout = layouts[layout_name]
            rois = layout.get("rois", {})
            roi_config = rois.get(roi_name, {})
            
            if isinstance(roi_config, dict):
                inflate = roi_config.get("inflate", 0)
                if inflate > 0:
                    x, y, w, h = roi_px
                    # Applique l'inflate en pixels
                    base = self.relative_to_var.get()
                    if base == "table_zone":
                        anchor_w, anchor_h = self._get_anchor_pixels()[2:4]
                        px_inflate = int(inflate * min(anchor_w, anchor_h))
                    else:
                        client_w, client_h = self._get_client_size()
                        px_inflate = int(inflate * min(client_w, client_h))
                    
                    return (x - px_inflate, y - px_inflate, w + 2*px_inflate, h + 2*px_inflate)
            
            return roi_px
            
        except Exception as e:
            print(f"Erreur inflate ROI {roi_name}: {e}")
            return roi_px
    
    def _crop_roi(self, img: Image.Image, roi_px: Tuple[int, int, int, int]) -> Optional[Image.Image]:
        """Crop une région d'image selon les coordonnées pixels."""
        try:
            x, y, w, h = roi_px
            img_w, img_h = img.size
            
            # Assure que les coordonnées sont dans les limites
            x = max(0, min(x, img_w))
            y = max(0, min(y, img_h))
            w = max(1, min(w, img_w - x))
            h = max(1, min(h, img_h - y))
            
            return img.crop((x, y, x + w, y + h))
            
        except Exception as e:
            print(f"Erreur crop ROI: {e}")
            return None

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
