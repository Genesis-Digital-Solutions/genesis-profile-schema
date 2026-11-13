"""
genesis_profile_schema/module_guides.py — o PERCURSO de configuração de cada módulo (v0.1.140,
31 Out 2026).

Camada do contrato ao lado da forma (`client_profile_schema.py`), de quem vê (`exposure.py`),
do texto de cada campo (`ui_text.py`) e do controlo (`presentation.py`). Essas dizem o que é
CADA campo; esta diz em que ORDEM se configura um módulo e o que é essencial:

  * casos de uso («Para que é?») — o ponto de partida, cada um com a sua predefinição;
  * passos por ordem lógica, cada um `essential` | `optional` | `advanced`, com «para que
    serve», «quando usar», os campos essenciais e os avançados, a condição para aparecer,
    o que conta como feito e exemplos;
  * ligações a outros módulos (ex.: o email da Ingestão que entra numa fila) — onde ficam
    guardadas, para o ecrã as mostrar dos dois lados e as escolher numa lista.

PORQUÊ NO PACOTE
────────────────
É a mesma fonte para o ecrã do Studio, o Manual do Studio (passo a passo, com os exemplos),
o agente do Studio, o backoffice do cliente e as suites verticais. O Studio e o backoffice não
falam um com o outro; o pacote é o que ambos instalam.

O QUE ISTO NÃO É
────────────────
Não muda nada no comportamento: o genai-core não lê esta camada. Um percurso só arruma o que já
existe — os caminhos que cita têm de existir no schema (validado aqui) e, num módulo de mapa
(ex.: as filas), TODOS os campos do item têm de estar nalgum passo: nada fica sem ecrã.
"""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

_CLOSED = ConfigDict(extra="forbid")
_KEY_RE = r"^[a-z][a-z0-9_]{0,39}$"
#: Línguas em que todo o texto de um percurso tem de existir (as do Manual do Studio).
GUIDE_LANGS = ("pt", "en")
MAX_TEXT = 600

#: Listas e mapas que o schema guarda SEM forma (dicionários livres) — uma ligação pode
#: apontar para um campo lá dentro. Allowlist deliberada: cada entrada é uma decisão.
_UNTYPED_PREFIXES = {
    "ingest.sources": "fontes de ingestão (List[Dict], ProfileIngest.sources)",
}


def _text(v: Any) -> Dict[str, str]:
    if not isinstance(v, dict):
        raise ValueError("texto tem de ser {língua: texto}")
    out = {}
    for lang in GUIDE_LANGS:
        t = v.get(lang)
        if not isinstance(t, str) or not t.strip():
            raise ValueError(f"falta o texto em {lang!r}")
        if len(t) > MAX_TEXT:
            raise ValueError(f"texto em {lang!r} com mais de {MAX_TEXT} caracteres")
    for lang, t in v.items():
        if not isinstance(lang, str) or not isinstance(t, str):
            raise ValueError("texto tem de ser {língua: texto}")
        out[lang] = t
    return out


Text = Dict[str, str]


class GuideCondition(BaseModel):
    """O passo aparece se ALGUMA destas for verdadeira (vazio = sempre)."""
    model_config = _CLOSED
    any_present: List[str] = Field(default_factory=list)   # campos do item/módulo com valor
    case_in: List[str] = Field(default_factory=list)        # caso de uso escolhido


class GuideCase(BaseModel):
    """Um caso de uso — o «Para que é?». `preset`: o modelo de partida numa biblioteca do pacote
    que o módulo já tenha (ex.: no Intake, o id de um modelo de `intake_library`) —
    validado em `_PRESET_SOURCES`. As filas usam `module_guides/presets/` (abaixo)."""
    model_config = _CLOSED
    key: str = Field(pattern=_KEY_RE)
    title: Text
    description: Text
    when: Text
    preset: Optional[str] = Field(default=None, pattern=_KEY_RE)
    #: Caso de uso que o produto ainda não serve (3 Nov 2026; ex.: na verificação documental, «quem avalia» sem
    #: esquema): aparece «em preparação», não se escolhe e não tem predefinição.
    available: StrictBool = True

    @field_validator("title", "description", "when")
    @classmethod
    def _texts(cls, v):
        return _text(v)

    @model_validator(mode="after")
    def _unavailable_without_preset(self):
        if not self.available and self.preset:
            raise ValueError(f"caso {self.key!r} em preparação não pode ter `preset`")
        return self


class GuideLink(BaseModel):
    """Uma ligação a outro módulo. `path` = onde fica guardada, no dialeto de
    `exposure.leaf_paths()` (itens de listas juntos: `actionRules.rules.approval.queue`)."""
    model_config = _CLOSED
    key: str = Field(pattern=_KEY_RE)
    direction: Literal["in", "out"]
    module: str = Field(pattern=_KEY_RE)
    path: str = Field(min_length=1, max_length=200)
    title: Text
    purpose: Text
    #: O valor que conta como «ligada» quando não basta haver um valor (1 Nov 2026; ex.: o login
    #: obrigatório é `required`, não `optional`). Sem ele, qualquer valor conta.
    expects: Optional[Union[str, bool]] = None

    @field_validator("title", "purpose")
    @classmethod
    def _texts(cls, v):
        return _text(v)


class GuideStep(BaseModel):
    model_config = _CLOSED
    key: str = Field(pattern=_KEY_RE)
    level: Literal["essential", "optional", "advanced"]
    title: Text
    purpose: Text
    when: Optional[Text] = None
    essential: List[str] = Field(default_factory=list)
    advanced: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)
    show_if: Optional[GuideCondition] = None
    done_if: List[str] = Field(default_factory=list)       # feito = todos com valor
    examples: List[Text] = Field(default_factory=list, max_length=4)
    #: Passo sem campos próprios (o «Para que é?», o «Rever e testar»).
    kind: Literal["fields", "cases", "review"] = "fields"

    @field_validator("title", "purpose")
    @classmethod
    def _texts(cls, v):
        return _text(v)

    @field_validator("when")
    @classmethod
    def _when(cls, v):
        return None if v is None else _text(v)

    @field_validator("examples")
    @classmethod
    def _examples(cls, v):
        return [_text(x) for x in v]


class ModuleGuide(BaseModel):
    """O percurso de UM módulo. `scope`: `profile` (os caminhos são do perfil) ou `map`
    (um item de um mapa — ex.: cada fila de `reviewQueues`; os caminhos são do item)."""
    model_config = _CLOSED
    module: str = Field(pattern=_KEY_RE)
    order: int
    title: Text
    summary: Text
    scope: Literal["profile", "map"]
    root: str = Field(min_length=1, max_length=120)
    item_model: Optional[str] = None
    #: Chaves que o genai-core LÊ no item mas que o modelo não declara (`extra="allow"`), ex.
    #: `numberFields` das filas (`review_queue_spec.py`). Entram nos passos como as outras —
    #: assim nada do que o core lê fica sem ecrã (revisão de 31 Out 2026).
    item_extras: List[str] = Field(default_factory=list)
    cases: List[GuideCase] = Field(default_factory=list)
    steps: List[GuideStep] = Field(min_length=1)
    links: List[GuideLink] = Field(default_factory=list)

    @field_validator("title", "summary")
    @classmethod
    def _texts(cls, v):
        return _text(v)

    @model_validator(mode="after")
    def _coherent(self):
        def unique(keys, what):
            seen = set()
            for k in keys:
                if k in seen:
                    raise ValueError(f"{self.module}: {what} repetido {k!r}")
                seen.add(k)
            return seen
        cases = unique([c.key for c in self.cases], "caso")
        links = unique([l.key for l in self.links], "ligação")
        unique([s.key for s in self.steps], "passo")
        if (self.scope == "map") != bool(self.item_model):
            raise ValueError(f"{self.module}: `item_model` só (e sempre) num módulo de mapa")
        placed: Dict[str, str] = {}
        for s in self.steps:
            if s.kind == "cases" and not self.cases:
                raise ValueError(f"{self.module}.{s.key}: passo de casos sem casos")
            for f in s.essential + s.advanced:
                if f in placed:
                    raise ValueError(f"{self.module}: campo {f!r} em dois passos ({placed[f]}, {s.key})")
                placed[f] = s.key
            bad = sorted(set(s.links) - links)
            if bad:
                raise ValueError(f"{self.module}.{s.key}: ligações inexistentes {bad}")
            if s.show_if:
                bad = sorted(set(s.show_if.case_in) - cases)
                if bad:
                    raise ValueError(f"{self.module}.{s.key}: casos inexistentes {bad}")
        return self

    def fields(self) -> List[str]:
        """Todos os campos citados pelos passos (essenciais e avançados)."""
        return [f for s in self.steps for f in s.essential + s.advanced]


# ── caminhos: existem mesmo no schema? ──────────────────────────────────────

def _item_model(model_name: str) -> Any:
    """O modelo do item de um módulo de mapa: no schema do perfil, no do Intake ou na forma de uma
    fonte de ingestão (`ingest_source.py`, só descritiva — não valida o perfil)."""
    from . import client_profile_schema as cps
    from . import ingest_source, intake_schema
    for mod in (cps, intake_schema, ingest_source):
        model = getattr(mod, model_name, None)
        if model is not None and hasattr(model, "model_fields"):
            return model
    return None


def _item_fields(model_name: str) -> Tuple[str, ...]:
    model = _item_model(model_name)
    if model is None:
        raise ValueError(f"item_model desconhecido {model_name!r}")
    return tuple(model.model_fields)


@lru_cache(maxsize=1)
def _known_profile_paths() -> frozenset:
    from . import exposure
    return frozenset(exposure.leaf_paths()) | frozenset(exposure.tool_config_shapes())


def _profile_path_exists(path: str) -> bool:
    if path in _known_profile_paths():
        return True
    # Um nó intermédio (ex.: `voice`) também é um caminho válido para um passo.
    if any(p.startswith(path + ".") for p in _known_profile_paths()):
        return True
    return any(path == pre or path.startswith(pre + ".") for pre in _UNTYPED_PREFIXES)


def _step_refs(g: ModuleGuide) -> List[str]:
    """Os campos citados pelas condições e pelo «feito» dos passos."""
    out: List[str] = []
    for s in g.steps:
        out += list(s.done_if)
        if s.show_if:
            out += list(s.show_if.any_present)
    return out


def _intake_templates() -> frozenset:
    from . import intake_library
    return frozenset(t["id"] for t in intake_library.list_templates())


#: Módulos cujos casos de uso partem de uma biblioteca que já existe no pacote: o `preset`
#: de cada caso tem de ser um id dessa biblioteca (um modelo apagado parte o percurso aqui).
_PRESET_SOURCES = {"intake": _intake_templates}


def _check_case_presets(g: ModuleGuide) -> None:
    with_preset = [c for c in g.cases if c.preset]
    if not with_preset:
        return
    source = _PRESET_SOURCES.get(g.module)
    if source is None:
        raise ValueError(f"{g.module}: casos com `preset` num módulo sem biblioteca de modelos")
    bad = sorted(c.preset for c in with_preset if c.preset not in source())
    if bad:
        raise ValueError(f"{g.module}: `preset` que não existe na biblioteca {bad}")


def _check_paths(g: ModuleGuide) -> None:
    if g.scope == "map":
        model = set(_item_fields(g.item_model or ""))
        clash = sorted(set(g.item_extras) & model)
        if clash:
            raise ValueError(f"{g.module}: item_extras que o modelo já declara: {clash}")
        item = model | set(g.item_extras)
        bad = sorted(f for f in g.fields() if f not in item)
        if bad:
            raise ValueError(f"{g.module}: campos que não existem em {g.item_model}: {bad}")
        # Uma gralha numa condição deixava o passo escondido (ou nunca «feito») sem erro.
        bad = sorted(f for f in _step_refs(g) if f not in item)
        if bad:
            raise ValueError(f"{g.module}: condições ou «feito» com campos inexistentes: {bad}")
        missing = sorted(item - set(g.fields()))
        if missing:
            raise ValueError(f"{g.module}: campos de {g.item_model} sem passo (ficavam sem ecrã): {missing}")
        if not _profile_path_exists(g.root):
            raise ValueError(f"{g.module}: raiz inexistente {g.root!r}")
    else:
        bad = sorted(f for f in g.fields() + _step_refs(g) if not _profile_path_exists(f))
        if bad:
            raise ValueError(f"{g.module}: caminhos inexistentes {bad}")
    bad = sorted(l.path for l in g.links if not _profile_path_exists(l.path))
    if bad:
        raise ValueError(f"{g.module}: ligações com caminhos inexistentes {bad}")


# ── carregar ────────────────────────────────────────────────────────────────

def _check(doc: Any, name: str) -> ModuleGuide:
    g = ModuleGuide.model_validate(doc)
    if name != f"{g.module}.json":
        raise ValueError(f"{name}: `module` diferente do nome do ficheiro")
    _check_paths(g)
    _check_case_presets(g)
    return g


@lru_cache(maxsize=1)
def _load() -> Tuple[Dict[str, Any], ...]:
    folder = resources.files(__package__).joinpath("module_guides")
    docs = []
    for entry in folder.iterdir():
        if entry.name.endswith(".json"):
            doc = json.loads(entry.read_text(encoding="utf-8"))
            docs.append(_check(doc, entry.name).model_dump(exclude_none=True))
    docs.sort(key=lambda d: (d["order"], d["module"]))
    return tuple(docs)


def list_guides() -> List[Dict[str, Any]]:
    """Os percursos de todos os módulos, por ordem (cópias)."""
    return copy.deepcopy(list(_load()))


def get_guide(module: str) -> Optional[Dict[str, Any]]:
    """O percurso de `module` (cópia) ou None."""
    for g in _load():
        if g["module"] == module:
            return copy.deepcopy(g)
    return None


def links_for(module: str) -> List[Dict[str, Any]]:
    """As ligações de `module`, dos DOIS lados. Cada ligação é declarada uma só vez, no
    percurso de quem a recebe (`direction: "in"`, `module` = de onde vem); o módulo de origem
    vê-a aqui invertida (`direction: "out"`, `module` = para onde vai). Nunca duas cópias."""
    out = []
    for g in _load():
        for link in g["links"]:
            if g["module"] == module:
                out.append(copy.deepcopy(link))
            elif link["module"] == module:
                flipped = "out" if link["direction"] == "in" else "in"
                out.append({**copy.deepcopy(link), "direction": flipped, "module": g["module"]})
    return out


# ── predefinições (os casos de uso, prontos a aplicar) ──────────────────────
#
# `module_guides/presets/<módulo>.<caso>.<língua>.json` — GERADAS a partir do código do editor
# do Studio (`frontend/scripts/queue-presets.mjs`, `docver-presets.mjs`), que tem um teste de paridade contra
# estes ficheiros: nunca se editam à mão. `item` é o item do mapa (ex.: uma fila), validado aqui com o
# modelo do schema; `links` = ligações do percurso que o caso liga; `human` = campos do item que
# ficam por preencher por uma pessoa (ex.: o servidor do ERP do cliente). Num módulo de PERFIL cuja raiz é
# um bloco de `tools.config` (3 Nov 2026, verificação documental), `config` é esse bloco, validado com o
# modelo da tool.

#: As chaves de uma predefinição de um módulo de PERFIL.
_PROFILE_PRESET_KEYS = {"module", "case", "lang", "config", "links", "features", "human"}


def _root_tool_model(root: str) -> Any:
    """O modelo do bloco `tools.config.<tool>` da raiz de um percurso de perfil; None se a raiz não for um."""
    head, _, tool = root.rpartition(".")
    if head != "tools.config":
        return None
    from . import tool_config_models
    return tool_config_models().get(tool)

def _check_preset(doc: Any, name: str, guides: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        raise ValueError(f"{name}: não é um objeto")
    module, case, lang = doc.get("module"), doc.get("case"), doc.get("lang")
    if name != f"{module}.{case}.{lang}.json":
        raise ValueError(f"{name}: nome diferente de <module>.<case>.<lang>.json")
    g = guides.get(module)
    if g is None:
        raise ValueError(f"{name}: módulo sem percurso {module!r}")
    cases = {c["key"]: c for c in g.get("cases", [])}
    if case not in cases:
        raise ValueError(f"{name}: caso inexistente no percurso {case!r}")
    if cases[case].get("available") is False:
        raise ValueError(f"{name}: caso em preparação não tem predefinição")
    if lang not in GUIDE_LANGS:
        raise ValueError(f"{name}: língua fora de {GUIDE_LANGS}")
    bad = sorted(set(doc.get("links") or []) - {l["key"] for l in g.get("links", [])})
    if bad:
        raise ValueError(f"{name}: ligações inexistentes {bad}")
    feats = doc.get("features") or {}
    if not isinstance(feats, dict) or any(not isinstance(v, bool) for v in feats.values()):
        raise ValueError(f"{name}: `features` tem de ser {{flag: true|false}}")
    from . import exposure
    known_flags = {p.split(".", 2)[2] for p in exposure.leaf_paths() if p.startswith("frontend.features.")}
    bad = sorted(set(feats) - known_flags)
    if bad:
        raise ValueError(f"{name}: features inexistentes {bad}")
    # `human` = caminhos DENTRO do item (ex.: `onValidate.server`): o 1.º nível tem de existir.
    if g["scope"] == "map":
        allowed = set(g.get("item_extras") or [])
        allowed |= set(_item_model(g["item_model"]).model_fields)
        bad = sorted(h for h in doc.get("human") or [] if str(h).split(".", 1)[0] not in allowed)
        if bad:
            raise ValueError(f"{name}: `human` com campos inexistentes {bad}")
    if g["scope"] == "map":
        _item_model(g["item_model"]).model_validate(doc.get("item") or {})
        # A chave do item no mapa (ex.: «encomendas», «pedidos-agente»).
        if not re.fullmatch(r"^[a-z][a-z0-9_-]{0,39}$", str(doc.get("key") or "")):
            raise ValueError(f"{name}: `key` inválida")
    else:
        model = _root_tool_model(g["root"])
        if model is None:
            raise ValueError(f"{name}: predefinição num percurso de perfil sem bloco de tools.config")
        if "item" in doc or "key" in doc:
            raise ValueError(f"{name}: `item`/`key` só em módulos de mapa (aqui é `config`)")
        if not isinstance(doc.get("config"), dict):
            raise ValueError(f"{name}: falta `config` (o bloco {g['root']})")
        # O modelo da tool aceita chaves a mais (`extra="allow"`): uma gralha no gerador passava em silêncio.
        bad = sorted(set(doc) - _PROFILE_PRESET_KEYS)
        if bad:
            raise ValueError(f"{name}: chaves desconhecidas na predefinição {bad}")
        bad = sorted(set(doc["config"]) - set(model.model_fields))
        if bad:
            raise ValueError(f"{name}: `config` com campos inexistentes {bad}")
        model.model_validate(doc["config"])
        bad = sorted(h for h in doc.get("human") or [] if str(h).split(".", 1)[0] not in model.model_fields)
        if bad:
            raise ValueError(f"{name}: `human` com campos inexistentes {bad}")
    return doc


@lru_cache(maxsize=1)
def _load_presets() -> Tuple[Dict[str, Any], ...]:
    guides = {g["module"]: g for g in _load()}
    folder = resources.files(__package__).joinpath("module_guides").joinpath("presets")
    docs = []
    if folder.is_dir():
        for entry in folder.iterdir():
            if entry.name.endswith(".json"):
                docs.append(_check_preset(json.loads(entry.read_text(encoding="utf-8")), entry.name, guides))
    docs.sort(key=lambda d: (d["module"], d["case"], d["lang"]))
    return tuple(docs)


def list_presets(module: Optional[str] = None, lang: Optional[str] = None) -> List[Dict[str, Any]]:
    """As predefinições (cópias), filtradas por módulo e língua."""
    return [copy.deepcopy(p) for p in _load_presets()
            if (module is None or p["module"] == module) and (lang is None or p["lang"] == lang)]


def get_preset(module: str, case: str, lang: str) -> Optional[Dict[str, Any]]:
    for p in _load_presets():
        if (p["module"], p["case"], p["lang"]) == (module, case, lang):
            return copy.deepcopy(p)
    return None
