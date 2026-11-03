"""
genesis_profile_schema/minutes_library.py — BIBLIOTECA de modelos de ata (épico «Reuniões e atas»; D11 de
2 Nov 2026, criada a 3 Nov 2026 com a F3.6/R10, decisão D23).

Um JSON por modelo em `minutes_library/`, como a `intake_library`. Nesta primeira versão cada modelo traz só
os PRAZOS LEGAIS que se seguem a uma reunião (R10); os prompts, o validador e as fórmulas migram depois (D11).
O `audio.municipal_minutes.organ_type` do perfil aponta para o modelo (`model_for_organ_type`).

Um prazo:
  id       — estável (o core guarda «feito» por ele);
  label    — {pt, en};
  law      — a norma (texto, mostrado ao lado do prazo);
  from     — `meeting_date` (a data da deliberação);
  days     — o prazo, contado a partir do DIA SEGUINTE ao `from`;
  unit     — `calendar` (dias corridos) | `business` (dias úteis, com o calendário do cliente);
  window   — opcional, dias que a afixação tem de durar dentro do prazo (o edital: «durante cinco dos 10 dias»);
  scope    — opcional, {pt, en}: a que deliberações se aplica.
Quem chama recebe CÓPIAS.
"""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, List, Optional, Tuple

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_LANGS = ("pt", "en")
UNITS = ("calendar", "business")
FROMS = ("meeting_date",)
MAX_DAYS = 366

#: O tipo de órgão do perfil → o modelo (os quatro órgãos autárquicos partilham a Lei 75/2013).
ORGAN_MODEL = {
    "camara_municipal": "autarquia", "assembleia_municipal": "autarquia",
    "junta_freguesia": "autarquia", "assembleia_freguesia": "autarquia",
    "orgao_colegial": "orgao_colegial",
}


def _text(v: Any, name: str, part: str) -> None:
    if not isinstance(v, dict) or any(not str(v.get(l) or "").strip() for l in _LANGS):
        raise ValueError(f"{name}: `{part}` tem de existir em {list(_LANGS)}")


def _check_deadline(d: Any, name: str) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not _ID_RE.match(d["id"]):
        raise ValueError(f"{name}: prazo com `id` inválido")
    _text(d.get("label"), name, f"deadlines.{d['id']}.label")
    if not str(d.get("law") or "").strip():
        raise ValueError(f"{name}: prazo `{d['id']}` sem `law`")
    if d.get("from") not in FROMS or d.get("unit") not in UNITS:
        raise ValueError(f"{name}: prazo `{d['id']}` com `from`/`unit` inválido")
    days = d.get("days")
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise ValueError(f"{name}: prazo `{d['id']}` com `days` fora de 1–{MAX_DAYS}")
    win = d.get("window")
    if win is not None and (isinstance(win, bool) or not isinstance(win, int) or not 1 <= win <= days):
        raise ValueError(f"{name}: prazo `{d['id']}` com `window` fora de 1–{days}")
    if d.get("scope") is not None:
        _text(d.get("scope"), name, f"deadlines.{d['id']}.scope")


def _check(doc: Any, name: str) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        raise ValueError(f"{name}: não é um objeto")
    mid = doc.get("id")
    if not isinstance(mid, str) or not _ID_RE.match(mid) or name != f"{mid}.json":
        raise ValueError(f"{name}: `id` inválido ou diferente do nome do ficheiro")
    _text(doc.get("name"), name, "name")
    deadlines = doc.get("deadlines")
    if not isinstance(deadlines, list):
        raise ValueError(f"{name}: `deadlines` tem de ser uma lista")
    ids = set()
    for d in deadlines:
        _check_deadline(d, name)
        if d["id"] in ids:
            raise ValueError(f"{name}: prazo `{d['id']}` repetido")
        ids.add(d["id"])
    return doc


@lru_cache(maxsize=1)
def _load() -> Tuple[Dict[str, Any], ...]:
    folder = resources.files(__package__).joinpath("minutes_library")
    docs = [_check(json.loads(e.read_text(encoding="utf-8")), e.name)
            for e in folder.iterdir() if e.name.endswith(".json")]
    docs.sort(key=lambda d: d["id"])
    return tuple(docs)


def list_models() -> List[Dict[str, Any]]:
    return [copy.deepcopy(d) for d in _load()]


def get_model(model_id: str) -> Optional[Dict[str, Any]]:
    for d in _load():
        if d["id"] == model_id:
            return copy.deepcopy(d)
    return None


def model_for_organ_type(organ_type: Any) -> Optional[Dict[str, Any]]:
    """O modelo do tipo de órgão do perfil, ou None (tipo desconhecido)."""
    mid = ORGAN_MODEL.get(str(organ_type or ""))
    return get_model(mid) if mid else None
