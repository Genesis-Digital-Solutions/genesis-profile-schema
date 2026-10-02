"""
genesis_profile_schema/field_definition.py — a definição de campo ÚNICA do
produto (v0.1.79, 2 Out 2026; épico Plataforma de módulos §7, decisão 1).

Um campo declarado num perfil — uma pergunta de um questionário regulado, um
campo do detalhe de um pedido da fila, um dado do cabeçalho de um caso — tem
uma só forma. Estende os 6 tipos do visual `form` do genai-core (`text`,
`textarea`, `number`, `date`, `select`, `checkbox`) com o que os processos
regulados pedem (`multiselect`, `money`, `datetime`, `year`, `table`), sem
mudar o significado dos seis.

Tudo é NOVO (sem perfis antigos a preservar): `extra="forbid"` em cada
modelo, para uma chave inventada dar erro ao gravar em vez de inchar o perfil
(a lição das vagas-tipo, revisão de 23 Set). Textos e listas com tectos: isto
é conteúdo vindo de um editor, logo input externo.

Os valores destes campos (as RESPOSTAS) nunca são HTML nem instruções: quem os
desenha interpola, nunca `innerHTML` (regra do fecore).
"""

from __future__ import annotations

import math
import re
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from .rules_grammar import KEY_PATTERN

__all__ = [
    "FORM_FIELD_TYPES",
    "FIELD_TYPES",
    "StrictNumber",
    "I18nText",
    "FieldOption",
    "TableColumn",
    "FieldDefinition",
]

_CLOSED = ConfigDict(extra="forbid")

# Os seis do `form()` do genai-core (`core/agent/visual_contract.py`,
# `_FORM_FIELD_TYPES`) — mantêm o significado. Os restantes são a extensão.
FORM_FIELD_TYPES = ("text", "textarea", "number", "date", "select", "checkbox")
FIELD_TYPES = FORM_FIELD_TYPES + ("multiselect", "money", "datetime", "year", "table")

MAX_LABEL = 2000          # uma pergunta regulada bilingue pode ser longa
MAX_HELP = 4000
MAX_OPTIONS = 100
MAX_COLUMNS = 30
MAX_LANGS = 10
MAX_CURRENCIES = 60

_LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_CURRENCY_RE = r"^[A-Z]{3}$"
_MAX_ABS_NUMBER = 1e15


def _strict_number(value: Any) -> Any:
    """Número a sério: `true` e `"5"` NÃO são números (o modo lax do Pydantic
    convertia-os — revisão independente de 2 Out). Finito e com tecto."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("tem de ser um número")
    try:
        f = float(value)
    except OverflowError:
        raise ValueError("número fora dos limites") from None
    if not math.isfinite(f) or abs(f) > _MAX_ABS_NUMBER:
        raise ValueError("número fora dos limites")
    return f


StrictNumber = Annotated[float, BeforeValidator(_strict_number)]


def _i18n_checker(max_len: int, required: bool):
    def check(value: Dict[str, str]) -> Dict[str, str]:
        if required and not value:
            raise ValueError("texto obrigatório em pelo menos uma língua")
        if len(value) > MAX_LANGS:
            raise ValueError(f"no máximo {MAX_LANGS} línguas")
        for lang, text in value.items():
            if not _LANG_RE.match(lang):
                raise ValueError(f"código de língua inválido: {lang!r}")
            if len(text) > max_len:
                raise ValueError(f"texto em {lang!r} com mais de {max_len} caracteres")
            if required and not text.strip():
                raise ValueError(f"texto em {lang!r} vazio")
        return value
    return check


# {língua: texto}. Mesma forma do `I18nMap` do resto do perfil, com regras.
I18nText = Annotated[Dict[str, str], AfterValidator(_i18n_checker(MAX_LABEL, True))]
I18nHelp = Annotated[Dict[str, str], AfterValidator(_i18n_checker(MAX_HELP, False))]

FieldKey = Annotated[str, Field(pattern=KEY_PATTERN)]
FieldType = Literal["text", "textarea", "number", "date", "select", "checkbox",
                    "multiselect", "money", "datetime", "year", "table"]


class FieldOption(BaseModel):
    """Uma opção de `select`/`multiselect`. O `value` é o que se grava e o que
    as regras comparam; o `label` é só apresentação."""
    model_config = _CLOSED

    value: FieldKey
    label: I18nText


class TableColumn(BaseModel):
    """Coluna de um campo `table`. Sem tabelas dentro de tabelas."""
    model_config = _CLOSED

    key: FieldKey
    label: I18nText
    type: Literal["text", "number", "date", "select", "checkbox", "money", "year"] = "text"
    options: List[FieldOption] = Field(default_factory=list, max_length=MAX_OPTIONS)
    required: bool = False


class FieldDefinition(BaseModel):
    """Um campo, com o que é preciso para o desenhar, validar e auditar.

    - `required`: o ECRÃ pede a resposta antes de submeter (experiência de
      preenchimento). Não decide resultados: num questionário com metodologia,
      a completude que decide é `methodology.required` (uma regra aprovada),
      e uma pergunta pode ser obrigatória no ecrã sem ser essencial ao
      resultado, ou ao contrário.
    - `allow_unknown`: aceita a resposta «não sei precisar» em `number`,
      `money` e `year` (valor sentinela `"unknown"`) — diferente de vazio.
    - `editable=False`: mostra-se mas não se altera (ex.: valor confirmado).
    - `hidden=True`: existe no registo mas não se mostra.
    - `citation`: o valor pode vir com o excerto de um documento de onde foi
      extraído (o ecrã mostra a origem; a verificação do excerto é do core).
    """
    model_config = _CLOSED

    key: FieldKey
    label: I18nText
    help: I18nHelp = Field(default_factory=dict)
    type: FieldType = "text"
    required: bool = False
    options: List[FieldOption] = Field(default_factory=list, max_length=MAX_OPTIONS)
    columns: List[TableColumn] = Field(default_factory=list, max_length=MAX_COLUMNS)
    currencies: List[Annotated[str, Field(pattern=_CURRENCY_RE)]] = Field(
        default_factory=list, max_length=MAX_CURRENCIES)
    min: Optional[StrictNumber] = None
    max: Optional[StrictNumber] = None
    integer: bool = False
    max_length: int = Field(default=2000, ge=1, le=20000)
    allow_unknown: bool = False
    order: int = Field(default=0, ge=0, le=100000)
    group: str = Field(default="", max_length=64)
    editable: bool = True
    hidden: bool = False
    citation: bool = False

    @model_validator(mode="after")
    def _coerente(self) -> "FieldDefinition":
        choice = self.type in ("select", "multiselect")
        if choice and not self.options:
            raise ValueError(f"campo {self.key!r}: '{self.type}' precisa de opções")
        if not choice and self.options:
            raise ValueError(f"campo {self.key!r}: só select/multiselect têm opções")
        values = [o.value for o in self.options]
        if len(values) != len(set(values)):
            raise ValueError(f"campo {self.key!r}: valores de opções repetidos")
        if self.type == "table" and not self.columns:
            raise ValueError(f"campo {self.key!r}: 'table' precisa de colunas")
        if self.type != "table" and self.columns:
            raise ValueError(f"campo {self.key!r}: só 'table' tem colunas")
        cols = [c.key for c in self.columns]
        if len(cols) != len(set(cols)):
            raise ValueError(f"campo {self.key!r}: colunas repetidas")
        for c in self.columns:
            if c.type == "select" and not c.options:
                raise ValueError(f"campo {self.key!r}: coluna {c.key!r} precisa de opções")
        if self.currencies and self.type != "money":
            raise ValueError(f"campo {self.key!r}: só 'money' tem moedas")
        if self.allow_unknown and self.type not in ("number", "money", "year"):
            raise ValueError(f"campo {self.key!r}: 'não sei precisar' só em number/money/year")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"campo {self.key!r}: min maior do que max")
        return self
