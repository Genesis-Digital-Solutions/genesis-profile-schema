"""
genesis_profile_schema/intake_library.py — BIBLIOTECA de modelos de
questionário do Intake (v0.1.91, 6 Out 2026; épico Intake B12 F4 e §17 F6).

Uma só fonte para o Studio e para o GAIBO (decisão do Bruno, 6 Out: «ambos»):
cada modelo é um JSON em `intake_library/` com uma definição completa e
GENÉRICA — perguntas, textos de exemplo com «[entidade]» para trocar e, quando
tem regras, casos de teste que as provam. Nada de um cliente. Quem começa de um
modelo adapta tudo no editor e aprova a sua versão das regras.

Cada definição é validada contra `IntakeDefinition` ao carregar (um modelo
inválido rebenta aqui, nunca no ecrã de quem o escolhe); o core corre os casos
de cada modelo no motor real (`tests/intake/test_library_cases.py`).
Quem chama recebe CÓPIAS — mexer num rascunho nunca muda o modelo.
"""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, List, Optional, Tuple

from .intake_schema import IntakeDefinition

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_META_LANGS = ("pt", "en")


def _check(doc: Any, name: str) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        raise ValueError(f"{name}: não é um objeto")
    tid = doc.get("id")
    if not isinstance(tid, str) or not _ID_RE.match(tid) or name != f"{tid}.json":
        raise ValueError(f"{name}: `id` inválido ou diferente do nome do ficheiro")
    if not isinstance(doc.get("order"), int):
        raise ValueError(f"{name}: `order` em falta")
    for part in ("name", "description"):
        text = doc.get(part)
        if not isinstance(text, dict) or any(not str(text.get(l) or "").strip() for l in _META_LANGS):
            raise ValueError(f"{name}: `{part}` tem de existir em {list(_META_LANGS)}")
    model = IntakeDefinition.model_validate(doc.get("definition"))
    if bool(doc.get("rules")) != (model.methodology is not None):
        raise ValueError(f"{name}: `rules` não bate com a metodologia")
    return doc


@lru_cache(maxsize=1)
def _load() -> Tuple[Dict[str, Any], ...]:
    folder = resources.files(__package__).joinpath("intake_library")
    docs = []
    for entry in folder.iterdir():
        if entry.name.endswith(".json"):
            docs.append(_check(json.loads(entry.read_text(encoding="utf-8")), entry.name))
    docs.sort(key=lambda d: (d["order"], d["id"]))
    return tuple(docs)


def list_templates() -> List[Dict[str, Any]]:
    """Os modelos por ordem: `{id, order, name, description, rules, definition}`."""
    return copy.deepcopy(list(_load()))


def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    """O modelo `template_id` (cópia) ou None."""
    for doc in _load():
        if doc["id"] == template_id:
            return copy.deepcopy(doc)
    return None
