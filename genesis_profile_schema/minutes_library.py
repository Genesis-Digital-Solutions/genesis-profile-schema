"""
genesis_profile_schema/minutes_library.py — BIBLIOTECA de modelos de ata (épico «Reuniões e atas»; D11 de
2 Nov 2026, criada a 3 Nov 2026 com a F3.6/R10, decisão D23).

Um JSON por modelo em `minutes_library/`, como a `intake_library`. Cada modelo traz os PRAZOS LEGAIS que se
seguem a uma reunião (R10) e, desde a v0.1.146 (F4, 3 Nov 2026 — decisão do Bruno: os tipos de reunião por DADOS),
o regime e os órgãos: quem preside, os cargos (lista fechada), quem assina, o peso dos votos, a fórmula das
deliberações e as regras próprias que o modelo lê. O `audio.municipal_minutes.organ_type` do perfil é o `id` de um
órgão de um modelo (`model_for_organ_type`, `organ_info`).

Campos do modelo (os da v0.1.146 são opcionais; os modelos publicados trazem-nos todos):
  family      — `municipal` (Lei 75/2013, com edital) | `public` (CPA) | `private` (o resto);
  regime      — PT: o regime numa frase para o pedido ao modelo («de uma assembleia de condóminos (…)»);
  rules       — PT: regras próprias do regime, acrescentadas às do pedido;
  member_term — PT: como se chama um membro na discussão («O condómino X referiu…»);
  outsiders   — PT: a regra para quem fala sem ser membro;
  weight      — null ou {unit, label{pt,en}}: os votos contam por peso (permilagem, capital) — o peso de cada
                membro é dado do cliente (`members[].weight`), nunca inventado;
  organs      — [{id (o organ_type), label{pt,en}, default_name (PT, o nome quando o perfil não o dá),
                  subject (PT, «A Assembleia» na fórmula; vazio = «Foi deliberado»), preside [cargos, minúsculas],
                  roles [PT, a lista fechada de cargos — o texto que se grava e vai para a ata, com as formas no feminino], signatures [PT, quem assina],
                  sign_each_present [as `signatures` que dão uma linha por presente — «Os sócios que participaram»], closing (PT, a frase
                  final da ata)}].

Um prazo:
  id       — estável (o core guarda «feito» por ele);
  label    — {pt, en};
  law      — a norma (texto, mostrado ao lado do prazo);
  from     — `meeting_date` (a data da deliberação);
  days     — o prazo, contado a partir do DIA SEGUINTE ao `from`;
  unit     — `calendar` (dias corridos) | `business` (dias úteis, com o calendário do cliente);
  window   — opcional, dias que a afixação tem de durar dentro do prazo (o edital: «durante cinco dos 10 dias»);
  scope    — opcional, {pt, en}: a que deliberações se aplica;
  organs   — opcional, [ids de órgãos do modelo]: os órgãos a que o prazo se aplica (sem ele, todos; revisão de
             3 Nov 2026 — o registo no ISS é da assembleia geral, não da direção).
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

FAMILIES = ("municipal", "public", "private")
WEIGHT_UNITS = ("permilagem", "capital")
MAX_LIST = 40
MAX_TEXT = 2000


def _text(v: Any, name: str, part: str) -> None:
    if not isinstance(v, dict) or any(not str(v.get(l) or "").strip() for l in _LANGS):
        raise ValueError(f"{name}: `{part}` tem de existir em {list(_LANGS)}")


def _check_deadline(d: Any, name: str) -> None:
    if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not _ID_RE.fullmatch(d["id"]):
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
    orgs = d.get("organs")
    if orgs is not None and (not isinstance(orgs, list) or not orgs or len(orgs) > MAX_LIST
                             or any(not isinstance(x, str) or not _ID_RE.fullmatch(x) for x in orgs)):
        raise ValueError(f"{name}: prazo `{d['id']}` com `organs` inválido")


def _pt(v: Any, name: str, part: str, required: bool = True) -> None:
    if v is None and not required:
        return
    if not isinstance(v, str) or (required and not v.strip()) or len(v) > MAX_TEXT:
        raise ValueError(f"{name}: `{part}` tem de ser texto (até {MAX_TEXT})")


def _check_organ(o: Any, name: str) -> None:
    if not isinstance(o, dict) or not isinstance(o.get("id"), str) or not _ID_RE.fullmatch(o["id"]):
        raise ValueError(f"{name}: órgão com `id` inválido")
    oid = o["id"]
    _text(o.get("label"), name, f"organs.{oid}.label")
    _pt(o.get("default_name"), name, f"organs.{oid}.default_name")
    _pt(o.get("subject"), name, f"organs.{oid}.subject", required=False)
    _pt(o.get("closing"), name, f"organs.{oid}.closing", required=False)
    _pt(o.get("member_term"), name, f"organs.{oid}.member_term", required=False)
    if "weight" in o and o["weight"] is not None:
        if not isinstance(o["weight"], dict) or o["weight"].get("unit") not in WEIGHT_UNITS:
            raise ValueError(f"{name}: `organs.{oid}.weight` inválido")
        _text(o["weight"].get("label"), name, f"organs.{oid}.weight.label")   # o Studio mostra o rótulo
    rules = o.get("rules", [])
    if not isinstance(rules, list) or len(rules) > MAX_LIST:
        raise ValueError(f"{name}: `organs.{oid}.rules` tem de ser uma lista (até {MAX_LIST})")
    for r in rules:
        _pt(r, name, f"organs.{oid}.rules")
    for key in ("preside", "signatures", "roles"):
        v = o.get(key)
        if not isinstance(v, list) or not v or len(v) > MAX_LIST or any(not isinstance(x, str) or not x.strip() for x in v):
            raise ValueError(f"{name}: `organs.{oid}.{key}` tem de ser uma lista de textos")
    each = o.get("sign_each_present", [])
    if not isinstance(each, list) or any(x not in o["signatures"] for x in each):
        raise ValueError(f"{name}: `organs.{oid}.sign_each_present` tem de ser uma lista de `signatures`")


def _check_regime(doc: Dict[str, Any], name: str) -> None:
    """Os campos da v0.1.146 (opcionais; com `organs` ou `family`, os dois são obrigatórios — um modelo a meio
    nunca passa sem validar o resto)."""
    organs = doc.get("organs")
    if organs is None and doc.get("family") is None:
        for k in ("regime", "rules", "member_term", "outsiders", "weight"):
            if k in doc:
                raise ValueError(f"{name}: `{k}` sem `family` nem `organs`")
        return
    if doc.get("family") not in FAMILIES:
        raise ValueError(f"{name}: `family` tem de ser uma de {list(FAMILIES)}")
    if not isinstance(organs, list) or not organs:
        raise ValueError(f"{name}: `organs` tem de ser uma lista não vazia")
    for o in organs:
        _check_organ(o, name)
    ids = [o["id"] for o in organs]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{name}: órgão repetido no modelo")
    for d in doc.get("deadlines") or []:
        fora = set(d.get("organs") or []) - set(ids)
        if fora:
            raise ValueError(f"{name}: prazo `{d['id']}` com órgãos que o modelo não tem: {sorted(fora)}")
    private = doc["family"] == "private"
    _pt(doc.get("regime"), name, "regime", required=private)
    _pt(doc.get("member_term"), name, "member_term", required=private)
    _pt(doc.get("outsiders"), name, "outsiders", required=False)
    rules = doc.get("rules", [])
    if not isinstance(rules, list) or len(rules) > MAX_LIST:
        raise ValueError(f"{name}: `rules` tem de ser uma lista")
    for r in rules:
        _pt(r, name, "rules")
    w = doc.get("weight")
    if w is not None:
        if not isinstance(w, dict) or w.get("unit") not in WEIGHT_UNITS:
            raise ValueError(f"{name}: `weight.unit` tem de ser uma de {list(WEIGHT_UNITS)}")
        _text(w.get("label"), name, "weight.label")


def _check(doc: Any, name: str) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        raise ValueError(f"{name}: não é um objeto")
    mid = doc.get("id")
    if not isinstance(mid, str) or not _ID_RE.fullmatch(mid) or name != f"{mid}.json":
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
    _check_regime(doc, name)
    if doc.get("organs") is None and any(d.get("organs") for d in deadlines):
        raise ValueError(f"{name}: prazos com `organs` num modelo sem órgãos")
    return doc


@lru_cache(maxsize=1)
def _load() -> Tuple[Dict[str, Any], ...]:
    folder = resources.files(__package__).joinpath("minutes_library")
    docs = [_check(json.loads(e.read_text(encoding="utf-8")), e.name)
            for e in folder.iterdir() if e.name.endswith(".json")]
    docs.sort(key=lambda d: d["id"])
    seen: Dict[str, str] = {}
    for d in docs:
        for o in d.get("organs") or []:
            if o["id"] in seen:
                raise ValueError(f"órgão `{o['id']}` em dois modelos ({seen[o['id']]}, {d['id']})")
            seen[o["id"]] = d["id"]
    return tuple(docs)


def organ_model_map() -> Dict[str, str]:
    """O tipo de órgão do perfil → o id do modelo (lido dos `organs` da biblioteca)."""
    return {o["id"]: d["id"] for d in _load() for o in d.get("organs") or []}


def organ_types() -> List[str]:
    """Todos os tipos de órgão da biblioteca, pela ordem dos modelos e dos órgãos."""
    return [o["id"] for d in _load() for o in d.get("organs") or []]


def list_models() -> List[Dict[str, Any]]:
    return [copy.deepcopy(d) for d in _load()]


def get_model(model_id: str) -> Optional[Dict[str, Any]]:
    for d in _load():
        if d["id"] == model_id:
            return copy.deepcopy(d)
    return None


def model_for_organ_type(organ_type: Any) -> Optional[Dict[str, Any]]:
    """O modelo do tipo de órgão do perfil, ou None (tipo desconhecido)."""
    mid = organ_model_map().get(str(organ_type or ""))
    return get_model(mid) if mid else None


def organ_info(organ_type: Any) -> Optional[Dict[str, Any]]:
    """O órgão (cópia) com o regime do modelo junto: `{**órgão, model, family, regime, rules, member_term,
    outsiders, weight, deadlines}` — `deadlines` só com os prazos deste órgão; None para um tipo desconhecido."""
    m = model_for_organ_type(organ_type)
    if not m:
        return None
    o = next(x for x in m.get("organs") or [] if x["id"] == str(organ_type))
    # O órgão sobrepõe o modelo (revisão de 3 Nov 2026: o CA vota por cabeça, não por capital).
    def pick(k, default):
        return o[k] if k in o else m.get(k, default)
    return {**o, "model": m["id"], "family": m.get("family"), "regime": m.get("regime") or "",
            "rules": list(pick("rules", []) or []), "member_term": pick("member_term", "") or "",
            "outsiders": m.get("outsiders") or "", "weight": pick("weight", None),
            "deadlines": [d for d in m.get("deadlines") or [] if not d.get("organs") or o["id"] in d["organs"]]}
