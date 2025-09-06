# src/poker_assistant/ocr/table_calibrator.py
# Calibrateur amélioré avec capture de table entière et superposition des zones

from __future__ import annotations

import os
import yaml
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageDraw, ImageFont

try:
    from ..windows.detector import CandidateWindow
    from ..ui.room_selector import choose_table
except Exception:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from poker_assistant.windows.detector import CandidateWindow
    from poker_assistant.ui.room_selector import choose_table


@dataclass
class CardZone:
    """Zone de rang ou couleur dans une carte."""
    name: str
    x: float
    y: float
    w: float
    h: float
    zone_type: str  # "rank" ou "suit"


class TableCalibrator:
    """Calibrateur amélioré avec capture de table entière."""
    
    def __init__(self, yaml_path: str):
        """Initialise le calibrateur avec le chemin du YAML."""
        self.yaml_path = yaml_path
        self.config: Dict[str, Any] = {}
        self.card_rois: Dict[str, Dict[str, float]] = {}
        self.card_zones: Dict[str, List[CardZone]] = {}
        
        # Charge la configuration existante
        self._load_config()
    
    def _load_config(self) -> None:
        """Charge la configuration YAML existante."""
        try:
            with open(self.yaml_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f) or {}
            
            # Récupère les ROIs de cartes
            layouts = self.config.get('layouts', {})
            default_layout = layouts.get('default', {})
            rois = default_layout.get('rois', {})
            
            # Filtre les ROIs de cartes
            card_patterns = ['board_card', 'hero_cards']
            for roi_name, roi_config in rois.items():
                if any(pattern in roi_name for pattern in card_patterns):
                    if isinstance(roi_config, dict):
                        self.card_rois[roi_name] = roi_config
                    else:
                        # Format tuple/list -> convertit en dict
                        x, y, w, h = roi_config
                        self.card_rois[roi_name] = {'x': x, 'y': y, 'w': w, 'h': h}
            
            # Charge les zones existantes
            self._load_existing_zones()
            
            print(f"✅ Configuration chargée: {len(self.card_rois)} cartes détectées")
            for card_name in self.card_rois.keys():
                print(f"  - {card_name}")
                
        except Exception as e:
            print(f"❌ Erreur chargement YAML: {e}")
            self.config = {}
    
    def _load_existing_zones(self) -> None:
        """Charge les zones existantes depuis le YAML."""
        self.card_zones = {}
        
        card_zones_config = self.config.get('card_zones', {})
        for card_name, zones_config in card_zones_config.items():
            zones = []
            for zone_name, zone_config in zones_config.items():
                zone = CardZone(
                    name=zone_name,
                    x=zone_config['x'],
                    y=zone_config['y'],
                    w=zone_config['w'],
                    h=zone_config['h'],
                    zone_type=zone_config.get('type', 'rank')
                )
                zones.append(zone)
            self.card_zones[card_name] = zones
    
    def _save_config(self) -> None:
        """Sauvegarde la configuration étendue dans le YAML."""
        try:
            # Étend la configuration avec les zones de cartes
            if 'card_zones' not in self.config:
                self.config['card_zones'] = {}
            
            # Sauvegarde les zones pour chaque carte
            for card_name, zones in self.card_zones.items():
                if card_name not in self.config['card_zones']:
                    self.config['card_zones'][card_name] = {}
                
                for zone in zones:
                    self.config['card_zones'][card_name][zone.name] = {
                        'x': zone.x,
                        'y': zone.y,
                        'w': zone.w,
                        'h': zone.h,
                        'type': zone.zone_type
                    }
            
            # Sauvegarde avec préservation de la structure
            with open(self.yaml_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, 
                         sort_keys=False, allow_unicode=True)
            
            print(f"✅ Configuration sauvegardée: {len(self.card_zones)} cartes avec zones")
            
        except Exception as e:
            print(f"❌ Erreur sauvegarde YAML: {e}")
            messagebox.showerror("Erreur", f"Impossible de sauvegarder:\n{e}")
    
    def run_calibration(self) -> None:
        """Lance le processus de calibration interactif."""
        if not self.card_rois:
            messagebox.showwarning("Avertissement", 
                                 "Aucune carte détectée dans le YAML.\n"
                                 "Vérifiez que les ROIs de cartes sont bien définies.")
            return
        
        # Sélection de la table
        candidate = choose_table(room_pref=None)
        if not candidate:
            messagebox.showerror("Erreur", "Aucune table sélectionnée")
            return
        
        print(f"✅ Table sélectionnée: {candidate.title}")
        
        # Lance l'interface de calibration
        self._run_calibration_gui(candidate)
    
    def _run_calibration_gui(self, candidate: CandidateWindow) -> None:
        """Interface graphique pour la calibration des zones de cartes."""
        root = tk.Tk()
        root.title(f"Calibration Table Entière - {candidate.title}")
        root.geometry("1400x900")
        
        # Variables
        self.current_card = tk.StringVar()
        self.current_zone_type = tk.StringVar(value="rank")
        self.candidate = candidate
        self.table_image: Optional[Image.Image] = None
        self.display_image: Optional[Image.Image] = None
        self.zones: List[CardZone] = []
        self.drawing_zone = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.root = root
        
        # Interface
        self._build_gui(root)
        
        # Capture la table entière
        self._capture_table()
        
        root.mainloop()
    
    def _build_gui(self, root: tk.Tk) -> None:
        """Construit l'interface graphique."""
        # Panneau de contrôle
        control_frame = ttk.Frame(root)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        # Sélection de carte
        ttk.Label(control_frame, text="Carte:").pack(side="left")
        card_combo = ttk.Combobox(control_frame, textvariable=self.current_card, 
                                 values=list(self.card_rois.keys()), state="readonly")
        card_combo.pack(side="left", padx=(5, 20))
        card_combo.bind("<<ComboboxSelected>>", lambda e: self._select_card())
        
        # Type de zone
        ttk.Label(control_frame, text="Zone:").pack(side="left")
        zone_combo = ttk.Combobox(control_frame, textvariable=self.current_zone_type,
                                 values=["rank", "suit"], state="readonly")
        zone_combo.pack(side="left", padx=(5, 20))
        
        # Boutons
        ttk.Button(control_frame, text="Capturer Table", 
                  command=self._capture_table).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Forcer Capture", 
                  command=self._force_capture).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Ajouter Zone", 
                  command=self._add_zone).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Supprimer Dernière", 
                  command=self._remove_last_zone).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Sauvegarder Carte", 
                  command=self._save_current_card).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Sauvegarder Tout", 
                  command=self._save_all).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Résumé Zones", 
                  command=self._show_zones_summary).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Vider Zones", 
                  command=self._clear_all_zones).pack(side="left", padx=5)
        
        # Zone d'affichage
        self.image_frame = ttk.Frame(root)
        self.image_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Canvas pour l'image avec scrollbars
        canvas_frame = ttk.Frame(self.image_frame)
        canvas_frame.pack(fill="both", expand=True)
        
        self.canvas = tk.Canvas(canvas_frame, bg="white", width=1200, height=800)
        
        # Scrollbars
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        
        self.canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)
        
        # Placement
        self.canvas.grid(row=0, column=0, sticky="nsew")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        # Panneau d'informations
        info_frame = ttk.Frame(root)
        info_frame.pack(fill="x", padx=10, pady=5)
        
        self.info_label = ttk.Label(info_frame, text="Capturez la table pour commencer")
        self.info_label.pack(side="left")
        
        # Bindings
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        
        # Charge la première carte
        if self.card_rois:
            first_card = list(self.card_rois.keys())[0]
            self.current_card.set(first_card)
    
    def _capture_table(self) -> None:
        """Capture l'image de la table entière."""
        try:
            import mss
            import win32gui
            import win32con
            import time
            
            self.info_label.config(text="Capture de la table en cours...")
            self.root.update()
            
            # Récupère le handle de la fenêtre
            hwnd = self.candidate.handle
            if not hwnd:
                raise Exception("Handle de fenêtre non disponible")
            
            print(f"🔍 Handle de fenêtre: {hwnd}")
            
            # Force la fenêtre au premier plan et la restaure
            try:
                # Restaure la fenêtre si elle est minimisée
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)
                
                # Met la fenêtre au premier plan
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.1)
                
                # Force le focus
                win32gui.SetFocus(hwnd)
                time.sleep(0.2)
                
                print("✅ Fenêtre mise au premier plan")
            except Exception as e:
                print(f"⚠️ Impossible de mettre au premier plan: {e}")
            
            # Masque temporairement notre fenêtre de calibration
            self.root.withdraw()
            self.root.update()
            time.sleep(0.3)  # Attend que la fenêtre soit masquée
            
            try:
                # Récupère le client rect
                client_rect = win32gui.GetClientRect(hwnd)
                client_x, client_y, client_w, client_h = client_rect
                print(f"📐 Client rect: {client_rect}")
                
                # Convertit en coordonnées écran
                point = win32gui.ClientToScreen(hwnd, (0, 0))
                screen_x, screen_y = point
                print(f"📍 Coordonnées écran: ({screen_x}, {screen_y})")
                
                # Essaie d'abord PrintWindow (plus fiable pour les fenêtres spécifiques)
                try:
                    self.table_image = self._capture_with_printwindow(hwnd, client_w, client_h)
                    if self.table_image:
                        print(f"✅ Table capturée avec PrintWindow: {self.table_image.size}")
                    else:
                        raise Exception("PrintWindow a échoué")
                except Exception as e:
                    print(f"⚠️ PrintWindow échoué: {e}")
                    # Fallback vers MSS
                    with mss.mss() as sct:
                        monitor = {
                            "left": screen_x,
                            "top": screen_y,
                            "width": client_w,
                            "height": client_h
                        }
                        print(f"📷 Capture MSS: {monitor}")
                        screenshot = sct.grab(monitor)
                        self.table_image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                    
                    print(f"✅ Table capturée avec MSS: {self.table_image.size}")
                
            finally:
                # Restaure notre fenêtre de calibration
                self.root.deiconify()
                self.root.update()
                time.sleep(0.1)
            
            # Affiche la table avec les zones superposées
            self._display_table_with_zones()
            
            self.info_label.config(text=f"✅ Table capturée: {self.table_image.size}")
            
        except Exception as e:
            print(f"❌ Erreur capture table: {e}")
            self.info_label.config(text=f"❌ Erreur capture: {e}")
            messagebox.showerror("Erreur", f"Impossible de capturer la table:\n{e}")
            
            # S'assure que notre fenêtre est restaurée en cas d'erreur
            try:
                self.root.deiconify()
            except:
                pass
    
    def _force_capture(self) -> None:
        """Force la capture avec des délais plus longs."""
        try:
            import win32gui
            import win32con
            import time
            
            self.info_label.config(text="Capture forcée en cours...")
            self.root.update()
            
            hwnd = self.candidate.handle
            if not hwnd:
                raise Exception("Handle de fenêtre non disponible")
            
            # Force la fenêtre au premier plan avec des délais plus longs
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.5)
                
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.5)
                
                print("✅ Fenêtre forcée au premier plan")
            except Exception as e:
                print(f"⚠️ Impossible de forcer au premier plan: {e}")
            
            # Masque notre fenêtre plus longtemps
            self.root.withdraw()
            self.root.update()
            time.sleep(1.0)  # Délai plus long
            
            try:
                # Capture avec MSS uniquement (plus fiable)
                import mss
                
                client_rect = win32gui.GetClientRect(hwnd)
                client_w, client_h = client_rect[2], client_rect[3]
                
                point = win32gui.ClientToScreen(hwnd, (0, 0))
                screen_x, screen_y = point
                
                with mss.mss() as sct:
                    monitor = {
                        "left": screen_x,
                        "top": screen_y,
                        "width": client_w,
                        "height": client_h
                    }
                    print(f"📷 Capture forcée MSS: {monitor}")
                    screenshot = sct.grab(monitor)
                    self.table_image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                print(f"✅ Table capturée avec capture forcée: {self.table_image.size}")
                
            finally:
                # Restaure notre fenêtre
                self.root.deiconify()
                self.root.update()
                time.sleep(0.2)
            
            # Affiche la table
            self._display_table_with_zones()
            
            self.info_label.config(text=f"✅ Capture forcée réussie: {self.table_image.size}")
            
        except Exception as e:
            print(f"❌ Erreur capture forcée: {e}")
            self.info_label.config(text=f"❌ Erreur capture forcée: {e}")
            messagebox.showerror("Erreur", f"Impossible de forcer la capture:\n{e}")
            
            try:
                self.root.deiconify()
            except:
                pass
    
    def _capture_with_printwindow(self, hwnd: int, width: int, height: int) -> Optional[Image.Image]:
        """Capture une fenêtre avec PrintWindow (plus fiable)."""
        try:
            import win32gui
            import win32ui
            import win32con
            
            # Crée un device context pour la fenêtre
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            # Crée un bitmap
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # Capture avec BitBlt (alternative à PrintWindow)
            result = win32gui.BitBlt(saveDC.GetSafeHdc(), 0, 0, width, height, 
                                    hwndDC, 0, 0, win32con.SRCCOPY)
            
            if result:
                # Convertit en PIL Image
                bmpinfo = saveBitMap.GetInfo()
                bmpstr = saveBitMap.GetBitmapBits(True)
                
                # Crée l'image PIL
                img = Image.frombuffer(
                    'RGB',
                    (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                    bmpstr, 'raw', 'BGRX', 0, 1
                )
                
                # Nettoie
                win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                win32gui.ReleaseDC(hwnd, hwndDC)
                
                return img
            else:
                # Nettoie en cas d'échec
                win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                win32gui.ReleaseDC(hwnd, hwndDC)
                return None
                
        except Exception as e:
            print(f"❌ Erreur PrintWindow: {e}")
            return None
    
    def _display_table_with_zones(self) -> None:
        """Affiche la table avec les zones superposées."""
        if not self.table_image:
            return
        
        try:
            # Crée une copie de l'image pour l'affichage
            self.display_image = self.table_image.copy()
            draw = ImageDraw.Draw(self.display_image)
            
            # Dessine les ROIs de cartes
            self._draw_card_rois(draw)
            
            # Dessine les zones existantes
            self._draw_existing_zones(draw)
            
            # Convertit pour Tkinter
            self.photo = ImageTk.PhotoImage(self.display_image)
            
            # Affiche dans le canvas
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
            
            # Configure le scroll region
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            
            print(f"✅ Table affichée avec zones: {self.display_image.size}")
            
        except Exception as e:
            print(f"❌ Erreur affichage table: {e}")
            messagebox.showerror("Erreur", f"Impossible d'afficher la table:\n{e}")
    
    def _draw_card_rois(self, draw: ImageDraw.Draw) -> None:
        """Dessine les ROIs de cartes sur l'image."""
        client_size = self.config.get('client_size', {'w': 1376, 'h': 1040})
        client_w, client_h = client_size['w'], client_size['h']
        
        for card_name, roi_config in self.card_rois.items():
            # Convertit en pixels
            roi_x = int(roi_config['x'] * client_w)
            roi_y = int(roi_config['y'] * client_h)
            roi_w = int(roi_config['w'] * client_w)
            roi_h = int(roi_config['h'] * client_h)
            
            # Dessine le rectangle de la carte
            draw.rectangle([roi_x, roi_y, roi_x + roi_w, roi_y + roi_h], 
                          outline="blue", width=2)
            
            # Ajoute le nom de la carte
            try:
                font = ImageFont.truetype("arial.ttf", 12)
            except:
                font = ImageFont.load_default()
            
            draw.text((roi_x + 5, roi_y + 5), card_name, fill="blue", font=font)
    
    def _draw_existing_zones(self, draw: ImageDraw.Draw) -> None:
        """Dessine les zones existantes sur l'image."""
        client_size = self.config.get('client_size', {'w': 1376, 'h': 1040})
        client_w, client_h = client_size['w'], client_size['h']
        
        current_card = self.current_card.get()
        
        for card_name, zones in self.card_zones.items():
            if card_name not in self.card_rois:
                continue
            
            # Récupère la ROI de la carte
            roi_config = self.card_rois[card_name]
            roi_x = int(roi_config['x'] * client_w)
            roi_y = int(roi_config['y'] * client_h)
            roi_w = int(roi_config['w'] * client_w)
            roi_h = int(roi_config['h'] * client_h)
            
            # Mise en évidence de la carte sélectionnée
            if card_name == current_card:
                # Dessine un cadre épais autour de la carte sélectionnée
                draw.rectangle([roi_x - 3, roi_y - 3, roi_x + roi_w + 3, roi_y + roi_h + 3], 
                              outline="yellow", width=4)
            
            # Dessine les zones de cette carte
            for i, zone in enumerate(zones):
                # Convertit les coordonnées normalisées en pixels absolus
                zone_x = roi_x + int(zone.x * roi_w)
                zone_y = roi_y + int(zone.y * roi_h)
                zone_w = int(zone.w * roi_w)
                zone_h = int(zone.h * roi_h)
                
                # Couleur selon le type
                color = "red" if zone.zone_type == "rank" else "green"
                
                # Épaisseur différente selon si c'est la carte sélectionnée
                width = 3 if card_name == current_card else 2
                
                # Style différent selon si c'est la carte sélectionnée
                dash_pattern = None if card_name == current_card else (5, 5)
                
                # Dessine la zone
                draw.rectangle([zone_x, zone_y, zone_x + zone_w, zone_y + zone_h], 
                              outline=color, width=width)
                
                # Ajoute le nom de la zone
                try:
                    font = ImageFont.truetype("arial.ttf", 10)
                except:
                    font = ImageFont.load_default()
                
                # Label avec état de la zone
                if card_name == current_card:
                    zone_label = f"✓ {zone.zone_type}"
                    status_color = "white"
                else:
                    zone_label = f"{zone.zone_type}"
                    status_color = color
                
                draw.text((zone_x + 2, zone_y + 2), zone_label, 
                         fill=status_color, font=font)
                
                # Ajoute un indicateur de complétude
                if card_name == current_card:
                    completion_text = "ACTIF"
                    draw.text((zone_x + 2, zone_y + 15), completion_text, 
                             fill="yellow", font=font)
    
    def _select_card(self) -> None:
        """Sélectionne une carte et charge ses zones."""
        card_name = self.current_card.get()
        if not card_name or card_name not in self.card_rois:
            return
        
        # Charge les zones existantes pour cette carte
        self.zones = self.card_zones.get(card_name, []).copy()
        
        # Compte les zones par type
        rank_count = sum(1 for zone in self.zones if zone.zone_type == "rank")
        suit_count = sum(1 for zone in self.zones if zone.zone_type == "suit")
        
        self.info_label.config(text=f"Carte: {card_name} | Rank: {rank_count}/1 | Suit: {suit_count}/1")
        
        # Redessine l'image avec mise en évidence de la carte sélectionnée
        if self.table_image:
            self._display_table_with_zones()
    
    def _on_canvas_click(self, event) -> None:
        """Gestion du clic sur le canvas."""
        if not self.table_image:
            return
        
        # Convertit les coordonnées du canvas en coordonnées de l'image
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        self.drag_start_x = canvas_x
        self.drag_start_y = canvas_y
        self.drawing_zone = True
    
    def _on_canvas_drag(self, event) -> None:
        """Gestion du drag sur le canvas."""
        if not self.drawing_zone or not self.table_image:
            return
        
        # Supprime le rectangle temporaire
        self.canvas.delete("temp_rect")
        
        # Convertit les coordonnées
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        # Dessine le rectangle temporaire
        self.canvas.create_rectangle(self.drag_start_x, self.drag_start_y, 
                                   canvas_x, canvas_y, outline="yellow", width=2, tags="temp_rect")
    
    def _on_canvas_release(self, event) -> None:
        """Gestion du relâchement sur le canvas."""
        if not self.drawing_zone or not self.table_image:
            return
        
        self.drawing_zone = False
        
        # Convertit les coordonnées
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        # Supprime le rectangle temporaire
        self.canvas.delete("temp_rect")
        
        # Vérifie si le clic est dans une carte
        card_name = self._get_card_at_position(canvas_x, canvas_y)
        if not card_name:
            messagebox.showwarning("Avertissement", "Cliquez sur une carte pour ajouter une zone")
            return
        
        # Calcule les coordonnées normalisées en utilisant le rectangle dessiné
        norm_coords = self._get_normalized_coords_from_rectangle(card_name, 
                                                               self.drag_start_x, self.drag_start_y,
                                                               canvas_x, canvas_y)
        if not norm_coords:
            return
        
        # Gère la création/mise à jour de zone avec limitation à 2 zones par carte
        self._create_or_update_zone(card_name, norm_coords)
    
    def _get_normalized_coords_from_rectangle(self, card_name: str, 
                                            start_x: float, start_y: float,
                                            end_x: float, end_y: float) -> Optional[Dict[str, float]]:
        """Calcule les coordonnées normalisées à partir du rectangle dessiné."""
        if card_name not in self.card_rois:
            return None
        
        roi_config = self.card_rois[card_name]
        client_size = self.config.get('client_size', {'w': 1376, 'h': 1040})
        client_w, client_h = client_size['w'], client_size['h']
        
        # Convertit la ROI en pixels
        roi_x = int(roi_config['x'] * client_w)
        roi_y = int(roi_config['y'] * client_h)
        roi_w = int(roi_config['w'] * client_w)
        roi_h = int(roi_config['h'] * client_h)
        
        # Calcule les dimensions du rectangle dessiné
        rect_x = min(start_x, end_x)
        rect_y = min(start_y, end_y)
        rect_w = abs(end_x - start_x)
        rect_h = abs(end_y - start_y)
        
        # Vérifie que le rectangle a une taille minimale
        if rect_w < 5 or rect_h < 5:
            messagebox.showwarning("Zone trop petite", "Dessinez un rectangle plus grand")
            return None
        
        # Calcule les coordonnées relatives à la carte
        rel_x = rect_x - roi_x
        rel_y = rect_y - roi_y
        
        # Normalise les coordonnées
        norm_x = rel_x / roi_w
        norm_y = rel_y / roi_h
        norm_w = rect_w / roi_w
        norm_h = rect_h / roi_h
        
        # S'assure que les coordonnées sont dans les limites de la carte
        norm_x = max(0, min(norm_x, 1))
        norm_y = max(0, min(norm_y, 1))
        norm_w = max(0.01, min(norm_w, 1 - norm_x))  # Minimum 1% de largeur
        norm_h = max(0.01, min(norm_h, 1 - norm_y))  # Minimum 1% de hauteur
        
        print(f"📐 Rectangle dessiné: ({rect_x:.0f}, {rect_y:.0f}, {rect_w:.0f}, {rect_h:.0f})")
        print(f"📐 Coordonnées normalisées: ({norm_x:.3f}, {norm_y:.3f}, {norm_w:.3f}, {norm_h:.3f})")
        
        return {
            'x': norm_x,
            'y': norm_y,
            'w': norm_w,
            'h': norm_h
        }
    
    def _create_or_update_zone(self, card_name: str, norm_coords: Dict[str, float]) -> None:
        """Crée ou met à jour une zone pour une carte donnée."""
        zone_type = self.current_zone_type.get()
        
        # Initialise les zones pour cette carte si nécessaire
        if card_name not in self.card_zones:
            self.card_zones[card_name] = []
        
        # Cherche une zone existante du même type
        existing_zone = None
        for zone in self.card_zones[card_name]:
            if zone.zone_type == zone_type:
                existing_zone = zone
                break
        
        if existing_zone:
            # Met à jour la zone existante
            existing_zone.x = norm_coords['x']
            existing_zone.y = norm_coords['y']
            existing_zone.w = norm_coords['w']
            existing_zone.h = norm_coords['h']
            
            print(f"🔄 Zone '{existing_zone.name}' mise à jour pour {card_name}: ({existing_zone.x:.3f}, {existing_zone.y:.3f}, {existing_zone.w:.3f}, {existing_zone.h:.3f})")
            self.info_label.config(text=f"🔄 Zone {zone_type} mise à jour pour {card_name}")
            
        else:
            # Vérifie la limite de 2 zones par carte
            if len(self.card_zones[card_name]) >= 2:
                messagebox.showwarning("Limite atteinte", 
                                     f"Maximum 2 zones par carte (Rank + Suit).\n{card_name} a déjà {len(self.card_zones[card_name])} zones.")
                return
            
            # Crée une nouvelle zone
            zone_name = f"{zone_type}_{len(self.card_zones[card_name]) + 1}"
            zone = CardZone(
                name=zone_name,
                x=norm_coords['x'],
                y=norm_coords['y'],
                w=norm_coords['w'],
                h=norm_coords['h'],
                zone_type=zone_type
            )
            
            self.card_zones[card_name].append(zone)
            
            print(f"✅ Nouvelle zone '{zone.name}' créée pour {card_name}: ({zone.x:.3f}, {zone.y:.3f}, {zone.w:.3f}, {zone.h:.3f})")
            self.info_label.config(text=f"✅ Zone {zone_type} créée pour {card_name}")
        
        # Met à jour les zones de la carte sélectionnée pour l'affichage
        self.zones = self.card_zones[card_name].copy()
        
        # Redessine l'image avec les zones mises à jour
        self._display_table_with_zones()
    
    def _get_card_at_position(self, x: float, y: float) -> Optional[str]:
        """Retourne le nom de la carte à la position donnée."""
        client_size = self.config.get('client_size', {'w': 1376, 'h': 1040})
        client_w, client_h = client_size['w'], client_size['h']
        
        for card_name, roi_config in self.card_rois.items():
            roi_x = int(roi_config['x'] * client_w)
            roi_y = int(roi_config['y'] * client_h)
            roi_w = int(roi_config['w'] * client_w)
            roi_h = int(roi_config['h'] * client_h)
            
            if roi_x <= x <= roi_x + roi_w and roi_y <= y <= roi_y + roi_h:
                return card_name
        
        return None
    
    def _get_normalized_coords(self, card_name: str, x: float, y: float) -> Optional[Dict[str, float]]:
        """Calcule les coordonnées normalisées par rapport à la carte."""
        if card_name not in self.card_rois:
            return None
        
        roi_config = self.card_rois[card_name]
        client_size = self.config.get('client_size', {'w': 1376, 'h': 1040})
        client_w, client_h = client_size['w'], client_size['h']
        
        # Convertit la ROI en pixels
        roi_x = int(roi_config['x'] * client_w)
        roi_y = int(roi_config['y'] * client_h)
        roi_w = int(roi_config['w'] * client_w)
        roi_h = int(roi_config['h'] * client_h)
        
        # Calcule les coordonnées relatives à la carte
        rel_x = x - roi_x
        rel_y = y - roi_y
        
        # Normalise
        norm_x = rel_x / roi_w
        norm_y = rel_y / roi_h
        
        # Calcule la taille de la zone (petite zone par défaut)
        zone_size = 0.1  # 10% de la carte
        
        return {
            'x': max(0, min(norm_x - zone_size/2, 1 - zone_size)),
            'y': max(0, min(norm_y - zone_size/2, 1 - zone_size)),
            'w': zone_size,
            'h': zone_size
        }
    
    def _add_zone(self) -> None:
        """Ajoute une zone manuellement."""
        card_name = self.current_card.get()
        if not card_name:
            messagebox.showwarning("Avertissement", "Sélectionnez d'abord une carte")
            return
        
        zone_name = tk.simpledialog.askstring("Nouvelle Zone", "Nom de la zone:")
        if not zone_name:
            return
        
        zone_type = self.current_zone_type.get()
        
        # Demande les coordonnées
        coords_str = tk.simpledialog.askstring("Coordonnées", 
                                          "Coordonnées (x,y,w,h) normalisées (0.0-1.0):")
        if not coords_str:
            return
        
        try:
            coords = [float(x.strip()) for x in coords_str.split(',')]
            if len(coords) != 4:
                raise ValueError("4 coordonnées requises")
            
            zone = CardZone(
                name=zone_name,
                x=coords[0],
                y=coords[1],
                w=coords[2],
                h=coords[3],
                zone_type=zone_type
            )
            
            self.zones.append(zone)
            self._display_table_with_zones()
            self.info_label.config(text=f"Carte: {card_name} | Zones: {len(self.zones)}")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Coordonnées invalides:\n{e}")
    
    def _remove_last_zone(self) -> None:
        """Supprime la dernière zone ajoutée."""
        if self.zones:
            self.zones.pop()
            self._display_table_with_zones()
            card_name = self.current_card.get()
            self.info_label.config(text=f"Carte: {card_name} | Zones: {len(self.zones)}")
    
    def _save_current_card(self) -> None:
        """Sauvegarde les zones de la carte actuelle."""
        card_name = self.current_card.get()
        if not card_name:
            return
        
        # Stocke les zones pour cette carte
        self.card_zones[card_name] = self.zones.copy()
        
        messagebox.showinfo("Sauvegardé", f"Zones sauvegardées pour {card_name}")
    
    def _save_all(self) -> None:
        """Sauvegarde toutes les zones dans le YAML."""
        # Sauvegarde la carte actuelle
        self._save_current_card()
        
        # Sauvegarde dans le fichier
        self._save_config()
        
        messagebox.showinfo("Sauvegardé", "Toutes les zones ont été sauvegardées dans le YAML")
    
    def _show_zones_summary(self) -> None:
        """Affiche un résumé de toutes les zones créées."""
        summary = "=== RÉSUMÉ DES ZONES CRÉÉES ===\n\n"
        
        total_zones = 0
        for card_name, zones in self.card_zones.items():
            if zones:
                summary += f"🃏 {card_name}:\n"
                rank_zones = [z for z in zones if z.zone_type == "rank"]
                suit_zones = [z for z in zones if z.zone_type == "suit"]
                
                for zone in rank_zones:
                    summary += f"  🔴 Rank: ({zone.x:.3f}, {zone.y:.3f}, {zone.w:.3f}, {zone.h:.3f})\n"
                for zone in suit_zones:
                    summary += f"  🟢 Suit: ({zone.x:.3f}, {zone.y:.3f}, {zone.w:.3f}, {zone.h:.3f})\n"
                
                # Indicateur de complétude
                if len(rank_zones) == 1 and len(suit_zones) == 1:
                    summary += "  ✅ COMPLET (Rank + Suit)\n"
                elif len(rank_zones) == 1:
                    summary += "  ⚠️ Manque Suit\n"
                elif len(suit_zones) == 1:
                    summary += "  ⚠️ Manque Rank\n"
                else:
                    summary += "  ❌ Incomplet\n"
                
                summary += "\n"
                total_zones += len(zones)
        
        if total_zones == 0:
            summary += "❌ Aucune zone créée pour le moment.\n\n"
            summary += "Instructions:\n"
            summary += "1. Sélectionnez une carte dans la liste\n"
            summary += "2. Choisissez le type de zone (rank ou suit)\n"
            summary += "3. Cliquez-glissez sur la carte pour créer une zone\n"
            summary += "4. Les zones seront automatiquement sauvegardées"
        else:
            summary += f"✅ Total: {total_zones} zones créées\n\n"
            summary += "💡 Les zones sont automatiquement sauvegardées.\n"
            summary += "💡 Utilisez 'Sauvegarder Tout' pour écrire dans le YAML."
        
        # Affiche dans une fenêtre de dialogue
        from tkinter import scrolledtext
        
        summary_window = tk.Toplevel(self.root)
        summary_window.title("Résumé des Zones")
        summary_window.geometry("600x400")
        
        text_widget = scrolledtext.ScrolledText(summary_window, wrap=tk.WORD, width=70, height=20)
        text_widget.pack(fill="both", expand=True, padx=10, pady=10)
        text_widget.insert("1.0", summary)
        text_widget.config(state="disabled")
        
        # Bouton de fermeture
        ttk.Button(summary_window, text="Fermer", 
                  command=summary_window.destroy).pack(pady=10)
    
    def _clear_all_zones(self) -> None:
        """Vide toutes les zones créées."""
        if not self.card_zones:
            messagebox.showinfo("Vider Zones", "Aucune zone à vider.")
            return
        
        # Confirmation
        result = messagebox.askyesno("Confirmer", 
                                   f"Voulez-vous vraiment vider toutes les {sum(len(zones) for zones in self.card_zones.values())} zones créées ?")
        
        if result:
            # Vide toutes les zones
            self.card_zones.clear()
            self.zones.clear()
            
            # Redessine l'image sans zones
            self._display_table_with_zones()
            
            # Met à jour l'interface
            self.info_label.config(text="Toutes les zones ont été vidées")
            
            print("🗑️ Toutes les zones ont été vidées")
            messagebox.showinfo("Vider Zones", "Toutes les zones ont été vidées avec succès.")


def run_table_calibrator(yaml_path: str) -> None:
    """Fonction principale pour lancer le calibrateur de table."""
    calibrator = TableCalibrator(yaml_path)
    calibrator.run_calibration()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        yaml_path = sys.argv[1]
    else:
        yaml_path = "src/poker_assistant/rooms/winamax.yaml"
    
    run_table_calibrator(yaml_path)
