"""
pattern_guard.py — a regra do save para as regex de códigos de produto do
cliente (`product_identification.patterns`): só entram padrões com custo de
execução limitado.

Nasceu no core (`config/profile_pattern_guard.py`, 14 Nov 2026) e mudou-se para
aqui na v0.1.171 (17 Nov 2026) para haver UMA regra: o core recusa o save com
ela e o backoffice do cliente (GAIBO) pode avisar antes do save com a mesma
resposta. O `regex_risk()` do `field_checks.py` é outra coisa — um aviso de
editor, heurístico e mais largo; quem decide se um padrão grava é este módulo.

O campo é de escrita do cliente e as regex correm com o `re` do Python sobre a
pergunta e a resposta, sem limite de tempo. A garantia vem de duas peças:

* **execução palavra a palavra** (no core, `core/agent/product_identification.py`):
  os padrões correm sobre cada palavra (sem espaços) com no máximo
  `TOKEN_MAX_CHARS` caracteres;
* **orçamento do padrão** (aqui): o custo de UMA tentativa de casar é estimado
  pelo produto das larguras dos quantificadores (aberto `+`/`*`/`{n,}` conta
  `TOKEN_MAX_CHARS`), com teto `COST_MAX` por padrão e `TOTAL_COST_MAX` somado.
  Recusa-se o que não tem custo limitado: quantificador variável dentro de um
  que repete (`(a+)+`, `(?:\\d?\\d?){12}`), alternativa dentro de quantificador
  (`(a|ab)*`), referências a grupos (`\\1`), espaço no padrão (nunca casaria
  palavra a palavra) e padrões longos ou em número a mais.

O modelo é pessimista (multiplica quantificadores seguidos mesmo de classes
disjuntas): `[A-Z]+\\d+` é recusado e escreve-se `[A-Z]{1,8}\\d{1,12}`.

Motivos (estáveis — são contrato com o core e o GAIBO): `empty`,
`not_a_string`, `too_long`, `invalid_regex`, `nested_quantifier`,
`alternation_in_quantifier`, `backreference`, `whitespace`, `too_costly`; na
lista: `not_a_list`, `too_many`, `too_costly_total`. As mensagens levam o
caminho e o motivo, nunca o valor (vem do cliente).

Não é um validador do modelo de propósito: o core carrega perfis antigos com
padrões que hoje se recusam e não pode deixar de arrancar por isso (a execução
salta-os com aviso).
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, List, Optional

try:                                    # Python ≥ 3.11
    import re._constants as _c
    import re._parser as _parser
except ImportError:                     # pragma: no cover — Python < 3.11
    import sre_constants as _c          # type: ignore[no-redef]
    import sre_parse as _parser         # type: ignore[no-redef]

PATTERN_MAX_CHARS = 200
MAX_CUSTOM_PATTERNS = 10
TOKEN_MAX_CHARS = 128
COST_MAX = 4096          # por padrão
TOTAL_COST_MAX = 4096    # somado, todos os padrões do perfil (pior caso medido no core: ~0,4 s numa resposta de 40 000)

#: O texto que acompanha a recusa (`details` do 400 `unsafe_pattern` no core; o GAIBO
#: pode mostrá-lo antes do save). Veio do core (`config/profile_pattern_guard.py`) na
#: v0.1.178 para o texto ser o mesmo nos dois lados; os números vêm das constantes acima.
PATTERN_HINT = ("Os padrões de códigos de produto aplicam-se palavra a palavra (sem espaços) e têm de ter "
                f"custo limitado: até {PATTERN_MAX_CHARS} caracteres e {MAX_CUSTOM_PATTERNS} padrões, sem "
                "quantificador dentro de quantificador (`(a+)+`), sem alternativas dentro de um quantificador "
                "(`(a|b)+`), sem `\\1`, e com limites nos quantificadores (`\\d{4,12}` em vez de `\\d+` quando "
                "há vários seguidos).")

REASONS = ("empty", "not_a_string", "too_long", "invalid_regex", "nested_quantifier",
           "alternation_in_quantifier", "backreference", "whitespace", "too_costly")
LIST_REASONS = ("not_a_list", "too_many", "too_costly_total")

_REPEATS = (_c.MAX_REPEAT, _c.MIN_REPEAT) + ((_c.POSSESSIVE_REPEAT,) if hasattr(_c, "POSSESSIVE_REPEAT") else ())
_GROUPREFS = tuple(getattr(_c, n) for n in ("GROUPREF", "GROUPREF_EXISTS", "GROUPREF_IGNORE",
                                              "GROUPREF_LOC_IGNORE", "GROUPREF_UNI_IGNORE") if hasattr(_c, n))
_LITERALS = tuple(getattr(_c, n) for n in ("LITERAL", "LITERAL_IGNORE", "LITERAL_LOC_IGNORE",
                                             "LITERAL_UNI_IGNORE") if hasattr(_c, n))


class _Unsafe(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _class_has_space(items) -> bool:
    """Uma classe `[...]` (sem `^`) que casa espaço: `\\s`, um espaço literal ou uma gama que o cobre."""
    if any(op == _c.NEGATE for op, _ in items):
        return False
    for op, av in items:
        if op in _LITERALS and chr(av).isspace():
            return True
        if op == _c.RANGE and av[0] <= 0x20 <= av[1]:
            return True
        if op == _c.CATEGORY and av in (_c.CATEGORY_SPACE, getattr(_c, "CATEGORY_UNI_SPACE", None),
                                         getattr(_c, "CATEGORY_LOC_SPACE", None)):
            return True
    return False


def _cost(items, in_repeat: bool) -> int:
    """Custo de uma tentativa de casar. Dentro de um quantificador que repete (`hi > 1`) só
    pode haver passos sem escolha: um quantificador variável lá dentro (`+`, `*`, `?`, `{m,n}`,
    também `(?:\\d?\\d?){12}` — o `?` encaixado é exponencial) ou uma alternativa recusam-se;
    um `{n}` exato não escolhe nada e conta 1."""
    total = 1
    for op, av in items:
        if op in _REPEATS:
            lo, hi, sub = av
            if in_repeat and lo != hi:
                raise _Unsafe("nested_quantifier")
            repeats = hi > 1
            width = 1 if in_repeat else ((TOKEN_MAX_CHARS - lo + 1) if hi == _c.MAXREPEAT else (hi - lo + 1))
            total *= max(1, width) * _cost(sub, in_repeat or repeats)
        elif op == _c.SUBPATTERN:
            total *= _cost(av[-1], in_repeat)
        elif op == _c.BRANCH:
            if in_repeat:
                raise _Unsafe("alternation_in_quantifier")
            total *= sum(_cost(b, in_repeat) for b in av[1])
        elif op in (_c.ASSERT, _c.ASSERT_NOT):
            total *= _cost(av[1], in_repeat)
        elif hasattr(_c, "ATOMIC_GROUP") and op == _c.ATOMIC_GROUP:
            total *= _cost(av, in_repeat)
        elif op in _GROUPREFS:
            raise _Unsafe("backreference")
        elif op in _LITERALS and chr(av).isspace():
            raise _Unsafe("whitespace")
        elif op == _c.IN and _class_has_space(av):
            raise _Unsafe("whitespace")
        if total > COST_MAX:
            raise _Unsafe("too_costly")
    return total


@lru_cache(maxsize=256)
def _analyse(pattern: str):
    """(motivo, custo): motivo `None` = aceite. Só recebe texto já limitado a PATTERN_MAX_CHARS."""
    if not pattern.strip():
        return "empty", 0
    try:
        re.compile(pattern)
        parsed = _parser.parse(pattern)
    except (re.error, RecursionError, OverflowError):
        return "invalid_regex", 0
    try:
        return None, _cost(list(parsed), False)
    except _Unsafe as u:
        return u.reason, 0
    except RecursionError:
        return "too_costly", 0


def _checked(pattern: Any):
    if not isinstance(pattern, str):
        return "not_a_string", 0
    if len(pattern) > PATTERN_MAX_CHARS:      # antes da cache: nunca guarda um texto grande
        return "too_long", 0
    return _analyse(pattern)


def pattern_refusal(pattern: Any) -> Optional[str]:
    """O motivo por que este padrão não pode correr, ou `None` se o custo é limitado."""
    return _checked(pattern)[0]


def pattern_cost(pattern: Any) -> Optional[int]:
    """O custo estimado de um padrão aceite (`None` se recusado) — para o orçamento somado."""
    reason, cost = _checked(pattern)
    return None if reason else cost


def find_unsafe_patterns(doc: Any) -> List[str]:
    """`product_identification.patterns.<i>: <motivo>` — o valor nunca (vem do cliente).

    `doc` é o perfil inteiro (dict). Lista vazia = o save pode seguir."""
    pid = doc.get("product_identification") if isinstance(doc, dict) else None
    patterns = pid.get("patterns") if isinstance(pid, dict) else None
    if patterns is None:
        return []
    if not isinstance(patterns, list):
        return ["product_identification.patterns: not_a_list"]
    out: List[str] = []
    if len(patterns) > MAX_CUSTOM_PATTERNS:
        out.append(f"product_identification.patterns: too_many ({len(patterns)} > {MAX_CUSTOM_PATTERNS})")
    total = 0
    for i, p in enumerate(patterns[:MAX_CUSTOM_PATTERNS * 5]):
        reason, cost = _checked(p)
        if reason:
            out.append(f"product_identification.patterns.{i}: {reason}")
        total += cost
    if total > TOTAL_COST_MAX:
        out.append(f"product_identification.patterns: too_costly_total ({total} > {TOTAL_COST_MAX})")
    return out


__all__ = ["COST_MAX", "LIST_REASONS", "MAX_CUSTOM_PATTERNS", "PATTERN_HINT", "PATTERN_MAX_CHARS", "REASONS",
           "TOKEN_MAX_CHARS", "TOTAL_COST_MAX", "find_unsafe_patterns", "pattern_cost", "pattern_refusal"]
