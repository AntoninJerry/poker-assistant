"""Client Ollama pour l'analyse stratégique de poker."""

import json
import re
import requests
from typing import Optional

from .typing_ext import PolicyDict
from ...config import LLM_CFG
from ...state.model import HandState


PROMPT = """You are a poker assistant. Reply ONLY in compact JSON.

State:
- Street: {street}
- Hero: {hero_cards}
- Board: {board}
- Pot: {pot}
- ToCall: {to_call}
- BB: {bb}
- HeroStack: {hero_stack}
- History: {history}

Return a single-line JSON object with keys:
{{"action":"fold|call|raise","size_bb":float|null,"confidence":0.0-1.0,"reason":"short"}}

No markdown, no prose, JSON only.
"""


def _extract_json(txt: str) -> str:
    """Extrait le plus grand objet JSON du texte (tolérant)."""
    m = re.search(r"\{.*\}", txt, flags=re.S)
    return m.group(0) if m else "{}"


def call_ollama(prompt: str) -> str:
    """Appelle l'API Ollama avec le prompt donné."""
    url = f"{LLM_CFG.host}/api/generate"
    payload = {
        "model": LLM_CFG.model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": LLM_CFG.temperature,
            "top_p": LLM_CFG.top_p,
            "num_predict": LLM_CFG.max_tokens
        }
    }
    
    try:
        r = requests.post(url, json=payload, timeout=LLM_CFG.timeout_s)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "")
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Erreur appel Ollama: {e}")
        return ""
    except Exception as e:
        print(f"⚠️ Erreur inattendue Ollama: {e}")
        return ""


def parse_policy_json(txt: str) -> PolicyDict:
    """Parse le JSON de politique avec fallback tolérant."""
    try:
        json_str = _extract_json(txt)
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"⚠️ Erreur parsing JSON: {e}")
        return {}
    except Exception as e:
        print(f"⚠️ Erreur inattendue parsing: {e}")
        return {}


def query_policy(state: HandState) -> PolicyDict:
    """Interroge Ollama pour obtenir une politique de jeu."""
    if not LLM_CFG.enabled:
        print("⚠️ LLM désactivé dans la configuration")
        return {}
    
    prompt = PROMPT.format(
        street=state.street,
        hero_cards=state.hero_cards,
        board=state.board,
        pot=state.pot if state.pot is not None else "null",
        to_call=state.to_call if state.to_call is not None else "null",
        bb=state.bb if state.bb is not None else "null",
        hero_stack=state.hero_stack if state.hero_stack is not None else "null",
        history=state.history or []
    )
    
    print(f"🤖 Appel Ollama pour {state.street}...")
    txt = call_ollama(prompt)
    
    if not txt:
        print("⚠️ Réponse Ollama vide")
        return {}
    
    policy = parse_policy_json(txt)
    
    if policy:
        print(f"✅ Politique reçue: {policy}")
    else:
        print("⚠️ Aucune politique valide reçue")
    
    return policy