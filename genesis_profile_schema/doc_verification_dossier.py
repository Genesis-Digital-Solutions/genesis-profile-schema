"""
genesis_profile_schema/doc_verification_dossier.py — o contrato dos esquemas de
DOSSIÊ da Verificação Documental (v0.1.175, 19 Nov 2026).

Nasce com a verificação liminar de pedidos urbanísticos (RJUE) de um município,
mas é genérico: um esquema de dossiê é um pedido com um tipo, uma checklist de
documentos por tipo, uma matriz de procedimento (prazos, mecanismo de correção,
consequência), consultas externas e um desfecho proposto que uma pessoa valida.
Revisão do desenho: `codigo/docs/cmtv/REVISAO_plano_CMTV_19nov2026.md`.

Duas camadas, de propósito:
  * o PACK — a lei nacional (matriz, itens da Portaria, receitas de consulta,
    tabela de classes). Vive em CÓDIGO no genai-core, como os ficheiros do FEM,
    versionado e com casos de referência; é um `Scheme` normal da biblioteca
    (slug `rjue_pt`), nunca dados do perfil;
  * o OVERLAY — o que é do município (itens só da NIP ou do regulamento
    municipal, equivalências aceites, regras dos ficheiros, decisões jurídicas
    sobre células «a confirmar», limiares de aviso). Vive no perfil DENTRO de
    `tools.config.verify_documents.rules["<esquema>"].dossier`, para herdar o
    carril das regras configuráveis: portão com casos de referência em todos
    os saves, aprovação em 2 passos, versões, rota do GAIBO, fotografia por
    caso, regras próprias de cada frente (uma Partilhada não herda as do
    principal; uma Separada pode ser outro município).

O que NÃO está aqui, de propósito:
  * os sites das consultas externas (URL, hosts permitidos, exceções de TLS):
    são segurança e vivem na env do adaptador do genesis-mcp, nunca no perfil;
  * os moldes das cartas e do relatório: vão em `verify_documents.
    document_templates` (um por documento do esquema);
  * os feriados municipais: `calendar.holidays` do perfil da frente;
  * o prazo de conservação: `verify_documents.retention_months`;
  * expressões, regex ou texto interpretado pela IA como regra: as condições
    usam a gramática fechada de `rules_grammar.py`.

Vocabulários fechados (contrato com o genai-core, o fecore e o Studio): um
código fora destas listas é recusado ao gravar. «Não sei» tem sempre um valor
próprio (`nao_verificavel`, `escalar`) — um desconhecido nunca vira
`conforme`; quem avalia (o core) tem de o garantir e provar em teste.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import (AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, field_validator,
                      model_validator)

from .rules_grammar import validate_predicate

__all__ = [
    "CHECK_STATES", "QUERY_RESULTS", "OUTCOMES", "OUTCOME_KINDS", "ESCALATION_REASONS", "CORRECTIONS",
    "FACT_PREFIXES", "PRESENCE_ONLY_TYPES", "DEADLINE_NEAR_MIN_DAYS", "SUCCESSIVE_CONTROL_NEAR_MIN_DAYS",
    "DossierItemAdded", "DossierEquivalence", "DossierFileRules", "DossierReservedSpace", "DossierThresholds",
    "DossierMatrixDecision", "DocVerificationDossierOverlay", "outcome_kind", "CONSEQUENCE_KINDS",
    "NOT_DOSSIER_SCHEMES", "MAX_OVERLAY_NODES", "SafeText",
]

# ── Vocabulários ────────────────────────────────────────────────────────────────

#: Estado de cada item da checklist (o que o relatório imprime, por esta ordem).
CHECK_STATES = ("conforme", "nao_conforme", "em_falta", "nao_aplicavel", "dispensa_justificada")

#: Resultado de cada consulta externa. «Não verificado — sem acesso» = `nao_verificavel` com o motivo `no_access`.
QUERY_RESULTS = ("conforme", "deficiencia", "nao_verificavel", "escalar")

#: A espécie de cada desfecho — é por ela que as métricas, a exportação e a decisão agrupam, sem conhecer cada
#: código. `positive` = segue; `correction` = pede ao requerente que corrija; `negative` = termina o pedido;
#: `procedural` = ato do município que não decide o pedido; `review` = fica para uma pessoa decidir.
OUTCOME_KINDS = ("positive", "correction", "negative", "procedural", "review")

#: Os desfechos possíveis de um esquema de dossiê e a espécie de cada um. `escalar` é o único `review` e é o que o
#: agente propõe sempre que uma regra de escalamento dispara.
OUTCOMES: Dict[str, str] = {
    "prosseguir": "positive",
    "aperfeicoamento": "correction",
    "aperfeicoamento_cpa": "correction",
    "suprimento": "correction",
    "rejeicao_liminar": "negative",
    "rejeicao": "negative",
    "indeferimento": "negative",
    "ineptidao": "negative",
    "extincao": "negative",
    "inspecao": "procedural",
    "prorrogacao_complexidade": "procedural",
    "decisao_acessorio": "procedural",
    "escalar": "review",
}

#: Mecanismo de correção de uma linha da matriz.
CORRECTIONS = ("aperfeicoamento", "aperfeicoamento_cpa", "notificacao_unica", "nenhuma")

#: Motivos de escalamento (um por regra «escalar sempre» das instruções e os do anexo das consultas).
ESCALATION_REASONS = (
    "outcome_needs_human", "form_doubt", "matrix_missing", "matrix_to_confirm", "complex_legitimacy",
    "contradictory_docs", "waiver_unassessable", "complexity_extension", "unreadable_file", "cp_deadline_fault",
    "deadline_near", "successive_control_near", "start_works_incomplete", "pre_regime", "late_or_wrong_process",
    "conditional_doc_unclear", "no_letter_template", "forgery_signs", "other_technician", "registration_suspended",
    "site_down", "data_missing", "designation_equivalence", "insufficient_signatures_unclear", "manifest_violation",
)

#: De onde vêm os factos de uma condição. Uma condição só pode falar destes (o core achata os factos lidos assim).
FACT_PREFIXES = ("request.", "piece.", "pdf.", "query.", "case.")

#: Tipos de ficheiro aceites só por presença (o conteúdo não é lido; o relatório di-lo).
PRESENCE_ONLY_TYPES = ("dwg", "ods", "xls", "xlsx")

#: Os limiares de aviso só podem ANTECIPAR o aviso, nunca atrasá-lo: abaixo disto escalava-se tarde demais
#: (instruções do município: 5 dias de saneamento, 30 dias de controlo sucessivo).
DEADLINE_NEAR_MIN_DAYS = 5
SUCCESSIVE_CONTROL_NEAR_MIN_DAYS = 30

MAX_ITEMS_ADDED = 200
MAX_EQUIVALENCES = 500
MAX_MATRIX_DECISIONS = 60
MAX_TEXT = 400
MAX_TERM = 120
#: Orçamento de nós de TODAS as condições de um overlay (o `rules_grammar` pede um teto por definição: 200 condições no
#: teto de cada uma multiplicavam o custo de avaliar cada caso).
MAX_OVERLAY_NODES = 3000

_ID = r"^[a-z][a-z0-9_]{1,47}$"
_ID_RE = re.compile(_ID)
#: Controlo, quebras de linha e os invisíveis/bidi que disfarçam um texto (o mesmo conjunto dos canais e do registo
#: de ações). Estes textos vão para o relatório, as cartas ao requerente e o Word: um `\x00` partia a geração do
#: documento de todos os casos da frente, e uma quebra de linha injetava parágrafos numa carta.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]")

#: Esquemas da biblioteca que NÃO são de dossiê: um `dossier` neles é um engano (e partia um rollback do core).
NOT_DOSSIER_SCHEMES = ("concursos", "fem")


def outcome_kind(code: str) -> Optional[str]:
    """A espécie de um desfecho (`None` = código desconhecido — quem chama recusa, nunca adivinha)."""
    return OUTCOMES.get(code)


def _clean(value: str, what: str) -> str:
    """Texto que vai para documentos: sem controlos nem quebras de linha, e com pelo menos um carácter visível."""
    if _CONTROL.search(value):
        raise ValueError(f"{what}: sem caracteres de controlo, invisíveis nem quebras de linha")
    if not value.strip():
        raise ValueError(f"{what}: vazio")
    return value


def _fold(value: str) -> str:
    """Para comparar designações: NFC, sem distinguir maiúsculas nem espaços nas pontas."""
    return unicodedata.normalize("NFC", value).casefold().strip()


SafeText = Annotated[str, Field(min_length=1, max_length=MAX_TEXT), AfterValidator(lambda v: _clean(v, "texto"))]
SafeTerm = Annotated[str, Field(min_length=1, max_length=MAX_TERM), AfterValidator(lambda v: _clean(v, "designação"))]


class _Text(BaseModel):
    """Um texto nas duas línguas (o agente do Studio traduz). PT é o que o relatório imprime."""
    model_config = ConfigDict(extra="forbid")

    pt: SafeText
    en: SafeText


def _condition(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Gramática fechada do Intake, sem pontuações nem red flags, e só sobre factos do dossiê."""
    if value is None:
        return None
    refs = validate_predicate(value, allow_scores=False, allow_outcome_refs=False)
    if refs.money_questions or refs.uses_reference_year:
        raise ValueError("uma condição do dossiê não usa montantes convertidos nem o ano de referência")
    fora = sorted(q for q in refs.questions if not q.startswith(FACT_PREFIXES))
    if fora:
        raise ValueError(f"factos fora do dossiê na condição (só {', '.join(FACT_PREFIXES)}): {fora[:5]}")
    return value


def _unique(values: List[str], what: str) -> List[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"{what} repetido")
    return values


# ── Overlay ─────────────────────────────────────────────────────────────────────

class DossierItemAdded(BaseModel):
    """Um item que o MUNICÍPIO acrescenta à checklist do pack (itens só da NIP ou do regulamento municipal).
    - id: `c.` + nome curto, único (nunca colide com os do pack);
    - request_types: os tipos de pedido (linhas da matriz do pack) a que se aplica;
    - label: o que o relatório escreve na linha;
    - reference: a norma que o exige — obrigatória: nunca se pede um documento sem norma;
    - applies_when: condição sobre os factos lidos (`request.*`, `piece.<tipo>.*`, `pdf.*`, `query.*`, `case.*`);
      ausente = aplica-se sempre ao tipo de pedido. Um facto que não se leu deixa a condição INDETERMINADA, que
      escala (`conditional_doc_unclear`) — nunca `nao_aplicavel` em silêncio (garantia do avaliador do core);
    - satisfied_by: os tipos de documento (do pack) que o cumprem;
    - on_unknown: o que fica quando não se consegue decidir (nunca `conforme`);
    - waiver_allowed: o coordenador pode justificar a dispensa (`dispensa_justificada`, avaliada por uma pessoa);
    - enabled: desligar sem apagar."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^c\.[a-z0-9]+(?:[._][a-z0-9]+)*$", max_length=62)
    request_types: List[str] = Field(min_length=1, max_length=50)
    label: _Text
    reference: SafeText
    applies_when: Optional[Dict[str, Any]] = None
    satisfied_by: List[str] = Field(min_length=1, max_length=20)
    on_unknown: Literal["escalar", "em_falta"] = "escalar"
    waiver_allowed: StrictBool = False
    enabled: StrictBool = True

    @field_validator("request_types", "satisfied_by")
    @classmethod
    def _ids(cls, values: List[str]) -> List[str]:
        for v in values:
            if not isinstance(v, str) or not _ID_RE.fullmatch(v):
                raise ValueError("cada tipo tem de ser um id curto (minúsculas, algarismos e «_»)")
        return _unique(values, "tipo")

    @field_validator("applies_when")
    @classmethod
    def _cond(cls, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return _condition(value)


class DossierEquivalence(BaseModel):
    """Uma designação que o município aceita como equivalente entre o termo de responsabilidade e a declaração da
    associação profissional (ex.: «estruturas» = «estabilidade»). Sem a equivalência, a diferença escala
    (`designation_equivalence`); com ela, fica `conforme` com nota. Nasce de casos escalados e decididos.
    - source: onde ficou a decisão (despacho, ata, processo)."""
    model_config = ConfigDict(extra="forbid")

    termo: SafeTerm
    declaration: SafeTerm
    source: SafeText

    @model_validator(mode="after")
    def _different(self) -> "DossierEquivalence":
        if _fold(self.termo) == _fold(self.declaration):
            raise ValueError("uma equivalência liga duas designações diferentes")
        return self


class DossierReservedSpace(BaseModel):
    """O espaço que as peças escritas deixam livre para o carimbo do município."""
    model_config = ConfigDict(extra="forbid")

    width_cm: Union[StrictInt, StrictFloat] = Field(gt=0, le=30)
    height_cm: Union[StrictInt, StrictFloat] = Field(gt=0, le=30)
    corner: Literal["top_right", "top_left", "bottom_right", "bottom_left"] = "top_right"


class DossierFileRules(BaseModel):
    """As regras municipais dos ficheiros entregues (regulamento de instrução em formato digital). Campo ausente
    (`None`) = a regra não se verifica. Verificações deterministas, sem IA.
    - min_dpi: resolução mínima das imagens nas peças;
    - page_size: formato das peças escritas;
    - pdfa_required: as peças têm de declarar PDF/A;
    - reserved_space: o espaço livre para o carimbo;
    - presence_only: tipos aceites só por presença (o conteúdo não se lê, e o relatório diz que não se verificou).
    O padrão do nome dos ficheiros fica de fora até haver a convenção exata (entra como modelo com marcadores,
    nunca como regex do cliente)."""
    model_config = ConfigDict(extra="forbid")

    min_dpi: Optional[StrictInt] = Field(default=None, ge=72, le=1200)
    page_size: Optional[Literal["A4", "A3"]] = None
    pdfa_required: Optional[StrictBool] = None
    reserved_space: Optional[DossierReservedSpace] = None
    presence_only: List[Literal["dwg", "ods", "xls", "xlsx"]] = Field(default_factory=list, max_length=4)

    @field_validator("presence_only")
    @classmethod
    def _uniq(cls, values: List[str]) -> List[str]:
        return _unique(values, "tipo de ficheiro")


class DossierThresholds(BaseModel):
    """Quando avisar antes de um prazo (escalamento). `None` = o do pack. Só se pode avisar MAIS CEDO."""
    model_config = ConfigDict(extra="forbid")

    deadline_near_business_days: Optional[StrictInt] = Field(default=None, ge=DEADLINE_NEAR_MIN_DAYS, le=30)
    successive_control_near_days: Optional[StrictInt] = Field(default=None, ge=SUCCESSIVE_CONTROL_NEAR_MIN_DAYS,
                                                               le=180)


#: As espécies que podem ser a consequência de não corrigir: termina o pedido ou dá um ato do município. Nunca
#: «segue» (uma célula «a confirmar» não pode virar verde), nunca «corrige» (seria um segundo convite) nem «escalar».
CONSEQUENCE_KINDS = ("negative", "procedural")


class DossierMatrixDecision(BaseModel):
    """A decisão do apoio jurídico do município sobre uma linha da matriz que o pack traz «a confirmar»: o mecanismo
    de correção e/ou a consequência de não corrigir (pelo menos um). O core só a aplica a células que o pack marca
    «a confirmar»; nas outras é ignorada e o Studio di-lo (a lei não se muda por município). Enquanto não houver
    decisão, escala (`matrix_to_confirm`).
    - source: onde ficou a decisão (obrigatório)."""
    model_config = ConfigDict(extra="forbid")

    correction: Optional[Literal["aperfeicoamento", "aperfeicoamento_cpa", "notificacao_unica", "nenhuma"]] = None
    consequence: Optional[str] = None
    source: SafeText

    @field_validator("consequence")
    @classmethod
    def _outcome(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        kind = outcome_kind(value)
        if kind is None:
            raise ValueError(f"desfecho desconhecido (um de: {', '.join(OUTCOMES)})")
        if kind not in CONSEQUENCE_KINDS:
            raise ValueError("a consequência de não corrigir termina o pedido ou é um ato do município "
                             "(nunca «prosseguir», uma nova correção ou «escalar»)")
        return value

    @model_validator(mode="after")
    def _decides_something(self) -> "DossierMatrixDecision":
        if self.correction is None and self.consequence is None:
            raise ValueError("uma decisão da matriz diz o mecanismo de correção, a consequência, ou os dois")
        return self


class DocVerificationDossierOverlay(BaseModel):
    """O que um município (ou outro cliente) acrescenta ou decide sobre um esquema de dossiê. Vive em
    `tools.config.verify_documents.rules["<esquema>"].dossier`. Tudo vazio = o pack tal como vem do core.
    Mudar ou desligar um item do PACK faz-se pelos `overrides` da mesma entrada de `rules` (por id); as regras de
    escalamento do pack não se desligam (o core recusa).
    - items_added: itens próprios da checklist;
    - equivalences: designações aceites entre termo e declaração;
    - file_rules: regras municipais dos ficheiros;
    - thresholds: limiares de aviso dos prazos;
    - matrix_decisions: decisões jurídicas sobre linhas «a confirmar», por tipo de pedido."""
    model_config = ConfigDict(extra="forbid")

    items_added: List[DossierItemAdded] = Field(default_factory=list, max_length=MAX_ITEMS_ADDED)
    equivalences: List[DossierEquivalence] = Field(default_factory=list, max_length=MAX_EQUIVALENCES)
    file_rules: Optional[DossierFileRules] = None
    thresholds: Optional[DossierThresholds] = None
    matrix_decisions: Dict[str, DossierMatrixDecision] = Field(default_factory=dict, max_length=MAX_MATRIX_DECISIONS)

    @field_validator("items_added")
    @classmethod
    def _unique_items(cls, items: List[DossierItemAdded]) -> List[DossierItemAdded]:
        _unique([i.id for i in items], "id de item")
        nodes = sum(validate_predicate(i.applies_when, allow_scores=False, allow_outcome_refs=False).nodes
                    for i in items if i.applies_when is not None)
        if nodes > MAX_OVERLAY_NODES:
            raise ValueError(f"condições grandes demais no conjunto ({nodes} nós; até {MAX_OVERLAY_NODES})")
        return items

    @field_validator("equivalences")
    @classmethod
    def _unique_pairs(cls, pairs: List[DossierEquivalence]) -> List[DossierEquivalence]:
        _unique([f"{_fold(p.termo)}\x1f{_fold(p.declaration)}" for p in pairs], "par de designações")
        return pairs

    @field_validator("matrix_decisions")
    @classmethod
    def _matrix_keys(cls, value: Dict[str, DossierMatrixDecision]) -> Dict[str, DossierMatrixDecision]:
        for k in value:
            if not _ID_RE.fullmatch(k):
                raise ValueError("cada tipo de pedido tem de ser um id curto (minúsculas, algarismos e «_»)")
        return value
