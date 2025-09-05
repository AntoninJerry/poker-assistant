from __future__ import annotations

import argparse, os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import numpy as np
import cv2, mss, yaml, pywinctl
from PySide6 import QtCore, QtGui, QtWidgets

# --- pywin32 pour PrintWindow (robuste) ---
try:
    import win32gui, win32ui, win32con
    HAS_PYWIN32 = True
except Exception:
    HAS_PYWIN32 = False

from poker_assistant.config import AppSettings, load_room_config
try:
    from poker_assistant.windows.detector import list_poker_tables as _list_tables
except Exception:
    _list_tables = None


# ---------------- DPI helpers ----------------
IS_WIN = os.name == "nt"

def _enable_dpi_awareness() -> None:
    if not IS_WIN:
        return
    try:
        import ctypes  # type: ignore
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass  # Qt a déjà un contexte DPI correct

def _logical_to_physical_rect(x: int, y: int, w: int, h: int, hwnd: Optional[int] = None):
    if not IS_WIN:
        return x, y, w, h, 1.0
    scale = 1.0
    try:
        import ctypes  # type: ignore
        user32 = ctypes.windll.user32
        dpi = user32.GetDpiForWindow(hwnd) if hwnd else user32.GetDpiForSystem()
        scale = max(1.0, float(dpi) / 96.0)
    except Exception:
        pass
    return int(x * scale), int(y * scale), int(w * scale), int(h * scale), scale

# --- client rect (logique) d'une fenêtre ---
def _get_client_rect_logical(hwnd: int) -> Tuple[int, int, int, int]:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))  # (0,0,w,h)
    w, h = rect.right - rect.left, rect.bottom - rect.top
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))   # coin haut-gauche client -> écran
    return int(pt.x), int(pt.y), int(w), int(h)


# ---------------- Capture helpers ----------------
@dataclass
class PxRect:
    x: int
    y: int
    w: int
    h: int

def grab_rect_mss(rect: PxRect) -> np.ndarray:
    with mss.mss() as sct:
        shot = sct.grab({"left": rect.x, "top": rect.y, "width": rect.w, "height": rect.h})
        bgr = cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

def grab_window_printwindow(hwnd: int) -> Optional[np.ndarray]:
    """Capture le CLIENT RECT via PrintWindow (ne dépend pas de l'écran, évite la récursion)."""
    if not HAS_PYWIN32:
        return None
    try:
        cx, cy, cw, ch = _get_client_rect_logical(hwnd)
        px, py, pw, ph, _ = _logical_to_physical_rect(cx, cy, cw, ch, hwnd)
        width, height = max(1, pw), max(1, ph)

        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
        saveDC.SelectObject(saveBitMap)

        flags = 0x00000001 | 0x00000002  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
        win32gui.PrintWindow(hwnd, saveDC.GetSafeHdc(), flags)

        bmpinfo = saveBitMap.GetInfo()
        bmpstr  = saveBitMap.GetBitmapBits(True)

        # Cleanup GDI
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC(); mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

        # BGRA -> RGB numpy
        img = np.frombuffer(bmpstr, dtype=np.uint8)
        img.shape = (bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4)
        bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    except Exception:
        return None

def is_uniform_frame(img: np.ndarray, thr_std: float = 2.0) -> bool:
    if img is None or img.size == 0:
        return True
    return float(img.std()) < thr_std  # blanc/noir quasi uniforme


# ---------------- Normalization helpers ----------------
def roi_to_abs(win_bbox: Tuple[int,int,int,int], anchors: Dict[str, dict], roi: Dict[str, float]) -> Tuple[int,int,int,int]:
    wx, wy, ww, wh = win_bbox
    ref_name = roi.get("ref", "window")
    if ref_name == "window":
        ax, ay, aw, ah = 0.0, 0.0, 1.0, 1.0
    else:
        a = anchors[ref_name]
        ax, ay, aw, ah = a["x"], a["y"], a["w"], a["h"]
    rx = wx + int((ax + roi["x"] * aw) * ww)
    ry = wy + int((ay + roi["y"] * ah) * wh)
    rw = max(1, int(roi["w"] * aw * ww))
    rh = max(1, int(roi["h"] * ah * wh))
    return rx, ry, rw, rh


# ---------------- Sélection fenêtre cible ----------------
@dataclass
class TargetWindow:
    handle: Optional[int]
    title: str
    bbox_logical: Tuple[int, int, int, int]

def _pick_table_for_room(room: str) -> TargetWindow:
    room = room.lower()
    if _list_tables:
        try:
            tables = [t for t in _list_tables() if getattr(t, "room", "").lower() in (room, "winamax", "pmu")]
            if tables:
                t = max(tables, key=lambda x: x.bbox[2] * x.bbox[3])
                print(f"[roi_viewer] Fenêtre sélectionnée: '{t.title}' {t.bbox}")
                return TargetWindow(getattr(t, "handle", None), getattr(t, "title", ""), t.bbox)
        except Exception:
            pass
    # fallback simple par titre
    cands: List[TargetWindow] = []
    for w in pywinctl.getAllWindows():
        try:
            if not (w.isVisible and not w.isMinimized):
                continue
            title = w.title or ""
            if room in title.lower():
                x, y, r, b = w.left, w.top, w.right, w.bottom
                cands.append(TargetWindow(w.getHandle(), title, (x, y, r - x, b - y)))
        except Exception:
            continue
    if not cands:
        raise RuntimeError(f"Aucune fenêtre table détectée pour '{room}'. Ouvre une vraie table.")
    t = max(cands, key=lambda c: c.bbox_logical[2] * c.bbox_logical[3])
    print(f"[roi_viewer] Fenêtre sélectionnée: '{t.title}' {t.bbox_logical}")
    return t


# ---------------- Viewer temps réel ----------------
class LiveRoiViewer(QtWidgets.QMainWindow):
    def __init__(self, room: str, settings: Optional[AppSettings] = None, fps: int = 20):
        super().__init__()
        self.settings = settings or AppSettings()
        self.room = room.lower()
        self.setWindowTitle(f"ROI Live Viewer — {room}")
        self.fps = max(5, min(60, fps))

        tgt = _pick_table_for_room(self.room)
        self.hwnd = tgt.handle

        # Client rect (logique) -> pixels (physiques)
        if self.hwnd:
            cx, cy, cw, ch = _get_client_rect_logical(self.hwnd)
            px_x, px_y, px_w, px_h, _ = _logical_to_physical_rect(cx, cy, cw, ch, self.hwnd)
        else:
            lx, ly, lw, lh = tgt.bbox_logical
            px_x, px_y, px_w, px_h, _ = _logical_to_physical_rect(lx, ly, lw, lh, self.hwnd)
        self.win_bbox = (px_x, px_y, px_w, px_h)

        # Fenêtre de preview (on l'éloigne du rect capturé pour éviter toute récursion MSS)
        self.label = QtWidgets.QLabel(self); self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(self.label)
        self.resize(min(px_w, 1280), min(px_h, 720))
        self.move(px_x + 60, max(0, px_y - self.height() - 60))

        # Charger config YAML (modèle + brut pour 'ref')
        self.cfg = load_room_config(self.room, self.settings)
        try:
            yaml_path = (self.settings.ROOMS_DIR / f"{self.room}.yaml").resolve()
            with yaml_path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            self.rois_raw = raw.get("rois", {})
        except Exception:
            self.rois_raw = {}

        # (Optionnel) Exclure cette fenêtre de la capture écran (Windows 10 2004+)
        if IS_WIN:
            try:
                import ctypes  # type: ignore
                hwnd_view = int(self.winId())  # QWidget winId -> HWND
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd_view, 0x11)  # WDA_EXCLUDEFROMCAPTURE
            except Exception:
                pass

        QtGui.QShortcut(QtGui.QKeySequence("Esc"), self, activated=self.close)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(1000 / self.fps))

    def _tick(self) -> None:
        # Suivre le client rect (physique)
        try:
            if self.hwnd:
                cx, cy, cw, ch = _get_client_rect_logical(self.hwnd)
                px_x, px_y, px_w, px_h, _ = _logical_to_physical_rect(cx, cy, cw, ch, self.hwnd)
                self.win_bbox = (px_x, px_y, px_w, px_h)
        except Exception:
            self.timer.stop()
            return

        # 1) PrintWindow (robuste, hors-écran)
        frame_rgb = grab_window_printwindow(self.hwnd) if self.hwnd else None

        # 2) Fallback MSS (si PrintWindow indisponible)
        if frame_rgb is None or is_uniform_frame(frame_rgb):
            try:
                frame_rgb = grab_rect_mss(PxRect(*self.win_bbox))
            except Exception:
                frame_rgb = None

        if frame_rgb is None:
            w, h = self.win_bbox[2], self.win_bbox[3]
            frame_rgb = np.zeros((max(1, h), max(1, w), 3), dtype=np.uint8)
            cv2.putText(frame_rgb, "Capture indisponible", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 2, cv2.LINE_AA)

        H, W = frame_rgb.shape[:2]
        canvas = frame_rgb.copy()

        # Anchors (verts)
        anchors_norm: Dict[str, dict] = {}
        if self.cfg.anchors:
            for name, a in self.cfg.anchors.items():
                anchors_norm[name] = {"x": a.x, "y": a.y, "w": a.w, "h": a.h}
                rx, ry, rw, rh = roi_to_abs(self.win_bbox, {}, {"ref": "window", "x": a.x, "y": a.y, "w": a.w, "h": a.h})
                rx -= self.win_bbox[0]; ry -= self.win_bbox[1]
                cv2.rectangle(canvas, (rx, ry), (rx + rw, ry + rh), (0, 230, 118), 2)
                cv2.putText(canvas, f"[anchor] {name}", (rx + 6, ry + 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240,240,240), 1, cv2.LINE_AA)

        # ROIs (bleus) avec support du 'ref'
        if self.cfg.rois:
            for name, r in self.cfg.rois.items():
                ref_name = "window"
                raw = self.rois_raw.get(name, {})
                if isinstance(raw, dict):
                    ref_name = raw.get("ref", "window")
                rd = {"x": r.x, "y": r.y, "w": r.w, "h": r.h, "ref": ref_name}
                rx, ry, rw, rh = roi_to_abs(self.win_bbox, anchors_norm, rd)
                rx -= self.win_bbox[0]; ry -= self.win_bbox[1]
                cv2.rectangle(canvas, (rx, ry), (rx + rw, ry + rh), (79, 195, 247), 2)
                cv2.putText(canvas, name, (rx + 6, ry + 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240,240,240), 1, cv2.LINE_AA)

        qimg = QtGui.QImage(canvas.data, W, H, W * 3, QtGui.QImage.Format.Format_RGB888).copy()
        pix  = QtGui.QPixmap.fromImage(qimg)
        self.label.setPixmap(pix.scaled(self.label.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                        QtCore.Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, ev: QtGui.QResizeEvent) -> None:
        self._tick()
        super().resizeEvent(ev)


# ---------------- CLI ----------------
def main() -> None:
    _enable_dpi_awareness()
    parser = argparse.ArgumentParser(description="Viewer temps réel des ROIs (capture live robuste).")
    parser.add_argument("--room", choices=["winamax", "pmu"], default="winamax")
    parser.add_argument("--fps", type=int, default=20)
    args = parser.parse_args()

    settings = AppSettings()
    app = QtWidgets.QApplication([])
    w = LiveRoiViewer(room=args.room, settings=settings, fps=args.fps)
    w.show()
    app.exec()

if __name__ == "__main__":
    main()
