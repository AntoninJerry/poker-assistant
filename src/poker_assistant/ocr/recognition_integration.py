#!/usr/bin/env python3
"""
Module d'intégration de la reconnaissance dans l'interface live_preview.
"""

import cv2
import numpy as np
from typing import Optional, Dict, Any
from pathlib import Path
import threading
import time
from queue import Queue, Empty

from .card_recognition import CardRecognitionPipeline, RecognitionFrame, CardResult

class RecognitionIntegration:
    """Intégration de la reconnaissance dans l'interface."""
    
    def __init__(self, yaml_path: str, templates_dir: str = "assets/templates"):
        """
        Initialise l'intégration de reconnaissance.
        
        Args:
            yaml_path: Chemin vers le fichier YAML
            templates_dir: Dossier des templates
        """
        self.yaml_path = yaml_path
        self.templates_dir = templates_dir
        
        # Pipeline de reconnaissance
        self.pipeline: Optional[CardRecognitionPipeline] = None
        
        # Threading
        self.recognition_thread: Optional[threading.Thread] = None
        self.recognition_queue = Queue(maxsize=10)
        self.is_running = False
        
        # Derniers résultats
        self.last_recognition: Optional[RecognitionFrame] = None
        self.last_update_time = 0.0
        
        # Configuration
        self.recognition_enabled = False
        self.recognition_fps = 2  # 2 FPS pour la reconnaissance
        
    def initialize_pipeline(self) -> bool:
        """
        Initialise le pipeline de reconnaissance.
        
        Returns:
            True si l'initialisation réussit
        """
        try:
            self.pipeline = CardRecognitionPipeline(
                yaml_path=self.yaml_path,
                templates_dir=self.templates_dir
            )
            print("✅ Pipeline de reconnaissance initialisé")
            return True
        except Exception as e:
            print(f"❌ Erreur initialisation pipeline: {e}")
            return False
    
    def start_recognition(self):
        """Démarre le thread de reconnaissance."""
        if self.pipeline is None:
            if not self.initialize_pipeline():
                return False
        
        if self.is_running:
            return True
        
        self.is_running = True
        self.recognition_thread = threading.Thread(
            target=self._recognition_worker,
            daemon=True
        )
        self.recognition_thread.start()
        print("🚀 Thread de reconnaissance démarré")
        return True
    
    def stop_recognition(self):
        """Arrête le thread de reconnaissance."""
        self.is_running = False
        if self.recognition_thread:
            self.recognition_thread.join(timeout=1.0)
        print("⏹️ Thread de reconnaissance arrêté")
    
    def _recognition_worker(self):
        """Worker thread pour la reconnaissance."""
        while self.is_running:
            try:
                # Attend un frame à traiter
                frame_data = self.recognition_queue.get(timeout=1.0)
                
                # Traite le frame
                recognition_frame = self.pipeline.recognize_cards(frame_data)
                
                # Met à jour les résultats
                self.last_recognition = recognition_frame
                self.last_update_time = time.time()
                
                # Vide la queue pour éviter l'accumulation
                while not self.recognition_queue.empty():
                    try:
                        self.recognition_queue.get_nowait()
                    except Empty:
                        break
                
            except Empty:
                continue
            except Exception as e:
                print(f"⚠️ Erreur dans le worker de reconnaissance: {e}")
                time.sleep(0.1)
    
    def process_frame(self, frame: np.ndarray) -> bool:
        """
        Traite un frame pour la reconnaissance.
        
        Args:
            frame: Image à traiter
            
        Returns:
            True si le frame a été ajouté à la queue
        """
        if not self.recognition_enabled or not self.is_running:
            return False
        
        try:
            # Ajoute le frame à la queue (non-bloquant)
            self.recognition_queue.put_nowait(frame)
            return True
        except:
            # Queue pleine, ignore ce frame
            return False
    
    def get_last_recognition(self) -> Optional[RecognitionFrame]:
        """
        Retourne la dernière reconnaissance.
        
        Returns:
            Dernier frame de reconnaissance ou None
        """
        return self.last_recognition
    
    def get_recognition_summary(self) -> str:
        """
        Retourne un résumé de la dernière reconnaissance.
        
        Returns:
            Résumé textuel
        """
        if self.last_recognition is None:
            return "🔍 Reconnaissance en cours..."
        
        return self.pipeline.get_recognition_summary(self.last_recognition)
    
    def get_hero_cards_display(self) -> str:
        """
        Retourne l'affichage des cartes hero.
        
        Returns:
            String d'affichage des cartes hero
        """
        if self.last_recognition is None:
            return "?? ??"
        
        hero_str = ""
        for card in self.last_recognition.hero_cards:
            if card.rank and card.suit:
                hero_str += f"{card.rank}{card.suit}"
                if card.is_uncertain:
                    hero_str += "?"
                hero_str += " "
            else:
                hero_str += "?? "
        
        return hero_str.strip()
    
    def get_board_cards_display(self) -> str:
        """
        Retourne l'affichage des cartes du board.
        
        Returns:
            String d'affichage des cartes du board
        """
        if self.last_recognition is None:
            return "?? ?? ?? ?? ??"
        
        board_str = ""
        for card in self.last_recognition.board_cards:
            if card.rank and card.suit:
                board_str += f"{card.rank}{card.suit} "
            else:
                board_str += "?? "
        
        return board_str.strip()
    
    def get_game_state_display(self) -> str:
        """
        Retourne l'affichage de l'état du jeu.
        
        Returns:
            String d'affichage de l'état
        """
        if self.last_recognition is None:
            return "🔍 Détection..."
        
        state_emoji = {
            "preflop": "🎯",
            "flop": "🃏",
            "turn": "🂠",
            "river": "🎲"
        }
        
        emoji = state_emoji.get(self.last_recognition.game_state.value, "❓")
        return f"{emoji} {self.last_recognition.game_state.value.upper()}"
    
    def get_confidence_display(self) -> str:
        """
        Retourne l'affichage des confiances.
        
        Returns:
            String d'affichage des confiances
        """
        if self.last_recognition is None:
            return "Confiance: --"
        
        # Calcule la confiance moyenne
        all_confidences = []
        
        for card in self.last_recognition.hero_cards:
            if card.combined_confidence > 0:
                all_confidences.append(card.combined_confidence)
        
        for card in self.last_recognition.board_cards:
            if card.combined_confidence > 0:
                all_confidences.append(card.combined_confidence)
        
        if not all_confidences:
            return "Confiance: --"
        
        avg_confidence = sum(all_confidences) / len(all_confidences)
        return f"Confiance: {avg_confidence:.2f}"
    
    def is_recognition_stale(self, max_age: float = 5.0) -> bool:
        """
        Vérifie si la reconnaissance est obsolète.
        
        Args:
            max_age: Âge maximum en secondes
            
        Returns:
            True si la reconnaissance est obsolète
        """
        if self.last_recognition is None:
            return True
        
        age = time.time() - self.last_update_time
        return age > max_age
    
    def get_recognition_status(self) -> str:
        """
        Retourne le statut de la reconnaissance.
        
        Returns:
            Statut textuel
        """
        if not self.recognition_enabled:
            return "🔴 Désactivé"
        
        if not self.is_running:
            return "🟡 Arrêté"
        
        if self.is_recognition_stale():
            return "🟠 Obsolète"
        
        return "🟢 Actif"
