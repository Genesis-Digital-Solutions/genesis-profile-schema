"""
genesis_profile_schema/rules_grammar.py — a gramática das condições que um
perfil pode declarar (v0.1.79, 2 Out 2026; núcleo partilhado do Intake e da
Verificação Documental).

Porquê aqui e não no genai-core: a MESMA gramática valida o perfil quando se
grava (Studio, gaibo, core) e é a que o motor de regras do core avalia. Duas
cópias divergiam — é a lição do `ISO_TO_CANONICAL` (camada 7 do CAPACIDADES).

Regras de segurança, todas fechadas em código:
  * Uma condição é JSON ESTRUTURADO. Nunca texto avaliado: não existe `eval`,
    nem expressões em string, nem acesso a atributos. Um operador fora da
    allowlist é erro.
  * Tectos de profundidade, de nós, de listas e de texto por condição; quem
    valida uma definição inteira soma os nós (`PredicateRefs.nodes`) para um
    orçamento POR DEFINIÇÃO — senão 300 condições no tecto multiplicavam o
    custo de cada avaliação (revisão independente de 2 Out).
  * Números finitos; booleanos não são números.
  * As referências e os literais são DEVOLVIDOS para quem chama confirmar,
    contra as perguntas reais, que existem, que o tipo serve e que o literal é
    uma opção válida — uma condição sobre algo que não existe, ou sobre uma
    opção mal escrita, dava sempre falso em silêncio.

Forma (P = condição, V = valor):

    P := {"all": [P, ...]} | {"any": [P, ...]} | {"not": P}
       | {"count": [P, ...], <cmp>: int}            # quantas são verdadeiras
       | {"q": <chave>, <op>: <literal>}            # sobre uma resposta
       | {"q": <chave>, "answered": bool}
       | {"cmp": {"left": V, "op": <cmp>, "right": V}}
       | {"incomplete": true} | {"red_flag": true} | {"red_flag": <chave>}
    V := {"q": <chave>} | {"score": <chave>} | {"const": número}
       | {"map": {"q": <chave>, "values": {<texto>: número}}}
       | {"money": <chave>}                         # convertido à moeda base
       | {"ref_year_offset": int}                   # ano de referência + n
    <cmp> := eq | ne | gt | gte | lt | lte
    <op>  := eq | ne | gt | gte | lt | lte | in | nin | contains
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set, Tuple

__all__ = [
    "KEY_PATTERN",
    "MAX_DEPTH",
    "MAX_NODES",
    "PredicateRefs",
    "validate_predicate",
    "validate_value",
    "is_valid_key",
]

# Chaves de perguntas, pontuações, red flags: letras, algarismos e `._-`.
# Começa por letra ou algarismo («3.6», «k_score»). 64 = folga larga para
# «3.5.value» e nomes legíveis, sem servir de canal para texto.
KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_KEY_RE = re.compile(KEY_PATTERN)

MAX_DEPTH = 10          # aninhamento de all/any/not/count
MAX_NODES = 300         # nós por condição (incluindo valores)
MAX_LIST = 100          # itens de all/any/count/in/nin
MAX_TEXT = 200          # literais de texto
MAX_MAP = 100           # entradas de um `map`
MAX_ABS_NUMBER = 1e15   # literais numéricos (montantes incluídos)
MAX_YEAR_OFFSET = 200

CMP_OPS = ("eq", "ne", "gt", "gte", "lt", "lte")
ANSWER_OPS = CMP_OPS + ("in", "nin", "contains")
NUMERIC_OPS = ("gt", "gte", "lt", "lte")


@dataclass
class PredicateRefs:
    """O que uma condição refere — para quem a valida confirmar contra a
    definição real."""
    questions: Set[str] = field(default_factory=set)
    # `{"money": q}` — q tem de ser um montante.
    money_questions: Set[str] = field(default_factory=set)
    # `{"q": q}` como VALOR numérico de uma comparação — q tem de ser número/ano.
    numeric_questions: Set[str] = field(default_factory=set)
    # `{"q": q, <op>: literal}` — (pergunta, operador, literal) para confirmar
    # o tipo e as opções.
    literals: List[Tuple[str, str, Any]] = field(default_factory=list)
    # `{"map": {"q": q, "values": {...}}}` — (pergunta, chaves do mapa).
    map_keys: List[Tuple[str, Tuple[str, ...]]] = field(default_factory=list)
    scores: Set[str] = field(default_factory=set)
    red_flags: Set[str] = field(default_factory=set)
    uses_incomplete: bool = False
    uses_any_red_flag: bool = False
    uses_reference_year: bool = False
    nodes: int = 0

    def merge(self, other: "PredicateRefs") -> None:
        self.questions |= other.questions
        self.money_questions |= other.money_questions
        self.numeric_questions |= other.numeric_questions
        self.literals.extend(other.literals)
        self.map_keys.extend(other.map_keys)
        self.scores |= other.scores
        self.red_flags |= other.red_flags
        self.uses_incomplete |= other.uses_incomplete
        self.uses_any_red_flag |= other.uses_any_red_flag
        self.uses_reference_year |= other.uses_reference_year


class _Budget:
    def __init__(self) -> None:
        self.nodes = 0

    def tick(self) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ValueError(f"condição grande demais (mais de {MAX_NODES} nós)")


def is_valid_key(value: Any) -> bool:
    return isinstance(value, str) and bool(_KEY_RE.match(value))


def _key(value: Any, what: str) -> str:
    if not is_valid_key(value):
        raise ValueError(f"{what}: chave inválida {value!r} (letras, algarismos e ._-, até 64)")
    return value


def _number(value: Any, what: str) -> float:
    # bool é int em Python: `true` não é um número aqui.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what}: tem de ser um número")
    try:
        f = float(value)
    except OverflowError:
        raise ValueError(f"{what}: número fora dos limites") from None
    if not math.isfinite(f) or abs(f) > MAX_ABS_NUMBER:
        raise ValueError(f"{what}: número fora dos limites")
    return f


def _int(value: Any, what: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{what}: tem de ser um inteiro")
    if not lo <= value <= hi:
        raise ValueError(f"{what}: fora do intervalo {lo}–{hi}")
    return value


def _literal(value: Any, what: str) -> None:
    """Literal de comparação com uma resposta: texto curto, número ou booleano.
    `null` não — para «sem resposta» usa-se `answered: false`."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        _number(value, what)
        return
    if isinstance(value, str):
        if len(value) > MAX_TEXT:
            raise ValueError(f"{what}: texto com mais de {MAX_TEXT} caracteres")
        return
    raise ValueError(f"{what}: literal tem de ser texto, número ou booleano (para «sem resposta» use answered)")


def _only_keys(node: Dict[str, Any], allowed: Iterable[str], what: str) -> None:
    extra = set(node) - set(allowed)
    if extra:
        raise ValueError(f"{what}: chaves não permitidas {sorted(extra)}")


def validate_value(node: Any, *, allow_scores: bool = True, _budget: _Budget | None = None) -> PredicateRefs:
    """Valida um VALOR (lado de uma comparação) e devolve o que ele refere."""
    budget = _budget or _Budget()
    budget.tick()
    refs = PredicateRefs()
    if not isinstance(node, dict) or len(node) != 1:
        raise ValueError("valor: tem de ser um objeto com uma única chave")
    (kind, arg), = node.items()
    if kind == "q":
        key = _key(arg, "valor q")
        refs.questions.add(key)
        refs.numeric_questions.add(key)
    elif kind == "score":
        if not allow_scores:
            raise ValueError("valor: uma pontuação não pode referir outra pontuação")
        refs.scores.add(_key(arg, "valor score"))
    elif kind == "const":
        _number(arg, "valor const")
    elif kind == "money":
        key = _key(arg, "valor money")
        refs.questions.add(key)
        refs.money_questions.add(key)
    elif kind == "ref_year_offset":
        _int(arg, "valor ref_year_offset", -MAX_YEAR_OFFSET, MAX_YEAR_OFFSET)
        refs.uses_reference_year = True
    elif kind == "map":
        if not isinstance(arg, dict):
            raise ValueError("valor map: tem de ser um objeto {q, values}")
        _only_keys(arg, ("q", "values"), "valor map")
        key = _key(arg.get("q"), "valor map.q")
        refs.questions.add(key)
        values = arg.get("values")
        if not isinstance(values, dict) or not values or len(values) > MAX_MAP:
            raise ValueError(f"valor map.values: entre 1 e {MAX_MAP} entradas")
        for k, v in values.items():
            if not isinstance(k, str) or len(k) > MAX_TEXT:
                raise ValueError("valor map.values: chaves têm de ser texto curto")
            _number(v, f"valor map.values[{k!r}]")
        refs.map_keys.append((key, tuple(values)))
    else:
        raise ValueError(f"valor: tipo desconhecido {kind!r}")
    return refs


def _count_target(op: str, target: int, items: int) -> None:
    """Um alvo que torna a condição SEMPRE falsa ou SEMPRE verdadeira é um erro
    de escrita — recusa-se ao gravar (n = número de condições; a contagem vai
    de 0 a n)."""
    never = (
        (op == "eq" and target > items)
        or (op == "gt" and target >= items)
        or (op == "gte" and target > items)
        or (op == "lt" and target == 0)
    )
    always = (
        (op == "ne" and target > items)
        or (op == "gte" and target == 0)
        or (op == "lt" and target > items)
        or (op == "lte" and target >= items)
    )
    if never:
        raise ValueError(f"count.{op}: {target} com {items} condições nunca se cumpre")
    if always:
        raise ValueError(f"count.{op}: {target} com {items} condições cumpre-se sempre")


def validate_predicate(
    node: Any,
    *,
    allow_scores: bool = True,
    allow_outcome_refs: bool = True,
    _depth: int = 0,
    _budget: _Budget | None = None,
) -> PredicateRefs:
    """Valida uma condição e devolve o que ela refere (com `nodes` = tamanho).

    `allow_scores=False` dentro das próprias pontuações (uma pontuação não
    depende de outra — sem ciclos). `allow_outcome_refs=False` onde ainda não
    há completude nem red flags calculadas (pontuações, completude, a própria
    definição de uma red flag).
    """
    top = _budget is None
    budget = _budget or _Budget()
    refs = _validate(node, allow_scores, allow_outcome_refs, _depth, budget)
    if top:
        refs.nodes = budget.nodes
    return refs


def _validate(node: Any, allow_scores: bool, allow_outcome_refs: bool, depth: int, budget: _Budget) -> PredicateRefs:
    budget.tick()
    if depth > MAX_DEPTH:
        raise ValueError(f"condição aninhada demais (mais de {MAX_DEPTH} níveis)")
    if not isinstance(node, dict) or not node:
        raise ValueError("condição: tem de ser um objeto não vazio")

    refs = PredicateRefs()

    def sub(item: Any) -> None:
        refs.merge(_validate(item, allow_scores, allow_outcome_refs, depth + 1, budget))

    if "all" in node or "any" in node:
        op = "all" if "all" in node else "any"
        _only_keys(node, (op,), op)
        items = node[op]
        if not isinstance(items, list) or not items or len(items) > MAX_LIST:
            raise ValueError(f"{op}: lista entre 1 e {MAX_LIST} condições")
        for item in items:
            sub(item)
        return refs

    if "not" in node:
        _only_keys(node, ("not",), "not")
        sub(node["not"])
        return refs

    if "count" in node:
        _only_keys(node, ("count",) + CMP_OPS, "count")
        cmp = [k for k in node if k in CMP_OPS]
        if len(cmp) != 1:
            raise ValueError("count: exatamente um comparador (eq, ne, gt, gte, lt, lte)")
        items = node["count"]
        if not isinstance(items, list) or not items or len(items) > MAX_LIST:
            raise ValueError(f"count: lista entre 1 e {MAX_LIST} condições")
        target = _int(node[cmp[0]], f"count.{cmp[0]}", 0, MAX_LIST)
        _count_target(cmp[0], target, len(items))
        for item in items:
            sub(item)
        return refs

    if "cmp" in node:
        _only_keys(node, ("cmp",), "cmp")
        spec = node["cmp"]
        if not isinstance(spec, dict):
            raise ValueError("cmp: tem de ser {left, op, right}")
        _only_keys(spec, ("left", "op", "right"), "cmp")
        if spec.get("op") not in CMP_OPS:
            raise ValueError(f"cmp.op: tem de ser um de {CMP_OPS}")
        for side in ("left", "right"):
            if side not in spec:
                raise ValueError(f"cmp: falta {side}")
            refs.merge(validate_value(spec[side], allow_scores=allow_scores, _budget=budget))
        return refs

    if "incomplete" in node:
        _only_keys(node, ("incomplete",), "incomplete")
        if not allow_outcome_refs:
            raise ValueError("incomplete: não é permitido aqui")
        if node["incomplete"] is not True:
            raise ValueError("incomplete: só aceita true")
        refs.uses_incomplete = True
        return refs

    if "red_flag" in node:
        _only_keys(node, ("red_flag",), "red_flag")
        if not allow_outcome_refs:
            raise ValueError("red_flag: não é permitido aqui")
        arg = node["red_flag"]
        if arg is True:
            refs.uses_any_red_flag = True
        else:
            refs.red_flags.add(_key(arg, "red_flag"))
        return refs

    if "q" in node:
        ops = [k for k in node if k != "q"]
        if len(ops) != 1:
            raise ValueError("q: exatamente um operador")
        op = ops[0]
        key = _key(node["q"], "q")
        refs.questions.add(key)
        arg = node[op]
        if op == "answered":
            if not isinstance(arg, bool):
                raise ValueError("answered: true ou false")
        elif op in ("in", "nin"):
            if not isinstance(arg, list) or not arg or len(arg) > MAX_LIST:
                raise ValueError(f"{op}: lista entre 1 e {MAX_LIST} literais")
            for i, item in enumerate(arg):
                _literal(item, f"{op}[{i}]")
                refs.literals.append((key, op, item))
        elif op in ANSWER_OPS:
            _literal(arg, op)
            if op in NUMERIC_OPS:
                _number(arg, op)
            refs.literals.append((key, op, arg))
        else:
            raise ValueError(f"q: operador desconhecido {op!r}")
        return refs

    raise ValueError(f"condição: forma desconhecida {sorted(node)}")
