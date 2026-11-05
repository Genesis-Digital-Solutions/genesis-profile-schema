"""
genesis_profile_schema/queue_summaries.py — tabelas-resumo e totais CALCULADOS de
uma fila (`reviewQueues.<fila>.summaryTables` / `summaryTotals`, v0.1.157) e o
destino de ação «fica no mesmo estado» (`actions[].to == "@same"`).

O PRODUTOR do contrato é o genai-core:
  - `core/managers/review_queue_summaries.py` (`public_summary_tables` /
    `public_summary_totals`) valida a forma e passa-a ao fecore em
    `queue_options[<fila>].summary_tables` / `summary_totals`;
  - o fecore (`review-queue-summaries.ts`) calcula ao vivo a partir das linhas
    do payload (agrupa, soma, multiplica) — nada é gravado, exceto o total com
    `field`, que vai para esse campo do payload;
  - `core/managers/review_queue_spec.py` (`SAME_STATE`/`resolve_target`) lê o
    `@same`.

Até à v0.1.156 estes campos viviam no `extra="allow"` da fila sem regras: o
core larga uma entrada partida em silêncio (só com aviso no log) e a fila
desenha-se sem ela. Aqui as MESMAS regras recusam-na ao gravar, com a razão —
nunca cortar em silêncio. Os limites (5 tabelas/totais, 20 colunas, rótulos de
80 caracteres) são os do core: acima deles o core cortava sem dizer.

Forma de uma tabela-resumo (todas as colunas são chaves das linhas de `source`
ou do payload):
    {
      "key": "transporte",                  # obrigatório, único na fila
      "label": "Transporte" | {"pt": …},    # opcional
      "source": "artigos",                  # array de linhas do payload
      "groupBy": ["codigo_transporte", …],  # ≥ 1 coluna
      "sum": "toneladas",                   # coluna somada por grupo
      "sumWhenSingle": "total_toneladas",   # campo do payload que vale com UM grupo
      "multiply": "preco_custo_extra",      # valor = soma × esta coluna
      "requires": [...], "carry": [...], "header": [...],
      "hideSourceColumns": [...],           # colunas da tabela de origem escondidas
      "editable": [...],                    # só colunas de groupBy/carry
      "columnLabels": {"toneladas": "Toneladas" | {"pt": …}},
      "valueLabels": {"codigo_transporte": {"920306": "920306 Granel"}}
    }
Forma de um total:
    {
      "key": "total_estimado",
      "label": … (opcional),
      "after": "artigos",                   # tabela de origem sob a qual se desenha
      "field": "valor_total",               # ou: o total VAI para este campo
      "add": [{"source": "artigos", "column": "valor", "label": …},
              {"summary": "transporte", "label": …}],   # ≥ 1 parte
      "references": [{"field": "valor_total", "label": …}]  # opcional
    }
"""

from __future__ import annotations

import re
from typing import Annotated, Dict, List, Optional, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

#: Destino reservado de uma ação: fica no estado de onde partiu (a não ser que
#: um gate desvie) e o operador não perde o claim. ⚠️ Um core anterior ao
#: commit 145e88a0 recusa a LISTA INTEIRA de ações da fila (cai para a máquina
#: embutida) — o Studio confirma a versão do core antes de o gravar.
SAME_STATE = "@same"

#: Os limites do core (`review_queue_summaries._MAX_TABLES` / `_MAX_COLS`).
MAX_SUMMARY_TABLES = 5
MAX_SUMMARY_COLUMNS = 20
MAX_SUMMARY_LABEL = 80
MAX_VALUE_LABEL_KEY = 64

_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

I18nMap = Dict[str, str]
#: Texto de uma coluna ou de um valor: `"texto"` ou `{"pt": …, "en": …}`. Alias
#: próprio de propósito: `columnLabels` é um mapa COLUNA → texto, não um mapa
#: de línguas — com `I18nMap` no nome o `i18n_field_paths` marcava o mapa
#: inteiro como multilíngue.
SummaryText = Union[str, Dict[str, str]]


def _col(v: str, what: str) -> str:
    s = str(v or "").strip()
    if not _KEY_RE.match(s):
        raise ValueError(f"{what}: {s[:40]!r} não é uma chave válida (letras, números, «.», «_», «-»; até 64)")
    return s


def _cols(v: Optional[List[str]], what: str) -> Optional[List[str]]:
    if v is None:
        return None
    if len(v) > MAX_SUMMARY_COLUMNS:
        raise ValueError(f"{what}: no máximo {MAX_SUMMARY_COLUMNS} colunas")
    out: List[str] = []
    for x in v:
        k = _col(x, what)
        if k in out:
            raise ValueError(f"{what}: coluna repetida {k!r}")
        out.append(k)
    return out


def _text(v, what: str):
    """Rótulo `str` ou `{língua: str}`: não vazio, até 80 caracteres."""
    if v is None:
        return None
    if isinstance(v, str):
        if not v.strip():
            raise ValueError(f"{what}: rótulo vazio")
        if len(v.strip()) > MAX_SUMMARY_LABEL:
            raise ValueError(f"{what}: rótulo com mais de {MAX_SUMMARY_LABEL} caracteres")
        return v.strip()
    if isinstance(v, dict):
        out = {}
        for lang, t in v.items():
            if not isinstance(t, str):
                raise ValueError(f"{what}: o texto de {lang!r} tem de ser texto")
            if t.strip():
                if len(t.strip()) > MAX_SUMMARY_LABEL:
                    raise ValueError(f"{what}: rótulo ({lang}) com mais de {MAX_SUMMARY_LABEL} caracteres")
                out[str(lang)] = t.strip()
        if not out:
            raise ValueError(f"{what}: rótulo vazio")
        return out
    raise ValueError(f"{what}: rótulo tem de ser texto ou {{língua: texto}}")


class ProfileQueueSummaryTable(BaseModel):
    """Uma tabela-resumo calculada (ver o docstring do módulo)."""
    model_config = ConfigDict(extra="allow")
    key: str
    label: Optional[Union[str, I18nMap]] = None
    source: str
    groupBy: List[str] = Field(min_length=1)
    sum: str
    sumWhenSingle: Optional[str] = None
    multiply: Optional[str] = None
    requires: Optional[List[str]] = None
    carry: Optional[List[str]] = None
    header: Optional[List[str]] = None
    hideSourceColumns: Optional[List[str]] = None
    editable: Optional[List[str]] = None
    columnLabels: Optional[Dict[str, SummaryText]] = None
    valueLabels: Optional[Dict[str, Dict[str, SummaryText]]] = None

    @field_validator("key", "source", "sum")
    @classmethod
    def _required_key(cls, v, info):
        return _col(v, info.field_name)

    @field_validator("sumWhenSingle", "multiply")
    @classmethod
    def _optional_key(cls, v, info):
        if v is None or not str(v).strip():
            return None
        return _col(v, info.field_name)

    @field_validator("groupBy", "requires", "carry", "header", "hideSourceColumns", "editable")
    @classmethod
    def _key_lists(cls, v, info):
        return _cols(v, info.field_name)

    @field_validator("label", mode="before")
    @classmethod
    def _label(cls, v):
        return _text(v, "label")

    @field_validator("columnLabels", mode="before")
    @classmethod
    def _column_labels(cls, v):
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("columnLabels tem de ser {coluna: rótulo}")
        return {_col(k, "columnLabels"): _text(t, f"columnLabels.{k}") for k, t in v.items()}

    @field_validator("valueLabels", mode="before")
    @classmethod
    def _value_labels(cls, v):
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("valueLabels tem de ser {coluna: {valor: rótulo}}")
        out = {}
        for col, m in v.items():
            c = _col(col, "valueLabels")
            if not isinstance(m, dict):
                raise ValueError(f"valueLabels.{c} tem de ser {{valor: rótulo}}")
            inner = {}
            for val, t in m.items():
                sval = str(val)
                if not sval.strip() or len(sval) > MAX_VALUE_LABEL_KEY:
                    raise ValueError(f"valueLabels.{c}: valor vazio ou com mais de {MAX_VALUE_LABEL_KEY} caracteres")
                inner[sval] = _text(t, f"valueLabels.{c}.{sval[:20]}")
            out[c] = inner
        return out

    @model_validator(mode="after")
    def _editable_in_rows(self):
        # O core (2.5b) só aceita editar colunas que existem nas linhas: as de
        # groupBy e carry. A soma e o valor são calculados.
        ed = self.editable or []
        allowed = set(self.groupBy) | set(self.carry or [])
        bad = [c for c in ed if c not in allowed]
        if bad:
            raise ValueError(f"editable: {', '.join(bad[:5])} não está em groupBy nem em carry "
                             "(só essas colunas se editam na tabela-resumo)")
        return self


class ProfileQueueSummaryPart(BaseModel):
    """Uma parte somada num total: uma coluna das linhas (`source` + `column`)
    OU o `valor` de uma tabela-resumo (`summary`)."""
    model_config = ConfigDict(extra="allow")
    source: Optional[str] = None
    column: Optional[str] = None
    summary: Optional[str] = None
    label: Optional[Union[str, I18nMap]] = None

    @field_validator("source", "column", "summary")
    @classmethod
    def _keys(cls, v, info):
        if v is None or not str(v).strip():
            return None
        return _col(v, info.field_name)

    @field_validator("label", mode="before")
    @classmethod
    def _label(cls, v):
        return _text(v, "add.label")

    @model_validator(mode="after")
    def _one_kind(self):
        rows = bool(self.source and self.column)
        if rows == bool(self.summary) or (not rows and (self.source or self.column)):
            raise ValueError("cada parte do total é uma coluna das linhas (source + column) "
                             "OU uma tabela-resumo (summary), nunca as duas")
        return self


class ProfileQueueSummaryReference(BaseModel):
    """Um campo do payload mostrado AO LADO do total (ex.: o total que veio no pedido)."""
    model_config = ConfigDict(extra="allow")
    field: str
    label: Optional[Union[str, I18nMap]] = None

    @field_validator("field")
    @classmethod
    def _field(cls, v):
        return _col(v, "references.field")

    @field_validator("label", mode="before")
    @classmethod
    def _label(cls, v):
        return _text(v, "references.label")


class ProfileQueueSummaryTotal(BaseModel):
    """Um total calculado (ver o docstring do módulo)."""
    model_config = ConfigDict(extra="allow")
    key: str
    label: Optional[Union[str, I18nMap]] = None
    after: Optional[str] = None
    field: Optional[str] = None
    add: List[ProfileQueueSummaryPart] = Field(min_length=1, max_length=MAX_SUMMARY_COLUMNS)
    references: Optional[List[ProfileQueueSummaryReference]] = Field(default=None, max_length=MAX_SUMMARY_COLUMNS)

    @field_validator("key")
    @classmethod
    def _key(cls, v):
        return _col(v, "key")

    @field_validator("after", "field")
    @classmethod
    def _opt(cls, v, info):
        if v is None or not str(v).strip():
            return None
        k = _col(v, info.field_name)
        if info.field_name == "field" and k.startswith("_"):
            raise ValueError("field: campos começados por «_» são internos do motor")
        return k

    @field_validator("label", mode="before")
    @classmethod
    def _label(cls, v):
        return _text(v, "label")

    @model_validator(mode="after")
    def _where(self):
        if not (self.after or self.field):
            raise ValueError("o total precisa de «after» (a tabela sob a qual se desenha) "
                             "ou de «field» (o campo do pedido onde fica)")
        return self


def _unique(kind: str):
    def check(value):
        if value is None:
            return value
        if len(value) > MAX_SUMMARY_TABLES:
            raise ValueError(f"{kind}: no máximo {MAX_SUMMARY_TABLES}")
        keys = [t.key for t in value]
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            raise ValueError(f"{kind} com a mesma key: {', '.join(dup[:5])}")
        return value
    return check


QueueSummaryTables = Annotated[List[ProfileQueueSummaryTable], AfterValidator(_unique("summaryTables"))]
QueueSummaryTotals = Annotated[List[ProfileQueueSummaryTotal], AfterValidator(_unique("summaryTotals"))]


def check_summary_references(tables, totals) -> None:
    """Uma parte `summary` tem de nomear uma tabela-resumo da MESMA fila (o core
    largava a parte em silêncio). Levanta `ValueError` com a razão."""
    keys = {t.key for t in (tables or [])}
    for tot in totals or []:
        for p in tot.add:
            if p.summary and p.summary not in keys:
                raise ValueError(f"summaryTotals.{tot.key}: a parte «summary: {p.summary}» não nomeia "
                                 "nenhuma tabela-resumo desta fila")


__all__ = [
    "MAX_SUMMARY_COLUMNS",
    "MAX_SUMMARY_LABEL",
    "MAX_SUMMARY_TABLES",
    "ProfileQueueSummaryPart",
    "ProfileQueueSummaryReference",
    "ProfileQueueSummaryTable",
    "ProfileQueueSummaryTotal",
    "QueueSummaryTables",
    "QueueSummaryTotals",
    "SAME_STATE",
    "check_summary_references",
]
