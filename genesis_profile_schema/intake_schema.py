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

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator, StrictBool, StrictInt

from .field_definition import FieldDefinition, I18nHelp, I18nText, StrictNumber, _i18n_checker
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
    "IntakePresentation",
    "INTAKE_CAPABILITIES",
    "IntakeDoubleValidation",
    "IntakeQualityPolicy",
    "IntakeDocumentTemplate",
    "INTAKE_DOCUMENT_KINDS",
    "IntakeSheetCell",
    "IntakeSheetResult",
    "INTAKE_SHEET_SOURCES",
    "IntakeReviewPolicy",
    "IntakeRetention",
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


# Dados que se podem PROPOR a partir do documento de identificação (v0.1.91,
# B9): lista FECHADA, independente do fornecedor da leitura (o core traduz).
INTAKE_ID_DOCUMENT_FIELDS = (
    "full_name", "given_names", "surname", "document_number", "nationality", "issuing_country",
    "date_of_birth", "date_of_expiry", "place_of_birth", "sex", "address",
)


class IntakeQuestion(FieldDefinition):
    """Uma pergunta = um campo + o que o percurso precisa.

    - `show_if`: só aparece (e só conta para a completude e para as regras)
      quando a condição é verdadeira — as condições do próprio questionário.
    - `assist`: glossário disponível nesta pergunta (e só se a secção deixar).
    - `prefill_from`: de onde se pode PROPOR a resposta; quem responde
      confirma sempre. Vazio = nunca pré-preenchida (declarações, perguntas
      de conhecimento). `previous` (v0.1.90): a resposta da avaliação
      ANTERIOR da mesma pessoa, numa reavaliação pedida pela equipa (ex.:
      informação insuficiente → pedir o que falta) — nunca nas perguntas que
      são o próprio teste.
    - Com várias origens, propõe-se a primeira que der valor, por ordem FIXA:
      documento de identificação, CV, comprovativo de morada, convite,
      avaliação anterior (o documento da própria pessoa vale mais do que o
      que a equipa escreveu no convite).
    """
    section: Key
    show_if: Optional[BaseCondition] = None
    assist: bool = True
    prefill_from: List[Literal["id_document", "cv", "invitation", "proof_of_address", "previous"]] = Field(
        default_factory=list, max_length=5)
    # Que dado do CONVITE se propõe (v0.1.84) — só com `invitation` em
    # `prefill_from` (ex.: 1.5 telemóvel → "phone", 1.6 email → "email").
    prefill_field: Optional[Literal["name", "email", "phone"]] = None
    # Que dado do DOCUMENTO DE IDENTIFICAÇÃO se propõe (v0.1.91, B9) — só com
    # `id_document` em `prefill_from`. Sem ele, o documento não propõe nada
    # nesta pergunta (o editor do Studio avisa).
    prefill_document_field: Optional[Literal[INTAKE_ID_DOCUMENT_FIELDS]] = None  # type: ignore[valid-type]

    @model_validator(mode="after")
    def _prefill_field_do_convite(self) -> "IntakeQuestion":
        if self.prefill_field and "invitation" not in self.prefill_from:
            raise ValueError(f"pergunta {self.key!r}: prefill_field só com prefill_from 'invitation'")
        if self.prefill_document_field and "id_document" not in self.prefill_from:
            raise ValueError(f"pergunta {self.key!r}: prefill_document_field só com prefill_from 'id_document'")
        if ((self.prefill_field or self.prefill_document_field or "previous" in self.prefill_from)
                and (not self.editable or self.hidden)):
            # Uma proposta tem de poder ser confirmada ou corrigida por quem responde.
            raise ValueError(f"pergunta {self.key!r}: proposta (prefill) numa pergunta não editável ou escondida")
        return self


class IntakeGlossaryTerm(BaseModel):
    """Termo do glossário fechado e aprovado. `sections` é uma ALLOWLIST: um
    termo sem secções não é servido em lado nenhum. `questions` (v0.1.88)
    estreita mais: com perguntas, o termo só aparece NESSAS (que têm de estar
    numa das `sections`); vazio = todas as perguntas com assistência dessas
    secções. Onde o termo aparece não é conteúdo: fica fora do hash da
    metodologia (o texto do termo conta)."""
    model_config = _CLOSED

    key: Key
    term: I18nText
    text: I18nText
    sections: List[Key] = Field(default_factory=list, max_length=MAX_SECTIONS)
    questions: List[Key] = Field(default_factory=list, max_length=MAX_QUESTIONS)


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


class IntakeFxPolicy(BaseModel):
    """Câmbio das avaliações (v0.1.83, épico Intake B8; caderno A8): taxas de
    referência do BCE do dia útil ANTERIOR à data de referência (a submissão),
    fotografadas no processo com a fonte. O BCE não publica todas as moedas
    (ex.: AED, SAR): essas só com `via_usd` — unidades da moeda por 1 USD
    (ex.: AED 3.6725), um parâmetro que a Compliance aprova e que, por ser da
    metodologia, obriga a subir a versão quando muda. Sem taxa, o montante
    fica POR DETERMINAR e o processo vai a uma pessoa — nunca se adivinha.
    Sem este bloco não há câmbio (o comportamento até à v0.1.82)."""
    model_config = _CLOSED

    source: Literal["ecb"] = "ecb"
    via_usd: Dict[Annotated[str, Field(pattern=_CURRENCY_RE)], FxRate] = Field(
        default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def _via_usd_sem_usd(self) -> "IntakeFxPolicy":
        if "USD" in self.via_usd:
            raise ValueError("via_usd: o USD não se converte através de si próprio")
        return self


class IntakeMethodology(BaseModel):
    model_config = _CLOSED

    version: str = Field(pattern=_VERSION_RE)
    effective_from: Optional[str] = Field(default=None, pattern=_DATE_RE)
    approval: Optional[MethodologyApproval] = None
    base_currency: str = Field(default="EUR", pattern=_CURRENCY_RE)
    fx: Optional[IntakeFxPolicy] = None
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


class IntakeAccessPolicy(BaseModel):
    """Acesso de quem responde: link pessoal + código enviado a cada entrada
    (decisões do Bruno, 2 Out 2026). Os valores por omissão são os decididos;
    os tetos impedem uma configuração de desligar a proteção (nunca mais de
    10 tentativas por código, nunca um link de 6 meses)."""
    model_config = _CLOSED

    link_valid_days: StrictInt = Field(default=30, ge=1, le=90)
    session_idle_minutes: StrictInt = Field(default=30, ge=5, le=120)
    code_ttl_minutes: StrictInt = Field(default=10, ge=2, le=30)
    code_max_attempts: StrictInt = Field(default=5, ge=1, le=10)
    max_failed_codes: StrictInt = Field(default=3, ge=1, le=10)
    code_min_interval_seconds: StrictInt = Field(default=60, ge=30, le=600)
    codes_per_day: StrictInt = Field(default=10, ge=1, le=30)
    channels: List[Literal["email", "sms"]] = Field(default_factory=lambda: ["email", "sms"],
                                                    min_length=1, max_length=2)

    @model_validator(mode="after")
    def _sem_repetidos(self) -> "IntakeAccessPolicy":
        if len(set(self.channels)) != len(self.channels):
            raise ValueError("canais repetidos")
        return self


class IntakePresentation(BaseModel):
    """Como o percurso SE APRESENTA a quem responde (v0.1.81, 3 Out 2026; B5 —
    maquetas da proposta). Só aparência: nada aqui muda respostas,
    visibilidade nem avaliação, por isso fica fora do hash da metodologia
    (como `access`) — a fotografia de cada processo guarda-o na mesma.
    Vazio = o ecrã por omissão do produto."""
    model_config = _CLOSED

    # Mostra cada pergunta e opção também na OUTRA língua da definição, por
    # baixo (questionários bilingues aprovados assim). Com mais de duas
    # línguas, a outra é a primeira das `languages` diferente da escolhida.
    bilingual: StrictBool = False
    # Rodapé legal em todos os ecrãs (texto simples, nunca HTML).
    footer: I18nHelp = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Textos aprovados do percurso (v0.1.84, 3 Out 2026; Anexo II da Quadrantis)
# ─────────────────────────────────────────────────────────────────────────────

MAX_NOTICE = 12000           # a informação sobre dados pessoais do Anexo II tem ~4 500 por língua
I18nNotice = Annotated[Dict[str, str], AfterValidator(_i18n_checker(MAX_NOTICE, True))]


class IntakeNotice(BaseModel):
    model_config = _CLOSED
    title: I18nHelp = Field(default_factory=dict)
    text: I18nNotice


class IntakeWarning(BaseModel):
    """Advertência escrita de um resultado (v0.1.85; Anexos III/IV da
    Quadrantis): emitida DEPOIS de validado esse resultado e entregue no
    percurso; quem respondeu confirma a receção escolhendo a Opção A (não
    prossegue) ou B (prossegue), num campo separado da mensagem."""
    model_config = _CLOSED
    title: I18nText
    text: I18nNotice
    option_a: I18nText
    option_b: I18nText


class IntakeTexts(BaseModel):
    """Textos APROVADOS que o percurso mostra tal e qual (v0.1.84): `intro`
    (finalidade, no início), `privacy` (informação sobre dados pessoais — a
    tomada de conhecimento é OBRIGATÓRIA antes da 1.ª resposta), `declaration`
    (aceite OBRIGATORIAMENTE na submissão) e `incomplete_warning` (no ecrã de
    revisão quando falta resposta). Texto simples, nunca HTML. Fora do hash da
    metodologia: não é o que se avalia; a fotografia de cada processo guarda-os
    e cada aceitação regista a impressão do texto aceite."""
    model_config = _CLOSED

    intro: Optional[IntakeNotice] = None
    privacy: Optional[IntakeNotice] = None
    declaration: Optional[IntakeNotice] = None
    incomplete_warning: I18nHelp = Field(default_factory=dict)
    # Resultado final (chave da metodologia) → advertência a emitir (v0.1.85).
    warnings: Dict[Key, IntakeWarning] = Field(default_factory=dict, max_length=20)


# ─────────────────────────────────────────────────────────────────────────────
# Comunicações (v0.1.85, 3 Out 2026; épico Intake B8 — caderno D7)
# ─────────────────────────────────────────────────────────────────────────────

_EMAIL_RE = r"^[^@\s<>\"',;]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}$"


class IntakeCommunications(BaseModel):
    """O que o produto envia sozinho (por email). `invite`: o convite com o
    link pessoal, na criação do processo. `reminders`: lembretes nos
    `reminder_days` (dias desde o convite para o questionário; desde a emissão
    para a advertência) — cada lembrete leva um link NOVO e o anterior deixa
    de valer. `team_alert_day`: alerta à equipa (área da equipa e
    `team_alert_emails`) quando ainda não houve resposta/receção. Tudo
    desligado por omissão."""
    model_config = _CLOSED

    invite: StrictBool = False
    reminders: StrictBool = False
    reminder_days: List[Annotated[StrictInt, Field(ge=1, le=60)]] = Field(
        default_factory=lambda: [3, 7], max_length=5)
    team_alert_day: Optional[Annotated[StrictInt, Field(ge=1, le=90)]] = 15
    team_alert_emails: List[Annotated[str, Field(pattern=_EMAIL_RE)]] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _dias(self) -> "IntakeCommunications":
        if self.reminder_days != sorted(set(self.reminder_days)):
            raise ValueError("reminder_days: crescentes e sem repetidos")
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Revisão pela equipa (v0.1.82, 3 Out 2026; épico Intake B6)
# ─────────────────────────────────────────────────────────────────────────────

# Capacidades da área da equipa — lista FECHADA do produto: cada uma só existe
# se houver código que a imponha (uma capacidade inventada num perfil seria
# falsa segurança). Crescem com as ações: `reopen` (pedir complemento /
# reabrir) está RESERVADA — recusada até a ação existir. `quality` (controlo
# de qualidade mensal da Compliance, D8) existe desde a v0.1.87.
INTAKE_CAPABILITIES = ("view", "create", "review", "second_review", "export", "quality")
_RESERVED_CAPABILITIES = ("reopen",)

_ROLE_RE = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"
Role = Annotated[str, Field(pattern=_ROLE_RE)]


def _default_roles() -> Dict[str, List[str]]:
    return {
        "view": ["Intake.Commercial", "Intake.Reviewer", "Intake.Supervisor", "Intake.Auditor", "Intake.Compliance"],
        "create": ["Intake.Commercial"],
        "review": ["Intake.Reviewer", "Intake.Supervisor"],
        "second_review": ["Intake.Supervisor"],
        "export": ["Intake.Supervisor", "Intake.Auditor", "Intake.Compliance"],
        "quality": ["Intake.Compliance"],
    }


class IntakeDoubleValidation(BaseModel):
    """Quando a decisão de quem revê precisa de uma 2.ª pessoa (D3). Mudar o
    resultado do motor obriga SEMPRE (decisão de produto, não configurável).
    `min_amount`: montante previsto do processo (indicado por quem o cria) a
    partir do qual é obrigatória, em `currency`; noutra moeda não há
    conversão — conta como obrigatória (nunca se adivinha uma taxa)."""
    model_config = _CLOSED

    min_amount: Optional[StrictNumber] = Field(default=None, gt=0)
    currency: str = Field(default="EUR", pattern=_CURRENCY_RE)
    on_red_flags: StrictBool = True
    outcomes: List[Key] = Field(default_factory=list, max_length=20)


class IntakeQualityPolicy(BaseModel):
    """Controlo de qualidade mensal pela Compliance (D8, v0.1.87): dos
    processos VALIDADOS no mês, uma amostra aleatória de `sample_rate`, com um
    mínimo de `sample_min` — todos, se forem menos do que o mínimo. A amostra
    é tirada uma vez por mês fechado e fica gravada (semente incluída, para
    se poder refazer a conta). Só operação: fora do hash da metodologia."""
    model_config = _CLOSED

    sample_rate: StrictNumber = Field(default=0.10, gt=0, le=1)
    sample_min: StrictInt = Field(default=5, ge=1, le=100)


MAX_LIST_COLUMNS = 3


class IntakeReviewPolicy(BaseModel):
    """Quem pode o quê na área da equipa e quando a decisão precisa de 2.ª
    validação. `roles`: capacidade → app roles do Entra (claim `roles`) que a
    dão; uma capacidade sem papéis não é dada a ninguém. Separação de funções
    (fixa no produto): quem criou o processo não o revê nem o valida (D2) e
    quem fez a 1.ª validação não faz a 2.ª. Todo o resultado é validado por
    uma pessoa antes de ser comunicado (D1). Só operação: fora do hash da
    metodologia, como `access`."""
    model_config = _CLOSED

    roles: Dict[str, List[Role]] = Field(default_factory=_default_roles, max_length=len(INTAKE_CAPABILITIES))
    double_validation: IntakeDoubleValidation = Field(default_factory=IntakeDoubleValidation)
    # Quem cria tem de indicar o montante previsto (sem ele a regra do
    # montante não se aplica — o processo vai a 2.ª validação por precaução).
    amount_required: StrictBool = False
    # Execução em paralelo com a matriz antiga (v0.1.84): quem revê regista o
    # resultado que a matriz deu, para medir a concordância motor × matriz.
    # Desliga-se quando a matriz deixar de se usar.
    parallel_run: StrictBool = False
    quality: IntakeQualityPolicy = Field(default_factory=IntakeQualityPolicy)
    # Colunas a mais na lista da área da equipa (v0.1.91): até 3 perguntas
    # (ex.: País). Mostra a resposta; o resto da lista é fixo no produto.
    list_columns: List[Key] = Field(default_factory=list, max_length=MAX_LIST_COLUMNS)

    @model_validator(mode="after")
    def _capacidades(self) -> "IntakeReviewPolicy":
        for cap, roles in self.roles.items():
            if cap in _RESERVED_CAPABILITIES:
                raise ValueError(f"capacidade {cap!r} ainda não existe (reservada)")
            if cap not in INTAKE_CAPABILITIES:
                raise ValueError(f"capacidade desconhecida {cap!r}")
            if len(roles) > 20 or len(set(roles)) != len(roles):
                raise ValueError(f"capacidade {cap!r}: papéis repetidos ou a mais (máx. 20)")
        return self


INTAKE_UPLOAD_RETENTION = ("delete_after_submit", "keep_with_process")


class IntakeUploads(BaseModel):
    """Os ficheiros que quem responde carrega para PROPOR respostas (v0.1.91,
    B9): o documento de identificação e o CV (ou o PDF do LinkedIn). Pedem-se
    SÓ quando alguma pergunta os tem em `prefill_from` — nada a ligar — e são
    sempre opcionais: nunca bloqueiam o percurso. `retention` decide o
    FICHEIRO: `delete_after_submit` (por omissão) apaga-o na submissão e
    ficam os dados confirmados, os excertos e a impressão SHA-256;
    `keep_with_process` guarda-o com o processo. Só operação: fora do hash da
    metodologia."""
    model_config = _CLOSED

    retention: Literal[INTAKE_UPLOAD_RETENTION] = "delete_after_submit"  # type: ignore[valid-type]


class IntakeRetention(BaseModel):
    """Por quanto tempo se guarda cada PROCESSO (v0.1.93; ex.: 5 anos — art.
    307.º-B do CVM, suporte duradouro do art. 72.º do Reg. 2017/565). Conta da
    conclusão da avaliação (a validação final; com advertência, a receção dela
    se for posterior; submetido e nunca validado → a submissão) ou da data da
    subscrição registada pela equipa, se for posterior. No fim do prazo o core
    apaga o processo, os ficheiros e a pessoa (se não tiver outros processos);
    durante o prazo os documentos guardados ficam imutáveis (WORM).
    Processos nunca avaliados (cancelados, ou expirados sem submissão)
    apagam-se `unevaluated_days` depois. `years` vazio = nada se apaga
    sozinho (como até aqui). Só operação: fora do hash da metodologia."""
    model_config = _CLOSED

    years: Optional[int] = Field(default=None, ge=1, le=30)
    unevaluated_days: int = Field(default=90, ge=7, le=3650)


# ─────────────────────────────────────────────────────────────────────────────
# Documentos gerados (v0.1.89, 4 Out 2026; épico Intake B7)
# ─────────────────────────────────────────────────────────────────────────────

INTAKE_DOCUMENT_KINDS = ("questionnaire", "internal_sheet", "warning", "spreadsheet")
_TEMPLATE_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.(docx|xlsx)$"

# ─── Folha de cálculo do cliente como molde (v0.1.92, épico Intake B13) ───────
# Ex.: a matriz do Anexo V da Quadrantis. O core preenche as células de entrada,
# a folha recalcula (LibreOffice) e o resultado da célula `result` entra na
# execução em paralelo. Lista FECHADA de origens dos valores.
INTAKE_SHEET_SOURCES = (
    "answer",           # a resposta à pergunta (com `map` valor → texto da folha nas escolhas)
    "amount_base",      # um montante convertido para a moeda base pela avaliação (câmbio A8)
    "subject_name",     # o nome de quem responde
    "fund",             # o fundo/veículo da definição
    "evaluation_date",  # a data de referência da avaliação
)
# «Folha!A1» — o nome da folha sem os caracteres que o Excel proíbe.
_CELL_RE = r"^[^:\\/?*\[\]!'\x00-\x1f]{1,31}![A-Z]{1,3}[1-9][0-9]{0,6}$"
MAX_SHEET_CELLS = 200
_SHEET_TEXT = 200


class IntakeSheetCell(BaseModel):
    """Uma célula de entrada da folha. `answer`/`amount_base` levam a
    `question`; `map` (só em `answer`) traduz o valor da opção para o texto
    que a folha espera (ex.: `master` → «Mestrado / Masters Degree»); numa
    escolha múltipla escreve-se o PRIMEIRO valor do mapa que a resposta tiver
    (a ordem do mapa é a prioridade). `not_applicable`: o texto a escrever
    quando a pergunta não se aplica ao processo (ex.: «N/A»); uma pergunta que
    se aplica e ficou por responder deixa a célula vazia. `not_applicable_when`
    restringe o «N/A» a uma condição (as macros da matriz da Quadrantis só o
    punham no ensino secundário — na habilitação «Outra» a área fica VAZIA e a
    matriz dá «Informação insuficiente», caderno A7); sem ela, vale sempre que a
    pergunta não se aplica."""
    model_config = _CLOSED

    ref: str = Field(pattern=_CELL_RE)
    source: Literal[INTAKE_SHEET_SOURCES]  # type: ignore[valid-type]
    question: Optional[Key] = None
    map: Dict[str, Annotated[str, Field(min_length=1, max_length=_SHEET_TEXT)]] = Field(
        default_factory=dict, max_length=100)
    not_applicable: Optional[str] = Field(default=None, min_length=1, max_length=50)
    not_applicable_when: Optional[BaseCondition] = None

    @model_validator(mode="after")
    def _coerente(self) -> "IntakeSheetCell":
        needs_q = self.source in ("answer", "amount_base")
        if needs_q != (self.question is not None):
            raise ValueError(f"célula {self.ref}: `question` só (e sempre) com answer/amount_base")
        if self.map and self.source != "answer":
            raise ValueError(f"célula {self.ref}: `map` só com source answer")
        if self.not_applicable is not None and not needs_q:
            raise ValueError(f"célula {self.ref}: `not_applicable` só em células de uma pergunta")
        if self.not_applicable_when is not None and self.not_applicable is None:
            raise ValueError(f"célula {self.ref}: `not_applicable_when` só com `not_applicable`")
        return self


class IntakeSheetResult(BaseModel):
    """A célula com o resultado que a folha calcula e o mapa do texto dela
    para os resultados da metodologia (ex.: «ADEQUADO» → `adequado`)."""
    model_config = _CLOSED

    ref: str = Field(pattern=_CELL_RE)
    outcomes: Dict[Annotated[str, Field(min_length=1, max_length=_SHEET_TEXT)], Key] = Field(
        min_length=1, max_length=20)
_SHA256_RE = r"^[0-9a-f]{64}$"
MAX_DOCUMENTS = 20


class IntakeDocumentTemplate(BaseModel):
    """Um molde Word oficial do cliente (cópia com marcadores `{{…}}`), guardado
    no armazenamento DO CLIENTE e carregado pelo Studio — nunca num repo.
    `kind`: questionnaire (o questionário preenchido), internal_sheet (folha
    interna) ou warning (advertência — `outcome` diz de que resultado).
    `sha256` é a impressão do molde APROVADO: o core recusa gerar com um ficheiro
    diferente. Versão e entrada em vigor por molde (Procedimento, ponto 2): um
    processo usa o molde em vigor na sua data; `revoked_from` deixa de o usar.
    Os moldes têm versão própria: ficam fora do hash da metodologia."""
    model_config = _CLOSED

    key: Key
    kind: Literal[INTAKE_DOCUMENT_KINDS]  # type: ignore[valid-type]
    outcome: Optional[Key] = None
    title: I18nText
    template: str = Field(pattern=_TEMPLATE_RE)
    sha256: str = Field(pattern=_SHA256_RE)
    version: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    effective_from: str = Field(pattern=_DATE_RE)
    revoked_from: Optional[str] = Field(default=None, pattern=_DATE_RE)
    # Só nas folhas de cálculo (`kind: spreadsheet`, v0.1.92).
    cells: List[IntakeSheetCell] = Field(default_factory=list, max_length=MAX_SHEET_CELLS)
    result: Optional[IntakeSheetResult] = None

    @model_validator(mode="after")
    def _coerente(self) -> "IntakeDocumentTemplate":
        if (self.kind == "warning") != (self.outcome is not None):
            raise ValueError(f"documento {self.key!r}: `outcome` só (e sempre) nas advertências")
        sheet = self.kind == "spreadsheet"
        if sheet != self.template.endswith(".xlsx"):
            raise ValueError(f"documento {self.key!r}: a folha de cálculo é .xlsx e os outros moldes .docx")
        if sheet and not self.cells:
            raise ValueError(f"documento {self.key!r}: uma folha de cálculo precisa de células a preencher")
        if not sheet and (self.cells or self.result is not None):
            raise ValueError(f"documento {self.key!r}: `cells`/`result` só nas folhas de cálculo")
        refs = [c.ref for c in self.cells] + ([self.result.ref] if self.result else [])
        if len(set(refs)) != len(refs):
            raise ValueError(f"documento {self.key!r}: célula repetida")
        if self.revoked_from is not None and self.revoked_from <= self.effective_from:
            raise ValueError(f"documento {self.key!r}: revogado antes de entrar em vigor")
        return self


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
    access: IntakeAccessPolicy = Field(default_factory=IntakeAccessPolicy)
    presentation: IntakePresentation = Field(default_factory=IntakePresentation)
    texts: IntakeTexts = Field(default_factory=IntakeTexts)
    communications: IntakeCommunications = Field(default_factory=IntakeCommunications)
    # Fundo / OIC a que o questionário se aplica (v0.1.85; Anexos III/IV «OIC/Fund»).
    fund: I18nHelp = Field(default_factory=dict)
    review: IntakeReviewPolicy = Field(default_factory=IntakeReviewPolicy)
    # Moldes dos documentos gerados (v0.1.89, B7).
    documents: List[IntakeDocumentTemplate] = Field(default_factory=list, max_length=MAX_DOCUMENTS)
    # Ficheiros carregados por quem responde (v0.1.91, B9).
    uploads: IntakeUploads = Field(default_factory=IntakeUploads)
    # Prazo de conservação dos processos e apagamento automático (v0.1.93).
    retention: IntakeRetention = Field(default_factory=IntakeRetention)

    @model_validator(mode="after")
    def _referencias(self) -> "IntakeDefinition":
        _Checker(self).run()
        # Nova avaliação (v0.1.90): as perguntas que são o TESTE (as que uma
        # pontuação conta como certas/erradas — `count_matches`) nunca levam a
        # resposta anterior proposta — responde-se de novo.
        if self.methodology:
            teste = {it.q for sc in self.methodology.scores for t in sc.terms
                     if getattr(t, "kind", None) == "count_matches" for it in t.items}
            # v0.1.91: também o CV e o documento — o teste responde-o a própria pessoa.
            bad = sorted(q.key for q in self.questions
                         if q.key in teste and {"previous", "cv", "id_document"} & set(q.prefill_from))
            if bad:
                raise ValueError(f"prefill_from 'previous'/'cv'/'id_document' em perguntas de conhecimento (o teste): {bad[:10]}")
        # Um texto que se ACEITA tem de existir em todas as línguas do percurso
        # (ninguém aceita um texto que não pode ler na língua em que responde).
        for name in ("intro", "privacy", "declaration"):
            notice = getattr(self.texts, name)
            if notice is not None:
                faltam = [l for l in self.languages if not (notice.text.get(l) or "").strip()]
                if faltam:
                    raise ValueError(f"texts.{name}: falta o texto em {faltam}")
        if self.texts.warnings:
            known = {o.key for o in (self.methodology.outcomes if self.methodology else [])}
            bad = sorted(set(self.texts.warnings) - known)
            if bad:
                raise ValueError(f"texts.warnings: resultados inexistentes {bad}")
            for key, w in self.texts.warnings.items():
                for part in ("title", "text", "option_a", "option_b"):
                    faltam = [l for l in self.languages if not (getattr(w, part).get(l) or "").strip()]
                    if faltam:
                        raise ValueError(f"texts.warnings.{key}.{part}: falta o texto em {faltam}")
        if self.presentation.bilingual and len(self.languages) < 2:
            raise ValueError("presentation.bilingual precisa de pelo menos duas languages")
        if self.documents:
            _unique([d.key for d in self.documents], "documentos")
            known = {o.key for o in (self.methodology.outcomes if self.methodology else [])}
            seen = set()
            by_q = {q.key: q for q in self.questions}
            for doc in self.documents:
                if doc.kind == "warning" and doc.outcome not in known:
                    raise ValueError(f"documento {doc.key!r}: resultado inexistente {doc.outcome!r}")
                for cell in doc.cells:
                    q = by_q.get(cell.question) if cell.question else None
                    if cell.question and q is None:
                        raise ValueError(f"documento {doc.key!r}, célula {cell.ref}: pergunta inexistente {cell.question!r}")
                    if cell.not_applicable_when is not None:
                        refs = validate_predicate(cell.not_applicable_when, allow_scores=False,
                                                  allow_outcome_refs=False).questions
                        bad = sorted(set(refs) - set(by_q))
                        if bad:
                            raise ValueError(f"documento {doc.key!r}, célula {cell.ref}: condição com perguntas "
                                             f"inexistentes {bad}")
                    if cell.source == "amount_base" and q.type != "money":
                        raise ValueError(f"documento {doc.key!r}, célula {cell.ref}: amount_base só numa pergunta de montante")
                    if cell.map:
                        values = {str(o.value) for o in q.options or []}
                        bad = sorted(set(cell.map) - values)
                        if bad:
                            raise ValueError(f"documento {doc.key!r}, célula {cell.ref}: opções inexistentes {bad}")
                if doc.result is not None:
                    bad = sorted(set(doc.result.outcomes.values()) - known)
                    if bad:
                        raise ValueError(f"documento {doc.key!r}: resultados inexistentes {bad}")
                for ident in ((doc.kind, doc.outcome, "v", doc.version), (doc.kind, doc.outcome, "d", doc.effective_from)):
                    if ident in seen:
                        raise ValueError(f"documento {doc.key!r}: versão ou data de entrada em vigor repetida para o "
                                         f"mesmo tipo (qual se usava?)")
                    seen.add(ident)
        if self.review.list_columns:
            _unique(self.review.list_columns, "review.list_columns")
            bad = sorted(set(self.review.list_columns) - {q.key for q in self.questions})
            if bad:
                raise ValueError(f"review.list_columns: perguntas inexistentes {bad}")
        dv = self.review.double_validation.outcomes
        if dv:
            known = {o.key for o in self.methodology.outcomes} if self.methodology else set()
            bad = sorted(set(dv) - known)
            if bad:
                raise ValueError(f"review.double_validation.outcomes: resultados inexistentes {bad}")
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
        by_key = {q.key: q for q in d.questions}
        for g in d.glossary:
            bad = sorted(set(g.sections) - sections)
            if bad:
                raise ValueError(f"glossário {g.key!r}: secções inexistentes {bad}")
            if len(set(g.questions)) != len(g.questions):
                raise ValueError(f"glossário {g.key!r}: perguntas repetidas")
            for qk in g.questions:
                if qk not in by_key:
                    raise ValueError(f"glossário {g.key!r}: pergunta inexistente {qk!r}")
                if by_key[qk].section not in g.sections:
                    raise ValueError(f"glossário {g.key!r}: a pergunta {qk!r} não está nas secções do termo")
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
