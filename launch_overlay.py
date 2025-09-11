# -*- coding: utf-8 -*-
"""
Lance le HUD avec tkinter simple (compatible) :
1) détecte les fenêtres de table,
2) sélection via petite popup,
3) démarre le provider (pipeline),
4) affiche l'overlay avec animation de chargement.
"""
import threading
import time
from typing import List, Dict, Optional

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

# === Imports projet existant ===
from poker_assistant.state.model import HandState, infer_street  # Modèles de données

# Détection de table
from poker_assistant.windows import detector

# Pipeline de reconnaissance
from poker_assistant.ocr import card_recognition, text_recognition
from poker_assistant.ocr.capture import ScreenCapture

# Strategy (avec gestion d'erreur pour requests)
try:
    from poker_assistant.strategy.engine import ask_policy
    STRATEGY_AVAILABLE = True
except ImportError:
    print("⚠️ Module strategy non disponible (requests manquant)")
    STRATEGY_AVAILABLE = False
    def ask_policy(state):
        return {"action": "fold", "size_bb": None, "confidence": 0.5, "reason": "Strategy unavailable"}

# Overlay CustomTkinter moderne
try:
    from poker_assistant.ui.overlay import PokerHUD as ModernPokerHUD
    MODERN_OVERLAY_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Overlay moderne non disponible: {e}")
    MODERN_OVERLAY_AVAILABLE = False

# === Bus de snapshots (dernier paquet seulement) ==============================
class SnapshotBus:
    """Bus thread-safe qui conserve uniquement le dernier snapshot publié.

    Fournit une lecture O(1) du paquet le plus récent pour éviter tout backlog
    entre les producteurs (workers) et le consommateur (UI overlay).
    """

    def __init__(self):
        self._snap: Optional[Dict] = None
        self._ts: float = 0.0
        self._lock = threading.Lock()

    def publish(self, snap: Dict) -> None:
        with self._lock:
            self._snap = snap
            self._ts = time.monotonic()

    def get(self) -> (Optional[Dict], float):
        with self._lock:
            return self._snap, self._ts

# === Sélection de fenêtre ======================================================
def select_table_dialog(candidates: List) -> Optional:
    """
    candidates: List[CandidateWindow] - liste des fenêtres candidates
    """
    print(f"🔍 Ouverture du dialogue de sélection avec {len(candidates)} tables")
    selected = {"value": None}

    app = ctk.CTk()
    app.title("Sélection de la table")
    app.geometry("500x400")
    app.resizable(False, False)
    
    # Centrer la fenêtre
    app.update_idletasks()
    x = (app.winfo_screenwidth() // 2) - (500 // 2)
    y = (app.winfo_screenheight() // 2) - (400 // 2)
    app.geometry(f"500x400+{x}+{y}")
    
    # Forcer la fenêtre au premier plan
    app.lift()
    app.attributes('-topmost', True)
    app.after(100, lambda: app.attributes('-topmost', False))
    
    # Titre
    title_label = ctk.CTkLabel(app, text="Sélectionnez une table :", font=("Inter", 16, "bold"))
    title_label.pack(pady=(20, 10))
    
    # Instructions
    instruction_label = ctk.CTkLabel(app, text="Double-cliquez sur une table ou sélectionnez puis cliquez 'Valider'", font=("Inter", 12))
    instruction_label.pack(pady=(0, 10))
    
    # Frame pour la liste
    list_frame = ctk.CTkFrame(app)
    list_frame.pack(padx=20, pady=10, fill="both", expand=True)
    
    # Liste des tables avec scrollbar
    listbox = tk.Listbox(list_frame, width=70, height=10, bg='#2b2b2b', fg='white', 
                        selectbackground='#0078d4', font=("Consolas", 11))
    scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
    listbox.configure(yscrollcommand=scrollbar.set)
    
    listbox.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
    scrollbar.pack(side="right", fill="y", pady=10)
    
    for i, c in enumerate(candidates):
        display_text = f"{i+1}. {c.title}\n   Score: {c.score:.2f} | Room: {c.room_guess or 'Unknown'}"
        listbox.insert(i, display_text)
    
    # Sélection par défaut du premier élément
    if candidates:
        listbox.selection_set(0)
        listbox.see(0)
    
    # Double-clic pour valider
    def _on_double_click(event):
        _ok()
    
    listbox.bind("<Double-Button-1>", _on_double_click)

    def _ok():
        selection = listbox.curselection()
        if selection:
            selected["value"] = candidates[selection[0]]
            print(f"✅ Table sélectionnée: {candidates[selection[0]].title}")
        else:
            print("⚠️ Aucune sélection dans la liste")
        app.destroy()

    def _cancel():
        selected["value"] = None
        print("❌ Sélection annulée")
        app.destroy()

    # Frame pour les boutons
    button_frame = ctk.CTkFrame(app, fg_color="transparent")
    button_frame.pack(pady=30, padx=20)
    
    # Boutons
    ok_button = ctk.CTkButton(button_frame, text="✅ Valider", command=_ok, width=140, height=40, font=("Inter", 14, "bold"))
    ok_button.pack(side="left", padx=(0, 15))
    
    cancel_button = ctk.CTkButton(button_frame, text="❌ Annuler", command=_cancel, width=140, height=40, fg_color="gray", font=("Inter", 14))
    cancel_button.pack(side="left")
    
    # Gestion de la fermeture
    app.protocol("WM_DELETE_WINDOW", _cancel)
    
    print("🖥️ Affichage de la fenêtre de sélection...")
    app.mainloop()
    print("🖥️ Fenêtre de sélection fermée")
    
    return selected["value"]

# === Provider hybride (simulation + vraie reconnaissance) ===================
class HybridProvider:
    """
    Provider qui combine simulation et vraie reconnaissance.
    Commence par des données simulées, puis essaie d'intégrer la vraie reconnaissance.
    """
    def __init__(self, handle: int):
        self._ready = False
        self._last_state: Optional[HandState] = None
        self._stop = False
        self._handle = handle
        self._use_real_recognition = False
        # Bus de snapshots (dernier paquet seulement)
        self._bus = SnapshotBus()
        self._last_ts_published: float = 0.0
        # Cache policy non-bloquant
        self._last_policy: Dict = {}
        
        # Tentative d'initialisation des pipelines
        self._init_pipelines()
        
        # Thread de reconnaissance
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _init_pipelines(self):
        """Initialise les pipelines de reconnaissance."""
        try:
            # Capture d'écran
            self.capture = ScreenCapture()
            print("✅ Capture d'écran initialisée")
            
            # Tentative de reconnaissance de cartes
            try:
                self.card_pipeline = card_recognition.CardRecognitionPipeline(
                    yaml_path="src/poker_assistant/rooms/winamax.yaml",
                    templates_dir="assets/templates"
                )
                print("✅ Pipeline de reconnaissance de cartes initialisé")
                print("🃏 Reconnaissance de cartes activée - recherche des cartes Hero et Board...")
            except Exception as e:
                print(f"⚠️ Erreur pipeline cartes: {e}")
                self.card_pipeline = None
            
            # Tentative d'OCR texte
            try:
                self.text_ocr = text_recognition.TextRecognitionPipeline(
                    yaml_path="src/poker_assistant/rooms/winamax.yaml"
                )
                print("✅ Pipeline OCR initialisé")
            except Exception as e:
                print(f"⚠️ Erreur pipeline OCR: {e}")
                self.text_ocr = None
            
            # Si au moins un pipeline fonctionne, on active la vraie reconnaissance
            if self.card_pipeline or self.text_ocr:
                self._use_real_recognition = True
                print("✅ Mode reconnaissance hybride activé")
            else:
                print("⚠️ Mode simulation uniquement")
            
        except Exception as e:
            print(f"❌ Erreur initialisation pipelines: {e}")
            self._use_real_recognition = False

    def _worker(self):
        """Thread principal de reconnaissance."""
        # Laisse le pipeline s'initialiser
        time.sleep(2.0)
        self._ready = True
        
        print("🔄 Démarrage de la reconnaissance...")
        
        # Compteur pour les données simulées
        sim_counter = 0
        
        # Boucle de reconnaissance
        while not self._stop:
            try:
                if self._use_real_recognition:
                    # Tentative de vraie reconnaissance
                    state = self._try_real_recognition()
                    if not state:
                        state = self._get_simulated_state(sim_counter)
                else:
                    # Mode simulation uniquement
                    state = self._get_simulated_state(sim_counter)

                # Publier un snapshot dès que l'état est prêt (avant policy)
                self._last_state = state
                self._publish_snapshot()

                # Calcul policy côté worker (évite de bloquer l'UI)
                policy: Dict = {}
                try:
                    if STRATEGY_AVAILABLE and state is not None:
                        policy = ask_policy(state) or {}
                except Exception as _e:
                    policy = {}

                # Mettre à jour le cache policy
                self._last_policy = policy or {}

                # Publier à nouveau après calcul de policy
                self._publish_snapshot()
                
                sim_counter += 1
                    
            except Exception as e:
                print(f"⚠️ Erreur dans _worker: {e}")
                
            time.sleep(0.5)  # 2 FPS - Plus réactif pour voir les cartes

    def _try_real_recognition(self) -> Optional[HandState]:
        """Tente la vraie reconnaissance."""
        try:
            # Capture de l'écran
            img = self.capture.capture_window(self._handle)
            if img is None:
                return None
            
            card_results = {}
            text_results = {}
            
            # Reconnaissance des cartes si disponible
            if self.card_pipeline:
                try:
                    recognition_frame = self.card_pipeline.recognize_cards(img)
                    hero_cards = [card.rank + card.suit for card in recognition_frame.hero_cards if card.rank and card.suit]
                    board_cards = [card.rank + card.suit for card in recognition_frame.board_cards if card.rank and card.suit]
                    
                    card_results = {
                        "hero": hero_cards,
                        "board": board_cards
                    }
                    
                    # Logs détaillés des cartes détectées
                    if hero_cards:
                        print(f"🃏 Cartes Hero détectées: {hero_cards}")
                    if board_cards:
                        print(f"🃏 Cartes Board détectées: {board_cards}")
                    
                    # Logs détaillés de chaque carte individuelle
                    for i, card in enumerate(recognition_frame.hero_cards):
                        if card.rank and card.suit:
                            conf = getattr(card, 'confidence', 0.0)
                            print(f"🃏 Hero card {i+1}: {card.rank}{card.suit} (conf: {conf:.3f})")
                    
                    for i, card in enumerate(recognition_frame.board_cards):
                        if card.rank and card.suit:
                            conf = getattr(card, 'confidence', 0.0)
                            print(f"🃏 Board card {i+1}: {card.rank}{card.suit} (conf: {conf:.3f})")
                            
                except Exception as e:
                    print(f"⚠️ Erreur reconnaissance cartes: {e}")
                    card_results = {}
            
            # OCR du texte si disponible
            if self.text_ocr:
                try:
                    text_results = self.text_ocr.recognize_text(img)
                except Exception as e:
                    print(f"⚠️ Erreur OCR: {e}")
            
            # Construction de l'état
            return self._build_state(card_results, text_results)
            
        except Exception as e:
            print(f"⚠️ Erreur reconnaissance réelle: {e}")
            return None

    def _get_simulated_state(self, counter: int) -> HandState:
        """Génère un état simulé pour les tests."""
        # Données simulées qui changent
        hero_cards = ["Ah", "Kd"] if counter % 10 < 5 else ["Qc", "Js"]
        board_cards = ["As", "Kh", "Qd"] if counter % 20 < 10 else ["2c", "3h", "4d", "5s"]
        
        # Métriques simulées
        pot_value = 100.0 + (counter % 50) * 10
        to_call_value = 25.0 + (counter % 20) * 5
        stack_value = 1000.0 - (counter % 100) * 2
        name_value = "Hero"
        
        # Big blind
        bb = 2.0
        
        # Détermination de la street
        street = infer_street(board_cards)
        
        return HandState(
            street=street,
            hero_cards=hero_cards,
            board=board_cards,
            pot=pot_value,
            to_call=to_call_value,
            hero_stack=stack_value,
            bb=bb,
            hero_name=name_value,
            history=[]
        )

    def _build_state(self, card_results, text_results) -> Optional[HandState]:
        """Construit l'état de la main à partir des résultats de reconnaissance."""
        try:
            # Extraction des cartes
            hero_cards = card_results.get("hero", [])
            board_cards = card_results.get("board", [])
            
            # Debug: afficher les cartes avant filtrage
            print(f"🔍 Cartes avant filtrage - Hero: {hero_cards}, Board: {board_cards}")
            
            # Filtrage des cartes valides
            hero_cards = [c for c in hero_cards if c and c != "??"]
            board_cards = [c for c in board_cards if c and c != "??"]
            
            # Debug: afficher les cartes après filtrage
            print(f"🔍 Cartes après filtrage - Hero: {hero_cards}, Board: {board_cards}")
            
            # Extraction du texte
            pot = text_results.get("pot_combined")
            to_call = text_results.get("to_call")
            hero_stack = text_results.get("hero_stack")
            hero_name = text_results.get("hero_name")
            
            # Debug: afficher les clés disponibles
            if text_results:
                print(f"🔍 Clés OCR disponibles: {list(text_results.keys())}")
            
            # Conversion des valeurs
            pot_value = float(pot.normalized_value) if pot and pot.is_valid and pot.normalized_value is not None else None
            to_call_value = float(to_call.normalized_value) if to_call and to_call.is_valid and to_call.normalized_value is not None else None
            stack_value = float(hero_stack.normalized_value) if hero_stack and hero_stack.is_valid and hero_stack.normalized_value is not None else None
            name_value = hero_name.text if hero_name and hero_name.is_valid else None
            
            # Big blind par défaut
            bb = 2.0
            
            # Détermination de la street
            street = infer_street(board_cards)
            
            # Construction de l'état
            state = HandState(
                street=street,
                hero_cards=hero_cards,
                board=board_cards,
                pot=pot_value,
                to_call=to_call_value,
                hero_stack=stack_value,
                bb=bb,
                hero_name=name_value,
                history=[]
            )
            
            # Debug: afficher l'état construit
            print(f"🎯 État construit: Hero={hero_cards}, Board={board_cards}, Stack={stack_value}, Name={name_value}")
            
            return state
            
        except Exception as e:
            print(f"⚠️ Erreur construction état: {e}")
            return None

    # --- Publication et lecture snapshots (non-bloquant)
    def _publish_snapshot(self) -> None:
        """Publie le dernier état/policy dans le bus (dernier paquet seulement)."""
        snap = {"state": self._last_state, "policy": (self._last_policy or {})}
        self._bus.publish(snap)

    def get_snapshot(self) -> Optional[Dict]:
        snap, _ts = self._bus.get()
        return snap

    def get_cached_policy(self) -> Dict:
        """Retourne la dernière policy calculée par le worker (non-bloquant)."""
        return self._last_policy or {}

    def get_policy(self, state: HandState) -> Dict:
        """Non-bloquant: ne fait PAS d’appel réseau; renvoie le cache."""
        return self.get_cached_policy()

    def ready(self) -> bool:
        return self._ready

    def get_state(self) -> Optional[HandState]:
        return self._last_state


    def stop(self):
        self._stop = True

# === Overlay HUD avec tkinter simple ==========================================
class PokerHUD:
    """HUD overlay avec tkinter simple (compatible)."""
    
    def __init__(self, provider: HybridProvider, title: str = "Poker HUD", alpha: float = 0.92):
        self.provider = provider
        self.title = title
        
        # Création de la fenêtre
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("+80+80")
        self.root.overrideredirect(True)  # frameless
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', alpha)
        self.root.configure(bg='#1e1e1e')
        
        # Variables pour le drag
        self._drag = {"x": 0, "y": 0}
        self.root.bind("<Button-1>", self._on_click)
        self.root.bind("<B1-Motion>", self._on_drag)
        
        # Contrôles clavier
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<F8>", self._toggle_visibility)
        
        # Interface
        self._create_interface()
        
        # Boucle de monitoring
        self.root.after(250, self._poll_provider)

    def _create_interface(self):
        """Crée l'interface utilisateur."""
        # Frame principal
        main_frame = tk.Frame(self.root, bg='#2b2b2b', relief='raised', bd=1)
        main_frame.pack(padx=8, pady=8, fill='both', expand=True)
        
        # Titre
        title_label = tk.Label(main_frame, text=self.title, bg='#2b2b2b', fg='#00ff00', font=('Arial', 12, 'bold'))
        title_label.pack(pady=(6, 4))
        
        # Cartes
        self.hero_label = tk.Label(main_frame, text="Hero: —", bg='#2b2b2b', fg='white', font=('Arial', 10))
        self.board_label = tk.Label(main_frame, text="Board: —", bg='#2b2b2b', fg='white', font=('Arial', 10))
        self.hero_label.pack(anchor='w', padx=8)
        self.board_label.pack(anchor='w', padx=8)
        
        # Montants
        money_frame = tk.Frame(main_frame, bg='#2b2b2b')
        money_frame.pack(fill='x', padx=8, pady=4)
        
        self.pot_label = tk.Label(money_frame, text="Pot: —", bg='#2b2b2b', fg='white', font=('Arial', 10))
        self.call_label = tk.Label(money_frame, text="À payer: —", bg='#2b2b2b', fg='white', font=('Arial', 10))
        self.stack_label = tk.Label(money_frame, text="Stack: —", bg='#2b2b2b', fg='white', font=('Arial', 10))
        
        self.pot_label.grid(row=0, column=0, sticky='w', padx=(0, 16))
        self.call_label.grid(row=0, column=1, sticky='w', padx=(0, 16))
        self.stack_label.grid(row=0, column=2, sticky='w')
        
        # Action
        action_frame = tk.Frame(main_frame, bg='#2b2b2b')
        action_frame.pack(fill='x', padx=8, pady=6)
        
        self.action_label = tk.Label(action_frame, text="—", bg='#2b2b2b', fg='#ff6b6b', font=('Arial', 14, 'bold'))
        self.size_label = tk.Label(action_frame, text="", bg='#2b2b2b', fg='white', font=('Arial', 10))
        self.confidence_label = tk.Label(action_frame, text="Confiance: —", bg='#2b2b2b', fg='#4ecdc4', font=('Arial', 10))
        
        self.action_label.pack(anchor='w')
        self.size_label.pack(anchor='w')
        self.confidence_label.pack(anchor='w')

    def _on_click(self, e):
        """Gestion du clic pour le drag."""
        self._drag["x"] = e.x
        self._drag["y"] = e.y

    def _on_drag(self, e):
        """Gestion du drag."""
        x = self.root.winfo_x() + (e.x - self._drag["x"])
        y = self.root.winfo_y() + (e.y - self._drag["y"])
        self.root.geometry(f"+{x}+{y}")

    def _toggle_visibility(self, *_):
        """Basculer la visibilité."""
        current_alpha = self.root.attributes('-alpha')
        new_alpha = 0.18 if current_alpha > 0.5 else 0.92
        self.root.attributes('-alpha', new_alpha)

    def _poll_provider(self):
        """Polling du provider (lecture mailbox non-bloquante)."""
        try:
            if not self.provider.ready():
                self.root.after(300, self._poll_provider)
                return

            snap = None
            try:
                snap = self.provider.get_snapshot()  # type: ignore[attr-defined]
            except Exception:
                snap = None

            if not snap:
                self.root.after(300, self._poll_provider)
                return

            state = snap.get("state")
            policy = snap.get("policy") or {}
            if state is None:
                self.root.after(300, self._poll_provider)
                return

            self._render(state, policy)
        finally:
            self.root.after(300, self._poll_provider)

    def _render(self, state: HandState, policy: Dict):
        """Rendu de l'interface."""
        # Cartes
        hero_cards = " ".join(state.hero_cards or [])
        board_cards = " ".join(state.board or [])
        self.hero_label.configure(text=f"Hero: {hero_cards}")
        self.board_label.configure(text=f"Board: {board_cards}")

        # Montants
        pot = state.pot if state.pot is not None else "—"
        to_call = state.to_call if state.to_call is not None else "—"
        stack = state.hero_stack if state.hero_stack is not None else "—"
        
        self.pot_label.configure(text=f"Pot: {pot}")
        self.call_label.configure(text=f"À payer: {to_call}")
        self.stack_label.configure(text=f"Stack: {stack}")

        # Action
        action = (policy.get("action") or "—").upper()
        conf = float(policy.get("confidence") or 0.0)
        size = policy.get("size_bb")
        reason = policy.get("reason") or ""

        self.action_label.configure(text=action)
        
        if action == "RAISE" and size:
            self.size_label.configure(text=f"{size:.1f} bb • {reason}")
        else:
            self.size_label.configure(text=reason)
            
        self.confidence_label.configure(text=f"Confiance: {conf:.2f}")

    def mainloop(self):
        """Démarre la boucle principale."""
        self.root.mainloop()

# === Entrée ===================================================================
def main():
    print("🎯 Lancement de l'overlay HUD (CustomTkinter)")
    print("=" * 50)
    
    # Configuration CustomTkinter pour esthétique cohérente
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
    
    # 1) détecte les tables
    candidates = detector.detect_poker_tables()
    if not candidates:
        print("❌ Aucune table détectée.")
        return
    
    print(f"✅ {len(candidates)} table(s) détectée(s)")
    
    # 2) sélection de la table
    chosen = select_table_dialog(candidates)
    if not chosen:
        print("❌ Aucune table sélectionnée")
        return
    
    print(f"✅ Table sélectionnée: {chosen.title}")
    
    # 3) création du HUD
    handle = chosen.handle
    provider = HybridProvider(handle)
    
    if MODERN_OVERLAY_AVAILABLE:
        print("✅ Utilisation de l'overlay CustomTkinter moderne")
        hud = ModernPokerHUD(provider, f"Poker HUD — {chosen.title}")
    else:
        print("⚠️ Utilisation de l'overlay tkinter simple (fallback)")
        hud = PokerHUD(provider, f"Poker HUD — {chosen.title}", alpha=0.92)
    
    print("✅ HUD créé et démarré")
    print("\n🎮 Contrôles:")
    print("   - F8: Basculer la visibilité")
    print("   - Échap: Fermer l'overlay")
    print("   - Glisser-déposer: Déplacer l'overlay")
    
    # 4) boucle principale
    try:
        if MODERN_OVERLAY_AVAILABLE:
            hud.mainloop()
        else:
            hud.mainloop()
    except KeyboardInterrupt:
        print("\n👋 Arrêt de l'overlay HUD")

if __name__ == "__main__":
    main()