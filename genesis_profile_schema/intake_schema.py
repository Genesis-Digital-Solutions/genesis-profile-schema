"""
genesis_profile_schema/intake_schema.py — `intake.definitions`: questionários
regulados com metodologia determinística (v0.1.79, 2 Out 2026; épico Intake,
bloco B1, revisto pela revisão independente do mesmo dia).

O que isto é: a DEFINIÇÃO de um percurso em que alguém de fora responde a um
questionário aprovado e um motor de regras do genai-core calcula uma proposta
de resultado que uma pessoa valida. Serve qualquer cliente e qualquer processo
desta família (adequação de investidores, elegibilidade, onboarding,
conflito de interesses…) — nada aqui conhece um cliente concreto.

Invariantes que este contrato fixa (decisões do épico, não opções):
  * A lógica é DADO declarativo: tipos de regra fechados + condições JSON da
    `rules_grammar` (sem `eval`, sem expressões em texto).
  * Toda a referência é confirmada ao gravar — perguntas, opções, tipos,
    pontuações, red flags, resultados, secções — e também os LITERAIS: uma
    condição `{"q": "grau", "eq": "Superior"}` contra a opção `superior` dava
    sempre falso em silêncio.
  * Uma pontuação não depende de outra; a completude e as red flags não
    dependem do resultado; as condições de visibilidade não têm ciclos.
  * Orçamento de tamanho POR DEFINIÇÃO (nós de todas as condições) — os
    tectos por condição sozinhos deixavam multiplicar o custo de cada
    avaliação por 300.
  * Os escalamentos não se encadeiam: um resultado posto por um escalamento
    não é trocado por outro (a ordem deixava de ser só apresentação).
  * `use_case` é uma allowlist: solvabilidade de pessoas e seleção de
    trabalhadores (AI Act, Anexo III) NÃO entram até haver o pacote de
    conformidade de alto risco.
  * Os casos de referência viajam COM a metodologia que provam, e as respostas
    deles passam pelo MESMO validador das respostas reais (`field_values`).

O que NÃO está aqui de propósito: quem pode ver o quê (fica `internal` até
existir consumidor — regra «campo sem consumidor fica escondido») e a
aprovação formal de uma versão (é do Studio, com o portão dos casos — B3).
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, Iterable, List, Literal, Optional, Set, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .field_definition import FieldDefinition, I18nHelp, I18nText, StrictNumber
from .field_values import iso_value, number_fits, validate_answers
from .rules_grammar import KEY_PATTERN, PredicateRefs, validate_predicate

__all__ = [
    "INTAKE_USE_CASES",
    "MAX_DEFINITION_NODES",
    "IntakeSection",
    "IntakeQuestion",
    "IntakeGlossaryTerm",
    "IntakeOutcome",
    "IntakeScore",
    "IntakeRequired",
    "IntakeRedFlag",
    "IntakeDecisionRule",
    "IntakeEscalation",
    "IntakeReferenceCase",
    "IntakeMethodology",
    "IntakeDefinition",
    "ProfileIntake",
]

_CLOSED = ConfigDict(extra="forbid")

# Allowlist (épico Intake §7). `credit_scoring` e `hiring` ficam DE FORA:
# solvabilidade de pessoas e seleção de trabalhadores são alto risco.
INTAKE_USE_CASES = (
    "appropriateness",       # conhecimento e experiência do investidor
    "suitability",           # adequação com objetivos/situação financeira
    "onboarding",            # adesão / KYC documental, sem decisão de risco
    "eligibility",           # elegibilidade para um apoio ou programa
    "consent",               # consentimento informado
    "conflict_of_interest",  # declarações de conflito de interesses
    "supplier_due_diligence",
)

MAX_DEFINITIONS = 20
MAX_SECTIONS = 30
MAX_QUESTIONS = 300
MAX_GLOSSARY = 300
MAX_SCORES = 20
MAX_TERMS = 50
MAX_ITEMS = 100
MAX_RULES = 100
MAX_CASES = 500
MAX_CASE_ANSWERS = 400
# Soma dos nós de TODAS as condições de uma definição. Uma definição real
# grande (61 perguntas, 3 pontuações, 7 escalamentos) usa ~500.
MAX_DEFINITION_NODES = 8000

Key = Annotated[str, Field(pattern=KEY_PATTERN)]
_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
_CURRENCY_RE = r"^[A-Z]{3}$"
_VERSION_RE = r"^[0-9A-Za-z][0-9A-Za-z._-]{0,31}$"


def _cond(*, scores: bool, outcomes: bool):
    def check(value: Dict[str, Any]) -> Dict[str, Any]:
        validate_predicate(value, allow_scores=scores, allow_outcome_refs=outcomes)
        return value
    return check


# Onde ainda não há pontuações nem resultado (visibilidade, termos, completude).
BaseCondition = Annotated[Dict[str, Any], AfterValidator(_cond(scores=False, outcomes=False))]
# Onde já há pontuações mas ainda não há completude/red flags (red flags).
ScoredCondition = Annotated[Dict[str, Any], AfterValidator(_cond(scores=True, outcomes=False))]
# Onde já há tudo (decisão, escalamentos).
FullCondition = Annotated[Dict[str, Any], AfterValidator(_cond(scores=True, outcomes=True))]


# Piso das taxas de câmbio (unidades de moeda por 1 da base): abaixo disto a
# conversão rebentava a precisão do Decimal no motor (revisão de 2 Out).
MIN_FX_RATE = 1e-6


def _positive(v: float) -> float:
    if v < MIN_FX_RATE:
        raise ValueError(f"tem de ser pelo menos {MIN_FX_RATE:g}")
    return v


Points = StrictNumber
FxRate = Annotated[StrictNumber, AfterValidator(_positive)]


# ─────────────────────────────────────────────────────────────────────────────
# Questionário
# ─────────────────────────────────────────────────────────────────────────────

class IntakeSection(BaseModel):
    """Secção do questionário. `assist=False` desliga o glossário em TODAS as
    perguntas dela — é o que protege uma secção que é o próprio teste (um
    esclarecimento no sítio errado invalidava-o)."""
    model_config = _CLOSED

    key: Key
    title: I18nText
    intro: I18nHelp = Field(default_factory=dict)
    assist: bool = True


class IntakeQuestion(FieldDefinition):
    """Uma pergunta = um campo + o que o percurso precisa.

    - `show_if`: só aparece (e só conta para a completude e para as regras)
      quando a condição é verdadeira — as condições do próprio questionário.
    - `assist`: glossário disponível nesta pergunta (e só se a secção deixar).
    - `prefill_from`: de onde se pode PROPOR a resposta; quem responde
      confirma sempre. Vazio = nunca pré-preenchida (declarações, perguntas
      de conhecimento).
    """
    section: Key
    show_if: Optional[BaseCondition] = None
    assist: bool = True
    prefill_from: List[Literal["id_document", "cv", "invitation", "proof_of_address"]] = Field(
        default_factory=list, max_length=4)


class IntakeGlossaryTerm(BaseModel):
    """Termo do glossário fechado e aprovado. `sections` é uma ALLOWLIST: um
    termo sem secções não é servido em lado nenhum."""
    model_config = _CLOSED

    key: Key
    term: I18nText
    text: I18nText
    sections: List[Key] = Field(default_factory=list, max_length=MAX_SECTIONS)


# ─────────────────────────────────────────────────────────────────────────────
# Metodologia — catálogo de tipos de regra
# ─────────────────────────────────────────────────────────────────────────────

class IntakeOutcome(BaseModel):
    """Um resultado possível. `kind` diz ao produto o que fazer com ele
    (advertências, revisão), sem conhecer o nome que o cliente lhe dá."""
    model_config = _CLOSED

    key: Key
    label: I18nText
    kind: Literal["positive", "negative", "insufficient", "review"]


class MatchItem(BaseModel):
    """`eq` é confirmado contra o TIPO da pergunta (texto numa escolha,
    booleano numa caixa, número num número) — ver `_check_literal`."""
    model_config = _CLOSED
    q: Key
    eq: Union[bool, str, StrictNumber]


class TermCountMatches(BaseModel):
    """`points_each` por cada resposta igual à esperada (ex.: perguntas de
    conhecimento com resposta certa)."""
    model_config = _CLOSED
    kind: Literal["count_matches"]
    items: List[MatchItem] = Field(min_length=1, max_length=MAX_ITEMS)
    points_each: Points = 1.0


class PointsItem(BaseModel):
    """Pontos por valor de resposta (escolha, escolha múltipla ou caixa — numa
    caixa as chaves são `true`/`false`). Numa escolha múltipla, `agg` decide se
    soma ou conta só o maior (ex.: várias áreas de formação)."""
    model_config = _CLOSED
    q: Key
    values: Dict[str, Points] = Field(min_length=1, max_length=MAX_ITEMS)
    agg: Literal["sum", "max"] = "sum"
    when: Optional[BaseCondition] = None


class TermPoints(BaseModel):
    model_config = _CLOSED
    kind: Literal["points"]
    items: List[PointsItem] = Field(min_length=1, max_length=MAX_ITEMS)


class Bonus(BaseModel):
    model_config = _CLOSED
    when: BaseCondition
    points: Points


class Category(BaseModel):
    """Uma categoria conta só quando `when` é verdadeiro; vale `base` mais os
    bónus que se verificarem DENTRO dela."""
    model_config = _CLOSED
    key: Key
    when: BaseCondition
    base: Points = 0.0
    bonuses: List[Bonus] = Field(default_factory=list, max_length=20)


class TermCategoryMax(BaseModel):
    """A maior pontuação entre categorias (0 se nenhuma conta)."""
    model_config = _CLOSED
    kind: Literal["category_max"]
    categories: List[Category] = Field(min_length=1, max_length=MAX_ITEMS)


class TermBonus(BaseModel):
    model_config = _CLOSED
    kind: Literal["bonus"]
    when: BaseCondition
    points: Points


Term = Annotated[
    Union[TermCountMatches, TermPoints, TermCategoryMax, TermBonus],
    Field(discriminator="kind"),
]


class ScoreBand(BaseModel):
    """Faixa informativa (ex.: «conhecimento suficiente» a partir de 6). Não
    decide nada — quem decide é a sequência de decisão."""
    model_config = _CLOSED
    min: Points
    label: I18nText


class IntakeScore(BaseModel):
    """Pontuação = soma dos termos. Cada ponto fica ligado às respostas que o
    geraram (o motor devolve o detalhe)."""
    model_config = _CLOSED
    key: Key
    label: I18nText
    terms: List[Term] = Field(min_length=1, max_length=MAX_TERMS)
    bands: List[ScoreBand] = Field(default_factory=list, max_length=20)


class IntakeRequired(BaseModel):
    """Resposta essencial para a avaliação poder concluir. Com `when`, só é
    exigida quando a condição é verdadeira. «Não sei» é uma resposta; o
    sentinela «não sei precisar» também."""
    model_config = _CLOSED
    q: Key
    when: Optional[BaseCondition] = None


class IntakeRedFlag(BaseModel):
    model_config = _CLOSED
    key: Key
    label: I18nText
    when: ScoredCondition


class IntakeDecisionRule(BaseModel):
    """Regra da sequência de decisão — avaliadas por ordem, ganha a primeira."""
    model_config = _CLOSED
    key: Key
    when: FullCondition
    outcome: Key


class IntakeEscalation(BaseModel):
    """Depois da decisão: se `when` é verdadeiro, o processo vai SEMPRE a
    revisão humana obrigatória; e se o resultado estiver em
    `replace_outcomes`, passa a `set_outcome` (ex.: respostas contraditórias
    num resultado favorável → revisão manual). Não se encadeiam: um
    `set_outcome` nunca está nos `replace_outcomes` de outro escalamento."""
    model_config = _CLOSED
    key: Key
    label: I18nText
    when: FullCondition
    replace_outcomes: List[Key] = Field(default_factory=list, max_length=20)
    set_outcome: Optional[Key] = None

    @model_validator(mode="after")
    def _par(self) -> "IntakeEscalation":
        if bool(self.replace_outcomes) != bool(self.set_outcome):
            raise ValueError(f"escalamento {self.key!r}: replace_outcomes e set_outcome andam juntos")
        if self.set_outcome and self.set_outcome in self.replace_outcomes:
            raise ValueError(f"escalamento {self.key!r}: troca um resultado por ele próprio")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Casos de referência — o teste de aceitação da metodologia
# ─────────────────────────────────────────────────────────────────────────────

class CaseExpectation(BaseModel):
    """O que a entidade aprovou como resultado esperado. `mandatory_review`,
    `scores` e `red_flags` são opcionais: quando presentes, são comparados."""
    model_config = _CLOSED
    outcome: Key
    mandatory_review: Optional[bool] = None
    scores: Dict[Key, Points] = Field(default_factory=dict, max_length=MAX_SCORES)
    red_flags: Optional[List[Key]] = Field(default=None, max_length=50)


class IntakeReferenceCase(BaseModel):
    """Um caso aprovado. As respostas são validadas contra as perguntas pelo
    mesmo validador das respostas reais (na definição, onde se conhecem)."""
    model_config = _CLOSED

    key: Key
    label: str = Field(default="", max_length=300)
    answers: Dict[Key, Any] = Field(max_length=MAX_CASE_ANSWERS)
    # Data de referência fixa do caso (a avaliação real fotografa a sua).
    reference_date: Optional[str] = Field(default=None, pattern=_DATE_RE)
    # Unidades de cada moeda por 1 unidade da moeda base (o caso traz as suas
    # taxas: um teste nunca depende do câmbio do dia).
    fx_rates: Dict[Annotated[str, Field(pattern=_CURRENCY_RE)], FxRate] = Field(
        default_factory=dict, max_length=60)
    expected: CaseExpectation
    note: str = Field(default="", max_length=2000)


# ─────────────────────────────────────────────────────────────────────────────
# Metodologia e definição
# ─────────────────────────────────────────────────────────────────────────────

class MethodologyApproval(BaseModel):
    """Registo informativo de quem aprovou a versão (a aprovação que BLOQUEIA
    a publicação é do Studio, com o portão dos casos)."""
    model_config = _CLOSED
    by: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=200)
    at: str = Field(pattern=_DATE_RE)


class IntakeMethodology(BaseModel):
    model_config = _CLOSED

    version: str = Field(pattern=_VERSION_RE)
    effective_from: Optional[str] = Field(default=None, pattern=_DATE_RE)
    approval: Optional[MethodologyApproval] = None
    base_currency: str = Field(default="EUR", pattern=_CURRENCY_RE)
    # Data de referência da avaliação (para «ano mais recente», etc.):
    # a data de SUBMISSÃO, fixada no processo — nunca a data do dia.
    reference_date: Literal["submission"] = "submission"
    outcomes: List[IntakeOutcome] = Field(min_length=1, max_length=20)
    scores: List[IntakeScore] = Field(default_factory=list, max_length=MAX_SCORES)
    required: List[IntakeRequired] = Field(default_factory=list, max_length=MAX_QUESTIONS)
    red_flags: List[IntakeRedFlag] = Field(default_factory=list, max_length=MAX_RULES)
    decision: List[IntakeDecisionRule] = Field(min_length=1, max_length=MAX_RULES)
    default_outcome: Key
    escalations: List[IntakeEscalation] = Field(default_factory=list, max_length=MAX_RULES)
    reference_cases: List[IntakeReferenceCase] = Field(default_factory=list, max_length=MAX_CASES)


class IntakeDefinition(BaseModel):
    """Uma definição completa (um questionário + a sua metodologia). Uma por
    veículo/processo: a chave no mapa `intake.definitions` é o seu id."""
    model_config = _CLOSED

    title: I18nText
    use_case: Literal[INTAKE_USE_CASES]  # type: ignore[valid-type]
    languages: List[Annotated[str, Field(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")]] = Field(
        min_length=1, max_length=10)
    sections: List[IntakeSection] = Field(min_length=1, max_length=MAX_SECTIONS)
    questions: List[IntakeQuestion] = Field(min_length=1, max_length=MAX_QUESTIONS)
    glossary: List[IntakeGlossaryTerm] = Field(default_factory=list, max_length=MAX_GLOSSARY)
    methodology: Optional[IntakeMethodology] = None

    @model_validator(mode="after")
    def _referencias(self) -> "IntakeDefinition":
        _Checker(self).run()
        return self

    def visibility_order(self) -> List[str]:
        """Perguntas por ordem topológica das dependências de `show_if`
        (validada sem ciclos) — a ordem em que o motor decide a visibilidade."""
        return _topological_order(self.questions)


class ProfileIntake(BaseModel):
    """Bloco `intake` do perfil. Vazio por omissão = inerte (como as filas)."""
    model_config = _CLOSED

    definitions: Dict[Key, IntakeDefinition] = Field(default_factory=dict, max_length=MAX_DEFINITIONS)


# ─────────────────────────────────────────────────────────────────────────────
# Validação cruzada
# ─────────────────────────────────────────────────────────────────────────────

_CHOICE = ("select", "multiselect")
_NUMERIC = ("number", "year")


def _unique(keys: Iterable[str], what: str) -> Set[str]:
    seen: Set[str] = set()
    dup: Set[str] = set()
    for k in keys:
        if k in seen:
            dup.add(k)
        seen.add(k)
    if dup:
        raise ValueError(f"{what} repetidos: {', '.join(sorted(dup))}")
    return seen


def _show_if_deps(q: IntakeQuestion) -> Set[str]:
    return validate_predicate(q.show_if, allow_scores=False, allow_outcome_refs=False).questions if q.show_if else set()


def _topological_order(questions: List[IntakeQuestion]) -> List[str]:
    """Kahn: as dependências antes de quem depende delas; desempate pela ordem
    da definição. Ciclo → erro (nenhuma pergunta de um ciclo poderia aparecer,
    e a completude delas era ignorada em silêncio)."""
    keys = [q.key for q in questions]
    deps = {q.key: _show_if_deps(q) & set(keys) for q in questions}
    order: List[str] = []
    done: Set[str] = set()
    pending = list(keys)
    while pending:
        ready = [k for k in pending if deps[k] <= done]
        if not ready:
            raise ValueError(f"show_if em ciclo entre {sorted(pending)[:10]}")
        for k in ready:
            order.append(k)
            done.add(k)
        pending = [k for k in pending if k not in done]
    return order


class _Checker:
    def __init__(self, d: IntakeDefinition) -> None:
        self.d = d
        self.by_key: Dict[str, IntakeQuestion] = {q.key: q for q in d.questions}
        self.nodes = 0

    # ── utilitários ─────────────────────────────────────────────────────────
    def q(self, key: str, where: str) -> IntakeQuestion:
        q = self.by_key.get(key)
        if q is None:
            raise ValueError(f"{where}: pergunta inexistente {key!r}")
        return q

    def options(self, q: IntakeQuestion) -> Set[str]:
        return {o.value for o in q.options}

    def literal(self, key: str, op: str, lit: Any, where: str) -> None:
        """O literal tem de poder ser igual a uma resposta VÁLIDA da pergunta."""
        q = self.q(key, where)
        t = q.type
        bad = f"{where}: {key!r} ({t}) não aceita {op} {lit!r}"
        if t == "select":
            if op not in ("eq", "ne", "in", "nin") or not isinstance(lit, str) or lit not in self.options(q):
                raise ValueError(bad)
        elif t == "multiselect":
            if op != "contains" or not isinstance(lit, str) or lit not in self.options(q):
                raise ValueError(bad + " (escolha múltipla: use contains com uma opção)")
        elif t == "checkbox":
            if op not in ("eq", "ne") or not isinstance(lit, bool):
                raise ValueError(bad)
        elif t in _NUMERIC:
            if op == "contains" or isinstance(lit, bool) or not isinstance(lit, (int, float)):
                raise ValueError(bad)
            # Igualdades com um número que nenhuma resposta válida pode ter
            # (2.5 num inteiro, 50 num ano, -1 com mínimo 0) nunca batem.
            if op in ("eq", "ne", "in", "nin") and not number_fits(q, lit):
                raise ValueError(bad + " (fora do que a pergunta aceita)")
        elif t in ("date", "datetime"):
            if op not in ("eq", "ne", "in", "nin") or not isinstance(lit, str):
                raise ValueError(bad)
            try:
                if iso_value(lit, t) != lit:
                    raise ValueError
            except ValueError:
                raise ValueError(bad + " (data ISO canónica, AAAA-MM-DD)") from None
        elif t in ("text", "textarea"):
            if op not in ("eq", "ne", "in", "nin") or not isinstance(lit, str):
                raise ValueError(bad)
        else:   # money, table
            raise ValueError(bad + " (use money/cmp)")

    def refs(self, cond: Optional[Dict[str, Any]], where: str, *, scores: Set[str] = frozenset(),
             flags: Set[str] = frozenset(), **kw: bool) -> PredicateRefs:
        if not cond:
            return PredicateRefs()
        r = validate_predicate(cond, **kw)
        self.nodes += r.nodes
        if self.nodes > MAX_DEFINITION_NODES:
            raise ValueError(f"definição grande demais (mais de {MAX_DEFINITION_NODES} nós de condições)")
        for key in r.questions:
            self.q(key, where)
        for key in r.money_questions:
            if self.by_key[key].type != "money":
                raise ValueError(f"{where}: 'money' sobre {key!r}, que não é montante")
        for key in r.numeric_questions:
            if self.by_key[key].type not in _NUMERIC:
                raise ValueError(f"{where}: comparação numérica sobre {key!r}, que não é número nem ano")
        for key, keys in r.map_keys:
            q = self.by_key[key]
            if q.type != "select":
                raise ValueError(f"{where}: 'map' só sobre escolhas, {key!r} é {q.type}")
            bad = sorted(set(keys) - self.options(q))
            if bad:
                raise ValueError(f"{where}: {key!r} não tem as opções {bad}")
        for key, op, lit in r.literals:
            self.literal(key, op, lit, where)
        bad_s = sorted(r.scores - set(scores))
        if bad_s:
            raise ValueError(f"{where}: pontuações inexistentes {bad_s}")
        bad_f = sorted(r.red_flags - set(flags))
        if bad_f:
            raise ValueError(f"{where}: red flags inexistentes {bad_f}")
        return r

    # ── a verificação ───────────────────────────────────────────────────────
    def run(self) -> None:
        d = self.d
        sections = _unique([s.key for s in d.sections], "secções")
        _unique([q.key for q in d.questions], "perguntas")
        _unique([g.key for g in d.glossary], "termos do glossário")
        for q in d.questions:
            if q.section not in sections:
                raise ValueError(f"pergunta {q.key!r}: secção inexistente {q.section!r}")
            if q.show_if:
                r = self.refs(q.show_if, f"pergunta {q.key!r} (show_if)",
                              allow_scores=False, allow_outcome_refs=False)
                if q.key in r.questions:
                    raise ValueError(f"pergunta {q.key!r}: show_if refere a própria pergunta")
        _topological_order(d.questions)
        for g in d.glossary:
            bad = sorted(set(g.sections) - sections)
            if bad:
                raise ValueError(f"glossário {g.key!r}: secções inexistentes {bad}")
        if d.methodology is not None:
            self.methodology(d.methodology)

    def methodology(self, m: IntakeMethodology) -> None:
        outcomes = _unique([o.key for o in m.outcomes], "resultados")
        scores = _unique([s.key for s in m.scores], "pontuações")
        flags = _unique([f.key for f in m.red_flags], "red flags")
        _unique([r.key for r in m.decision], "regras de decisão")
        _unique([e.key for e in m.escalations], "escalamentos")
        _unique([c.key for c in m.reference_cases], "casos de referência")
        base = dict(allow_scores=False, allow_outcome_refs=False)

        for s in m.scores:
            where = f"pontuação {s.key!r}"
            for t in s.terms:
                if isinstance(t, TermCountMatches):
                    for it in t.items:
                        self.literal(it.q, "eq", it.eq, where)
                elif isinstance(t, TermPoints):
                    for it in t.items:
                        q = self.q(it.q, where)
                        if q.type in _CHOICE:
                            allowed = self.options(q)
                        elif q.type == "checkbox":
                            allowed = {"true", "false"}
                        else:
                            raise ValueError(f"{where}: 'points' só sobre escolhas ou caixas, {it.q!r} é {q.type}")
                        bad = sorted(set(it.values) - allowed)
                        if bad:
                            raise ValueError(f"{where}: {it.q!r} não tem as opções {bad}")
                        if it.agg == "max" and q.type != "multiselect":
                            raise ValueError(f"{where}: agg 'max' só em escolha múltipla ({it.q!r})")
                        self.refs(it.when, where, **base)
                elif isinstance(t, TermCategoryMax):
                    _unique([c.key for c in t.categories], f"{where}: categorias")
                    for c in t.categories:
                        self.refs(c.when, where, **base)
                        for b in c.bonuses:
                            self.refs(b.when, where, **base)
                elif isinstance(t, TermBonus):
                    self.refs(t.when, where, **base)

        for r in m.required:
            self.q(r.q, "completude")
            self.refs(r.when, "completude", **base)
        for f in m.red_flags:
            self.refs(f.when, f"red flag {f.key!r}", scores=scores,
                      allow_scores=True, allow_outcome_refs=False)
        for r in m.decision:
            self.refs(r.when, f"regra {r.key!r}", scores=scores, flags=flags)
            if r.outcome not in outcomes:
                raise ValueError(f"regra {r.key!r}: resultado inexistente {r.outcome!r}")
        if m.default_outcome not in outcomes:
            raise ValueError(f"default_outcome inexistente {m.default_outcome!r}")
        replaced: Set[str] = set()
        set_by: Set[str] = set()
        destino: Dict[str, str] = {}
        for e in m.escalations:
            self.refs(e.when, f"escalamento {e.key!r}", scores=scores, flags=flags)
            if set(e.replace_outcomes) - outcomes or (e.set_outcome and e.set_outcome not in outcomes):
                raise ValueError(f"escalamento {e.key!r}: resultados inexistentes")
            for r in e.replace_outcomes:
                # O mesmo resultado trocado por destinos diferentes faria o
                # desfecho depender da ORDEM dos escalamentos.
                if r in destino and destino[r] != e.set_outcome:
                    raise ValueError(f"escalamentos trocam {r!r} por destinos diferentes "
                                     f"({destino[r]!r} e {e.set_outcome!r})")
                destino[r] = e.set_outcome  # type: ignore[assignment]
            replaced |= set(e.replace_outcomes)
            if e.set_outcome:
                set_by.add(e.set_outcome)
        chained = sorted(replaced & set_by)
        if chained:
            raise ValueError(f"escalamentos encadeados: {chained} é posto por um e trocado por outro")

        for c in m.reference_cases:
            where = f"caso {c.key!r}"
            check = validate_answers(self.d.questions, c.answers)
            if check.unknown_keys:
                raise ValueError(f"{where}: {check.unknown_keys} resposta(s) a perguntas inexistentes")
            if check.errors:
                k, msg = next(iter(sorted(check.errors.items())))
                raise ValueError(f"{where}: resposta inválida — {msg}")
            if c.expected.outcome not in outcomes:
                raise ValueError(f"{where}: resultado esperado inexistente {c.expected.outcome!r}")
            bad = sorted(set(c.expected.scores) - scores)
            if bad:
                raise ValueError(f"{where}: pontuações esperadas inexistentes {bad}")
            if c.expected.red_flags is not None:
                bad = sorted(set(c.expected.red_flags) - flags)
                if bad:
                    raise ValueError(f"{where}: red flags esperadas inexistentes {bad}")
