"""
genesis_profile_schema/field_values.py — validação de VALORES contra a
definição de campo única (v0.1.79, 2 Out 2026; revisão independente).

Uma resposta é input externo hostil (vem de um formulário público): antes de
tocar em qualquer regra é confrontada com o tipo da pergunta. Sem isto, um
`True` num «Sim/Não», uma lista num campo de escolha única ou um número
enorme contavam como resposta e mudavam o resultado em silêncio.

O mesmo validador serve o motor de regras do genai-core, os casos de
referência (ao gravar o perfil) e, depois, a API do percurso — uma regra só.

Normalização (deliberada e pequena):
  * vazio (`None`, texto só com espaços, lista ou objeto vazio) = AUSENTE —
    também numa escolha múltipla: `[]` é «sem resposta». Uma escolha múltipla
    obrigatória precisa por isso de uma opção do tipo «nenhuma/outra»;
  * um número inteiro escrito como `10.0` num campo `integer`/`year` passa a 10;
  * datas na forma ISO estendida, devolvidas canónicas;
  * nada mais é convertido: `"10"` num número é erro, não 10.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, Mapping, Optional

from .field_definition import FieldDefinition, TableColumn

__all__ = [
    "UNKNOWN",
    "iso_value",
    "number_fits",
    "MAX_ABS_NUMBER",
    "AnswersCheck",
    "is_empty",
    "validate_field_value",
    "validate_answers",
]

UNKNOWN = "unknown"            # «não sei precisar» (só onde `allow_unknown`)
MAX_ABS_NUMBER = 1e15
MAX_TABLE_ROWS = 200
MAX_CELL_TEXT = 2000
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_DEFAULT_YEAR_MIN, _DEFAULT_YEAR_MAX = 1000, 3000

_SKIP = object()


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _real(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what}: tem de ser um número")
    try:
        f = float(value)
    except OverflowError:
        raise ValueError(f"{what}: número fora dos limites") from None
    if not math.isfinite(f) or abs(f) > MAX_ABS_NUMBER:
        raise ValueError(f"{what}: número fora dos limites")
    return f


def _integral(value: Any, what: str) -> int:
    f = _real(value, what)
    if not f.is_integer():
        raise ValueError(f"{what}: tem de ser um número inteiro")
    return int(f)


def _bounds(f: float, lo: Optional[float], hi: Optional[float], what: str) -> None:
    if lo is not None and f < lo:
        raise ValueError(f"{what}: abaixo do mínimo {lo:g}")
    if hi is not None and f > hi:
        raise ValueError(f"{what}: acima do máximo {hi:g}")


def _money(value: Any, currencies: Iterable[str], what: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"amount", "currency"}:
        raise ValueError(f"{what}: montante tem de ser {{amount, currency}}")
    amount = _real(value["amount"], f"{what}.amount")
    if amount < 0:
        raise ValueError(f"{what}: montante negativo")
    currency = value["currency"]
    if not isinstance(currency, str) or not _CURRENCY_RE.match(currency):
        raise ValueError(f"{what}: moeda inválida (código ISO de 3 letras)")
    allowed = list(currencies)
    if allowed and currency not in allowed:
        raise ValueError(f"{what}: moeda {currency} não aceite neste campo")
    return {"amount": value["amount"], "currency": currency}


def _text(value: Any, max_len: int, what: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{what}: tem de ser texto")
    if len(value) > max_len:
        raise ValueError(f"{what}: texto com mais de {max_len} caracteres")
    return value


# Só a forma ISO estendida (o Python 3.11+ aceitaria também «20000101» ou
# «2000-W01-6», que depois não batiam com um literal «2000-01-01»).
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})?$")


def _iso(value: Any, kind: str, what: str) -> str:
    """Data/data-hora ISO estendida, devolvida na forma canónica
    (`isoformat()`), para as comparações por igualdade baterem sempre."""
    pattern = _DATE_RE if kind == "date" else _DATETIME_RE
    if not isinstance(value, str) or len(value) > 40 or not pattern.match(value):
        raise ValueError(f"{what}: {kind} em formato ISO (AAAA-MM-DD)")
    try:
        if kind == "date":
            return date.fromisoformat(value).isoformat()
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        raise ValueError(f"{what}: {kind} inválida") from None


def iso_value(value: Any, kind: str) -> str:
    """Forma canónica de uma data (`kind="date"`) ou data-hora ISO, ou
    ValueError — serve também para confirmar literais de condições."""
    return _iso(value, kind, "valor")


def number_fits(fd: FieldDefinition, value: Any) -> bool:
    """Um número que uma resposta VÁLIDA a este campo podia ter (inteiro onde
    é inteiro, dentro de min/max; num ano, os limites por omissão)."""
    try:
        if fd.type == "year":
            y = _integral(value, "valor")
            _bounds(y, fd.min if fd.min is not None else _DEFAULT_YEAR_MIN,
                    fd.max if fd.max is not None else _DEFAULT_YEAR_MAX, "valor")
        else:
            f = _integral(value, "valor") if fd.integer else _real(value, "valor")
            _bounds(f, fd.min, fd.max, "valor")
    except ValueError:
        return False
    return True


def _cell(col: TableColumn, value: Any, what: str) -> Any:
    if col.type == "text":
        return _text(value, MAX_CELL_TEXT, what)
    if col.type == "number":
        _real(value, what)
        return value
    if col.type == "year":
        return _integral(value, what)
    if col.type == "date":
        return _iso(value, "date", what)
    if col.type == "checkbox":
        if not isinstance(value, bool):
            raise ValueError(f"{what}: verdadeiro ou falso")
        return value
    if col.type == "select":
        if not isinstance(value, str) or value not in {o.value for o in col.options}:
            raise ValueError(f"{what}: opção inválida")
        return value
    if col.type == "money":
        return _money(value, (), what)
    raise ValueError(f"{what}: tipo de coluna desconhecido")


def validate_field_value(fd: FieldDefinition, value: Any) -> Any:
    """Devolve o valor normalizado, `None` se for vazio, ou levanta ValueError."""
    what = fd.key
    if is_empty(value):
        return None
    if value == UNKNOWN and isinstance(value, str):
        if fd.allow_unknown:
            return UNKNOWN
        raise ValueError(f"{what}: «não sei precisar» não é aceite neste campo")
    t = fd.type
    if t in ("text", "textarea"):
        return _text(value, fd.max_length, what)
    if t == "number":
        if fd.integer:
            n = _integral(value, what)
            _bounds(n, fd.min, fd.max, what)
            return n
        f = _real(value, what)
        _bounds(f, fd.min, fd.max, what)
        return value
    if t == "year":
        y = _integral(value, what)
        _bounds(y, fd.min if fd.min is not None else _DEFAULT_YEAR_MIN,
                fd.max if fd.max is not None else _DEFAULT_YEAR_MAX, what)
        return y
    if t == "money":
        return _money(value, fd.currencies, what)
    if t in ("date", "datetime"):
        return _iso(value, t, what)
    if t == "checkbox":
        if not isinstance(value, bool):
            raise ValueError(f"{what}: verdadeiro ou falso")
        return value
    options = {o.value for o in fd.options}
    if t == "select":
        if not isinstance(value, str) or value not in options:
            raise ValueError(f"{what}: opção inválida")
        return value
    if t == "multiselect":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{what}: lista de opções")
        if len(set(value)) != len(value):
            raise ValueError(f"{what}: opções repetidas")
        bad = [v for v in value if v not in options]
        if bad:
            raise ValueError(f"{what}: opções inválidas")
        return list(value)
    if t == "table":
        if not isinstance(value, list) or len(value) > MAX_TABLE_ROWS:
            raise ValueError(f"{what}: até {MAX_TABLE_ROWS} linhas")
        cols = {c.key: c for c in fd.columns}
        rows = []
        for i, row in enumerate(value):
            if not isinstance(row, dict) or set(row) - set(cols):
                raise ValueError(f"{what}[{i}]: colunas inválidas")
            clean = {}
            for key, col in cols.items():
                cell = row.get(key)
                if is_empty(cell):
                    if col.required:
                        raise ValueError(f"{what}[{i}].{key}: obrigatório")
                    continue
                clean[key] = _cell(col, cell, f"{what}[{i}].{key}")
            rows.append(clean)
        return rows
    raise ValueError(f"{what}: tipo desconhecido {t!r}")


@dataclass
class AnswersCheck:
    clean: Dict[str, Any] = field(default_factory=dict)          # só respostas válidas e não vazias
    errors: Dict[str, str] = field(default_factory=dict)         # pergunta → motivo (sem o valor)
    unknown_keys: int = 0                                        # chaves que não são perguntas (contadas, não listadas)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_answers(fields: Iterable[FieldDefinition], answers: Any) -> AnswersCheck:
    """Confronta cada resposta com a sua pergunta. Chaves desconhecidas são
    CONTADAS e descartadas (nunca ecoadas: podiam ser lixo arbitrário)."""
    if not isinstance(answers, Mapping):
        raise ValueError("respostas têm de ser um objeto {pergunta: valor}")
    by_key = {f.key: f for f in fields}
    out = AnswersCheck()
    for key, value in answers.items():
        fd = by_key.get(key) if isinstance(key, str) else None
        if fd is None:
            out.unknown_keys += 1
            continue
        try:
            clean = validate_field_value(fd, value)
        except ValueError as e:
            out.errors[key] = str(e)
            continue
        if clean is not None:
            out.clean[key] = clean
    return out
