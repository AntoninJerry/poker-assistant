from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox

import cv2
import mss
import numpy as np
from PIL import Image, ImageTk
import yaml

from poker_assistant.config import AppSettings, load_room_config, Roi, TemplateConfirmator  # :contentReference[oaicite:3]{index=3}
from poker_assistant.windows.detector import select_best_poker_window  # :contentReference[oaicite:4]{index=4}


@dataclass
class PxRect:
    x: int
    y: int
    w: int
    h: int

    @property
    def br(self) -> Tuple[int, int]:
        return self.x + self.w, self.y + self.h


def _grab_rect(rect: PxRect) -> np.ndarray:
    with mss.mss() as sct:
        shot = sct.grab({"left": rect.x, "top": rect.y, "width": rect.w, "height": rect.h})
        img = np.array(shot)  # BGRA
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def _norm_from_px(px: PxRect, win: PxRect) -> Dict[str, float]:
    return {
        "x": max(0.0, min(1.0, (px.x - win.x) / max(win.w, 1))),
        "y": max(0.0, min(1.0, (px.y - win.y) / max(win.h, 1))),
        "w": max(0.0, min(1.0, px.w / max(win.w, 1))),
        "h": max(0.0, min(1.0, px.h / max(win.h, 1))),
    }


def _px_from_norm(norm: Dict[str, float], win: PxRect) -> PxRect:
    return PxRect(
        x=int(win.x + norm["x"] * win.w),
        y=int(win.y + norm["y"] * win.h),
        w=max(1, int(norm["w"] * win.w)),
        h=max(1, int(norm["h"] * win.h)),
    )


class CalibratorApp(ctk.CTk):
    PRESET_NAMES = [
        "hero_cards",
        "community_cards",
        "pot_value",
        "action_buttons",
    ]

    def __init__(self, room: str, yaml_path: Path, settings: Optional[AppSettings] = None):
        super().__init__()
        self.title(f"Calibration — {room}")
        self.geometry("1100x760")
        self.minsize(980, 680)

        self.settings = settings or AppSettings()
        self.room_name = room
        self.yaml_path = yaml_path

        # 1) Détecter la fenêtre table via detector.py
        win_rect = select_best_poker_window()  # ClientRect | None  :contentReference[oaicite:5]{index=5}
        if win_rect is None:
            messagebox.showerror("Erreur", "Aucune table poker détectée. Ouvrez une table Winamax/PMU.")
            self.destroy()
            raise SystemExit(2)

        self.win = PxRect(x=win_rect.left, y=win_rect.top, w=win_rect.width, h=win_rect.height)

        # 2) Charger YAML existant (si présent) pour pré-remplir
        self.room_cfg = None
        if self.yaml_path.exists():
            try:
                self.room_cfg = load_room_config(self.room_name, self.settings)  # :contentReference[oaicite:6]{index=6}
            except Exception:
                self.room_cfg = None

        # 3) UI
        self._build_ui()

        # 4) Image initiale
        self.refresh_image()

        # Raccourcis
        self.bind("<Control-s>", lambda e: self.save_yaml())
        self.bind("<Key-r>", lambda e: self.refresh_image())

    # ---------- UI ----------
    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # Canvas (image + ROIs)
        self.canvas = tk.Canvas(self, bg="#111111", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Side panel
        side = ctk.CTkFrame(self, width=320)
        side.grid(row=0, column=1, sticky="ns")
        side.grid_propagate(False)

        ctk.CTkLabel(side, text="ROIs", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(12, 6))

        self.roi_name = tk.StringVar(value=self.PRESET_NAMES[0])
        ctk.CTkOptionMenu(side, values=self.PRESET_NAMES, variable=self.roi_name).pack(fill="x", padx=12, pady=6)

        self.btn_new = ctk.CTkButton(side, text="➕ Nouveau/Remplacer ROI", command=self._on_new_roi)
        self.btn_new.pack(fill="x", padx=12, pady=(6, 2))

        self.btn_del = ctk.CTkButton(side, text="🗑️ Supprimer ROI", fg_color="#8a1c1c", hover_color="#6f1515",
                                     command=self._on_delete_roi)
        self.btn_del.pack(fill="x", padx=12, pady=2)

        ctk.CTkLabel(side, text="Templates (confirmators)", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(18, 6))
        self.tpl_path = tk.StringVar(value="")
        self.tpl_thr = tk.DoubleVar(value=0.72)
        ctk.CTkButton(side, text="📁 Choisir image template", command=self._on_browse_template).pack(fill="x", padx=12, pady=2)
        ctk.CTkEntry(side, textvariable=self.tpl_path, placeholder_text="templates/<room>/dealer_btn.png").pack(fill="x", padx=12, pady=2)
        ctk.CTkSlider(side, from_=0.5, to=0.95, number_of_steps=45, variable=self.tpl_thr).pack(fill="x", padx=12, pady=(2, 0))
        ctk.CTkLabel(side, textvariable=tk.StringVar(value="Seuil matchTemplate")).pack(pady=(0, 8))
        self.btn_tpl_set = ctk.CTkButton(side, text="📍 Associer template au ROI courant", command=self._on_set_template)
        self.btn_tpl_set.pack(fill="x", padx=12, pady=(2, 8))

        ctk.CTkButton(side, text="🔄 Rafraîchir image (R)", command=self.refresh_image).pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkButton(side, text="💾 Enregistrer YAML (Ctrl+S)", command=self.save_yaml).pack(fill="x", padx=12, pady=4)

        # Liste ROIs existants
        ctk.CTkLabel(side, text="ROIs existants").pack(pady=(12, 4))
        self.roi_list = tk.Listbox(side, height=10)
        self.roi_list.pack(fill="both", expand=False, padx=12, pady=(0, 8))
        self.roi_list.bind("<<ListboxSelect>>", self._on_select_roi_in_list)

        # État
        self.status = ctk.CTkLabel(side, text="Prêt")
        self.status.pack(pady=6)

        # Canvas events (dessin)
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Conteneurs état dessin
        self.image_tk = None
        self.last_img = None
        self.scale = 1.0
        self.rois_px: Dict[str, PxRect] = {}
        self.rect_ids: Dict[str, int] = {}
        self.drag_start: Optional[Tuple[int, int]] = None
        self.preview_rect_id: Optional[int] = None
        self.templates: Dict[str, TemplateConfirmator] = {}

        # Pré-remplir depuis YAML si dispo
        if self.room_cfg:
            for name, roi in self.room_cfg.rois.items():
                px = _px_from_norm({"x": roi.x, "y": roi.y, "w": roi.w, "h": roi.h}, self.win)
                self.rois_px[name] = px
            for t in self.room_cfg.templates_confirmators:
                self.templates[getattr(t, "roi_name", "pot_value")] = t  # compat souple
            self._refresh_roi_list()

    # ---------- Capture/affichage ----------
    def refresh_image(self) -> None:
        img = _grab_rect(self.win)  # BGR
        self.last_img = img
        self._show_img(img)
        self._redraw_rois()
        self.status.configure(text=f"Image rafraîchie — {self.win.w}x{self.win.h}")

    def _show_img(self, bgr: np.ndarray) -> None:
        h, w = bgr.shape[:2]
        # Fit dans le canvas tout en gardant ratio
        can_w = max(100, self.canvas.winfo_width() or 1024)
        can_h = max(100, self.canvas.winfo_height() or 600)
        scale = min(can_w / w, can_h / h)
        self.scale = scale

        resized = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(rgb)
        self.image_tk = ImageTk.PhotoImage(img_pil)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.image_tk)
        self.canvas.config(width=resized.shape[1], height=resized.shape[0])

    def _redraw_rois(self) -> None:
        # Efface anciens rectangles
        for rid in self.rect_ids.values():
            self.canvas.delete(rid)
        self.rect_ids.clear()
        # Dessine tous les ROIs
        for name, px in self.rois_px.items():
            x = int((px.x - self.win.x) * self.scale)
            y = int((px.y - self.win.y) * self.scale)
            w = int(px.w * self.scale)
            h = int(px.h * self.scale)
            rid = self.canvas.create_rectangle(x, y, x + w, y + h, outline="#1db954", width=2)
            self.rect_ids[name] = rid
            self.canvas.create_text(x + 6, y + 10, anchor="w", text=name, fill="#e5e5e5", font=("Arial", 10, "bold"))

    # ---------- Événements dessin ----------
    def _on_mouse_down(self, e) -> None:
        self.drag_start = (e.x, e.y)
        if self.preview_rect_id:
            self.canvas.delete(self.preview_rect_id)
            self.preview_rect_id = None

    def _on_mouse_drag(self, e) -> None:
        if not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = e.x, e.y
        if self.preview_rect_id:
            self.canvas.coords(self.preview_rect_id, x0, y0, x1, y1)
        else:
            self.preview_rect_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="#f59e0b", dash=(4, 2), width=2)

    def _on_mouse_up(self, e) -> None:
        if not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = e.x, e.y
        self.drag_start = None
        if self.preview_rect_id:
            self.canvas.delete(self.preview_rect_id)
            self.preview_rect_id = None
        # Normaliser coord canvas -> pixels fenêtre
        x = min(x0, x1)
        y = min(y0, y1)
        w = abs(x1 - x0)
        h = abs(y1 - y0)
        if w < 5 or h < 5:
            self.status.configure(text="Rectangle trop petit ignoré.")
            return
        # back-project to window pixels
        px = PxRect(
            x=int(self.win.x + x / self.scale),
            y=int(self.win.y + y / self.scale),
            w=int(w / self.scale),
            h=int(h / self.scale),
        )
        # Affecter au nom courant
        name = self.roi_name.get()
        self.rois_px[name] = px
        self._refresh_roi_list()
        self._redraw_rois()
        self.status.configure(text=f"ROI '{name}' défini: {px.w}x{px.h}px")

    def _on_new_roi(self) -> None:
        # Rien à faire: l'utilisateur dessine sur le canvas. Ce bouton sert d’indication UI.
        messagebox.showinfo("Info", "Dessinez un rectangle sur l'image, il sera enregistré sous le nom sélectionné.")

    def _on_delete_roi(self) -> None:
        sel = self.roi_list.curselection()
        if not sel:
            return
        name = self.roi_list.get(sel[0]).split(" ")[0]
        self.rois_px.pop(name, None)
        self._refresh_roi_list()
        self._redraw_rois()

    def _on_browse_template(self) -> None:
        p = filedialog.askopenfilename(
            title="Choisir une image template",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg")]
        )
        if p:
            self.tpl_path.set(os.path.relpath(p, start=self.settings.TEMPLATES_DIR))

    def _on_set_template(self) -> None:
        name = self.roi_name.get()
        if name not in self.rois_px:
            messagebox.showwarning("ROI manquant", "Définissez d'abord le ROI courant en dessinant un rectangle.")
            return
        path_rel = self.tpl_path.get().strip()
        if not path_rel:
            messagebox.showwarning("Template manquant", "Choisissez un fichier image template.")
            return
        self.templates[name] = TemplateConfirmator(
            path=path_rel,
            roi=Roi(**_norm_from_px(self.rois_px[name], self.win)),
            thr=float(self.tpl_thr.get()),
        )
        messagebox.showinfo("OK", f"Template associé au ROI '{name}'.")

    def _on_select_roi_in_list(self, _evt) -> None:
        sel = self.roi_list.curselection()
        if not sel:
            return
        name = self.roi_list.get(sel[0]).split(" ")[0]
        if name in self.rois_px:
            self.roi_name.set(name)

    # ---------- Liste & sauvegarde ----------
    def _refresh_roi_list(self) -> None:
        self.roi_list.delete(0, tk.END)
        for name, px in self.rois_px.items():
            self.roi_list.insert(tk.END, f"{name}  ({px.w}x{px.h}px)")

    def save_yaml(self) -> None:
        # Charger YAML existant si présent
        data = {}
        if self.yaml_path.exists():
            with self.yaml_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

        # Valeurs par défaut
        data.setdefault("room", self.room_name)
        data.setdefault("version", 1)
        data.setdefault("window", {})
        data.setdefault("scaling", {"mode": "normalized", "dpi_compensation": True})
        data.setdefault("anchors", {})
        data.setdefault("rois", {})
        data.setdefault("templates", {"confirmators": []})

        # Injecter/mettre à jour rois
        for name, px in self.rois_px.items():
            data["rois"][name] = _norm_from_px(px, self.win)

        # Injecter templates confirmators (si définis)
        confs = []
        for roi_name, t in self.templates.items():
            confs.append({
                "path": t.path,
                "roi": {"x": t.roi.x, "y": t.roi.y, "w": t.roi.w, "h": t.roi.h},
                "thr": t.thr,
            })
        data["templates"]["confirmators"] = confs

        # Écriture
        self.yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with self.yaml_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

        self.status.configure(text=f"YAML enregistré → {self.yaml_path}")
        messagebox.showinfo("Enregistré", f"YAML mis à jour : {self.yaml_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assistant de calibration des ROIs (coords normalisées).")
    parser.add_argument("--room", choices=["winamax", "pmu"], default="winamax", help="Room à calibrer")
    parser.add_argument("--yaml", type=Path, default=None, help="Chemin YAML à écrire (par défaut rooms/<room>.yaml)")
    args = parser.parse_args()

    settings = AppSettings()  # :contentReference[oaicite:7]{index=7}
    yaml_path = args.yaml or (settings.ROOMS_DIR / f"{args.room}.yaml")
    app = CalibratorApp(room=args.room, yaml_path=yaml_path, settings=settings)
    app.mainloop()


if __name__ == "__main__":
    main()
