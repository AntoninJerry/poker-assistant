## Assistant IA Poker (Local, OCR + Ollama)

Assistant stratégique pour tables de poker en ligne. Lecture écran uniquement (OCR), analyse locale via Ollama (llama3.1:8b), et recommandations affichées dans un overlay discret.

### Caractéristiques
- Détection automatique de la fenêtre table (Winamax/PMU)
- Capture `mss` du rect client, ROIs calibrés via YAML
- OCR priorisé (pot, to_call, hero cards, board)
- Politique LLM locale (Ollama) en JSON strict
- UI CustomTkinter overlay topmost, borderless, draggable
- Sécurité gaming stricte: aucune automation, lecture seule

### Prérequis
- Windows 11, Python 3.12+
- Ollama installé et modèle `llama3.1:8b` disponible

### Installation (dev)
```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .[dev]
pre-commit install
```

### Lancement
```bash
python -m poker_assistant.app
```

### Arborescence
```
src/poker_assistant/
  app.py
  config.py
  security/guard.py
  windows/detector.py
  ocr/{capture.py,readers.py,parsers.py,calibrate_gui.py}
  strategy/{features.py,ev_math.py,profiles.py,engine.py,providers/{base.py,ollama_.py,rules_.py}}
  ui/{overlay.py,voice.py,room_selector.py}
  rooms/{winamax.yaml,pmu.yaml,templates/}
  telemetry/{logging.py,storage.py}
```

### Sécurité et conformité
- Aucune interaction avec le process poker (pas d'injection, pas de hooks)
- Aucun clic/clavier automatisé
- Lecture écran uniquement via `mss`
- Jitter OCR 200–500 ms configurable

### Tests
```bash
pytest
```

### Licence
MIT


