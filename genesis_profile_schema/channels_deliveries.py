"""
genesis_profile_schema/channels_deliveries.py — `channels.outbound.deliveries[]` (v0.1.172, carril
C2-mín fase 5, §6.6/§6.8 do pack dos canais): ENTREGAR um documento a um sistema de gestão documental
(GED) quando um módulo emite um evento. O primeiro caso é o da CCDR: parecer emitido na Verificação
Documental → registo no Filedoc, pelo servidor MCP com o adaptador `dms` (família `dms_*`).

Forma (combinada a 17 Nov 2026 com a sessão do adaptador Filedoc, ditada pelo que o adaptador aceita):

  {id, enabled, label?,
   when:    {module: "doc_verification", event: "opinion_issued"},
   to:      {transport: "mcp", server: <nome de um servidor MCP do perfil>, connector: "dms"},
   record:  {record_type, subtype, company_id?, support_type_id?, classification[], confidential,
             subject, from_user, to?, dynamic_fields{<chave>: {value, type?}}},
   process: {by: id|number|reference, from: <campo do caso>}?,
   files:   {main: "pdf", extra: [docx|xlsx|rules]},
   route:   {routing_type, to, message?, deadline_days?, confidential}?}

Um VALOR é exatamente um de:
  {source: "case.<campo>"}  — um campo da lista FECHADA `CASE_FIELDS` (a projeção do caso que o core monta;
                              nunca um caminho livre: um mapeamento não vai buscar o que a entrega não precisa);
  {literal: "texto"}        — até 512, sem caracteres de controlo;
  {template: "Parecer — {case.application_number} — {case.entity_name}"} — SÓ no `subject` e no
                              `route.message`: os marcadores são `{case.<campo>}` da mesma lista; não há
                              expressões, filtros nem aninhamento. O core limpa cada valor (controlo e quebras
                              de linha) e, se o resultado passar o teto do destino, RECUSA a entrega (nunca corta).

O que NÃO é configurável (constantes do core, menos superfície): as tentativas, a chave de sucesso
(`record_id`), a referência do registo (o core põe a `ref` do parecer quando o GED tem o campo de
referência pesquisável) e a chave de idempotência (o id do pedido de saída).

Credenciais do GED NUNCA aqui: vivem no Key Vault do cliente → env do servidor MCP (padrão SAP).
Os ficheiros vão DENTRO do pedido ao MCP (decisão do Bruno, 17 Nov 2026: os ficheiros da Verificação
Documental nunca saem por link SAS), com teto no core.

Exposição `internal`, como todo o `channels`. Grava-se só com valor: `deliveries: []` não se escreve.
"""

from __future__ import annotations

import re
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import (BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_serializer,
                      model_validator)

#: Eventos que podem disparar uma entrega (módulo → eventos). Cresce com cada emissor novo.
DELIVERY_EVENTS: Dict[str, Tuple[str, ...]] = {"doc_verification": ("opinion_issued",)}
DeliveryModule = Literal["doc_verification"]
DeliveryEvent = Literal["opinion_issued"]

#: A projeção do caso que um mapeamento pode usar (o core monta-a; teste de paridade no core).
CASE_FIELDS: Tuple[str, ...] = (
    "case.application_number",   # n.º da candidatura (o campo que o esquema declara; pode vir vazio)
    "case.entity_name",          # entidade candidata
    "case.entity_nif",           # NIF/NIPC da entidade
    "case.procedure",            # procedimento / aviso (ex.: «FEM 2026»)
    "case.project",              # projeto
    "case.outcome",              # sentido do parecer (código: go | go_with_reservations | no_go)
    "case.outcome_label",        # sentido do parecer (texto, na língua do parecer)
    "case.opinion_ref",          # referência do parecer emitido
    "case.opinion_version",      # versão n
    "case.issued_on",            # data de emissão (AAAA-MM-DD, dia de Lisboa)
    "case.issuer_email",         # email de quem emitiu (só verificado; senão vazio)
    "case.name",                 # nome do caso na VD
)
CaseField = Literal["case.application_number", "case.entity_name", "case.entity_nif", "case.procedure",
                    "case.project", "case.outcome", "case.outcome_label", "case.opinion_ref",
                    "case.opinion_version", "case.issued_on", "case.issuer_email", "case.name"]

#: Formatos do parecer emitido (`tools/doc_verification/opinion/issue.py::MIMES`).
EXTRA_FILES: Tuple[str, ...] = ("docx", "xlsx", "rules")
ExtraFile = Literal["docx", "xlsx", "rules"]

MAX_DELIVERIES = 10
MAX_LITERAL = 512
MAX_SUBJECT_TEMPLATE = 512
MAX_DYNAMIC_FIELDS = 50
MAX_CLASSIFICATION = 20
MAX_ROUTE_MESSAGE = 1000
MAX_TEMPLATE = MAX_ROUTE_MESSAGE
MAX_DEADLINE_DAYS = 365

#: Id de uma entrega (minúsculas: entra em chaves e registos).
DELIVERY_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
#: Nome de um servidor MCP do perfil (o padrão do Studio é `mcp-{adapter}-{project}-{env}`).
SERVER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
#: Chave de um campo dinâmico do GED (a do adaptador Filedoc, `mapping._KEY`).
DYNAMIC_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
#: Nome de tipo de coluna como o `dms_describe` o devolve (ex.: «Text»; o adaptador confere a lista dele).
DYNAMIC_TYPE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,39}")
#: Um marcador de modelo. Qualquer `{` ou `}` fora de um marcador válido é recusado.
PLACEHOLDER_RE = re.compile(r"\{(case\.[a-z_]{1,40})\}")
#: O endereço de email da saída (`core/platform/outbound/addresses.py::EMAIL_RE`, espelho do drain do Studio).
EMAIL_RE = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.[A-Za-z]{2,63}")
MAX_EMAIL = 254
#: Controlo, quebras de linha e os invisíveis/bidi que disfarçam um texto (o conjunto do registo de ações).
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]")


def _clean_text(v: str, cap: int, what: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"{what}: texto")
    if len(v) > cap:
        raise ValueError(f"{what}: até {cap} caracteres")
    if _CONTROL.search(v):
        raise ValueError(f"{what}: sem caracteres de controlo nem quebras de linha")
    return v


def _check_template(v: str) -> str:
    _clean_text(v, MAX_TEMPLATE, "modelo")
    rest = PLACEHOLDER_RE.sub("", v)
    if "{" in rest or "}" in rest:
        raise ValueError("modelo: só marcadores {case.<campo>}; chavetas soltas não")
    used = PLACEHOLDER_RE.findall(v)
    if not used:
        raise ValueError("modelo sem marcadores: usar `literal`")
    unknown = sorted({u for u in used if u not in CASE_FIELDS})
    if unknown:
        raise ValueError(f"modelo: campos do caso desconhecidos: {', '.join(unknown[:5])}")
    return v


def _check_email(v: str) -> str:
    if not isinstance(v, str) or len(v) > MAX_EMAIL or not EMAIL_RE.fullmatch(v):
        raise ValueError("email inválido")
    return v


class DeliveryValue(BaseModel):
    """Um valor do mapeamento: `source` OU `literal` (o `template` só onde o campo o aceita)."""
    model_config = ConfigDict(extra="forbid")

    source: Optional[CaseField] = None
    literal: Optional[str] = None
    template: Optional[str] = None

    @field_validator("literal")
    @classmethod
    def _literal(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _clean_text(v, MAX_LITERAL, "literal")

    @field_validator("template")
    @classmethod
    def _template(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _check_template(v)

    @model_validator(mode="after")
    def _exactly_one(self) -> "DeliveryValue":
        if sum(x is not None for x in (self.source, self.literal, self.template)) != 1:
            raise ValueError("um valor é exatamente um de: source, literal, template")
        return self


def _no_template(v: DeliveryValue, what: str) -> DeliveryValue:
    if v.template is not None:
        raise ValueError(f"{what}: modelos só no assunto e na mensagem do encaminhamento")
    return v


class DynamicField(BaseModel):
    """Um campo dinâmico do GED (`dms_describe` dá a lista, a obrigatoriedade e o tipo)."""
    model_config = ConfigDict(extra="forbid")

    value: DeliveryValue
    # O tipo como o `dms_describe` o devolve: o nome («Text») ou o número.
    type: Optional[str | StrictInt] = None

    @field_validator("value")
    @classmethod
    def _value(cls, v: DeliveryValue) -> DeliveryValue:
        return _no_template(v, "campo dinâmico")

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v is None:
            return v
        if isinstance(v, int):
            if v <= 0:
                raise ValueError("tipo de campo: número positivo")
            return v
        if not DYNAMIC_TYPE_RE.fullmatch(v):
            raise ValueError("tipo de campo inválido")
        return v


class RecordTo(BaseModel):
    """Destinatário do REGISTO: um utilizador do GED (o SaveDoc não aceita grupos)."""
    model_config = ConfigDict(extra="forbid")

    user_id: Optional[StrictInt] = Field(default=None, gt=0)
    email: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _check_email(v)

    @model_validator(mode="after")
    def _one(self) -> "RecordTo":
        if sum(x is not None for x in (self.user_id, self.email)) != 1:
            raise ValueError("destinatário do registo: exatamente um de user_id ou email")
        return self


class RouteTo(BaseModel):
    """Destinatário do ENCAMINHAMENTO: um utilizador, um grupo funcional ou um email."""
    model_config = ConfigDict(extra="forbid")

    user_id: Optional[StrictInt] = Field(default=None, gt=0)
    group_id: Optional[StrictInt] = Field(default=None, gt=0)
    email: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _check_email(v)

    @model_validator(mode="after")
    def _one(self) -> "RouteTo":
        if sum(x is not None for x in (self.user_id, self.group_id, self.email)) != 1:
            raise ValueError("destinatário do encaminhamento: exatamente um de user_id, group_id ou email")
        return self


class DeliveryRecord(BaseModel):
    """Os metadados do registo no GED (`dms_create_record` / `record` do `dms_deliver`)."""
    model_config = ConfigDict(extra="forbid")

    record_type: StrictInt = Field(gt=0)
    subtype: Literal["internal", "incoming", "outgoing"]
    company_id: Optional[StrictInt] = Field(default=None, gt=0)
    support_type_id: Optional[StrictInt] = Field(default=None, gt=0)
    classification: List[StrictInt] = Field(default_factory=list)
    confidential: StrictBool = False
    subject: DeliveryValue
    # `issuer_by_email`: o GED procura o emissor pelo email (verificado); sem ele, o utilizador técnico com aviso.
    from_user: Literal["issuer_by_email", "technical"] = "technical"
    to: Optional[RecordTo] = None
    dynamic_fields: Dict[str, DynamicField] = Field(default_factory=dict)

    @field_validator("subject")
    @classmethod
    def _subject(cls, v: DeliveryValue) -> DeliveryValue:
        if v.template is not None and len(v.template) > MAX_SUBJECT_TEMPLATE:
            raise ValueError(f"assunto: modelo até {MAX_SUBJECT_TEMPLATE} caracteres")
        return v

    @field_validator("classification")
    @classmethod
    def _classification(cls, v: List[int]) -> List[int]:
        if len(v) > MAX_CLASSIFICATION:
            raise ValueError(f"classificação: até {MAX_CLASSIFICATION} ids")
        if any(x <= 0 for x in v):
            raise ValueError("classificação: ids positivos")
        if len(v) != len(set(v)):
            raise ValueError("classificação: ids repetidos")
        return v

    @field_validator("dynamic_fields")
    @classmethod
    def _dynamic(cls, v: Dict[str, DynamicField]) -> Dict[str, DynamicField]:
        if len(v) > MAX_DYNAMIC_FIELDS:
            raise ValueError(f"campos dinâmicos: até {MAX_DYNAMIC_FIELDS}")
        bad = [k for k in v if not DYNAMIC_KEY_RE.fullmatch(k)]
        if bad:
            raise ValueError(f"chave de campo dinâmico inválida: {bad[0][:40]!r}")
        return v


class DeliveryProcess(BaseModel):
    """Associar o registo a um processo do GED, encontrado por um campo do caso. Grava-se `{by, from}`."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    by: Literal["id", "number", "reference"]
    from_: CaseField = Field(alias="from")

    @model_serializer(mode="plain")
    def _dump(self) -> Dict[str, str]:
        # Sempre a chave `from` (a do contrato), com ou sem `by_alias` — o padrão do `in` da ingestão
        # dependia de quem grava; aqui não.
        return {"by": self.by, "from": self.from_}


class DeliveryRoute(BaseModel):
    """Encaminhar o registo depois dos ficheiros (no Filedoc: uma circulação, ex. «Para assinatura»)."""
    model_config = ConfigDict(extra="forbid")

    routing_type: StrictInt = Field(gt=0)
    to: RouteTo
    message: Optional[DeliveryValue] = None
    deadline_days: Optional[StrictInt] = Field(default=None, ge=1, le=MAX_DEADLINE_DAYS)
    confidential: StrictBool = False

    @field_validator("message")
    @classmethod
    def _message(cls, v: Optional[DeliveryValue]) -> Optional[DeliveryValue]:
        if v is not None and v.literal is not None and len(v.literal) > MAX_ROUTE_MESSAGE:
            raise ValueError(f"mensagem: até {MAX_ROUTE_MESSAGE} caracteres")
        return v


class DeliveryFiles(BaseModel):
    """Que ficheiros do documento emitido seguem (o principal primeiro)."""
    model_config = ConfigDict(extra="forbid")

    main: Literal["pdf"] = "pdf"
    extra: List[ExtraFile] = Field(default_factory=list)

    @field_validator("extra")
    @classmethod
    def _extra(cls, v: List[str]) -> List[str]:
        if len(v) != len(set(v)):
            raise ValueError("ficheiros repetidos")
        return v


class DeliveryWhen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: DeliveryModule
    event: DeliveryEvent

    @model_validator(mode="after")
    def _known(self) -> "DeliveryWhen":
        if self.event not in DELIVERY_EVENTS.get(self.module, ()):
            raise ValueError(f"o módulo {self.module} não emite o evento {self.event}")
        return self


class DeliveryTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["mcp"] = "mcp"
    server: str
    connector: Literal["dms"] = "dms"

    @field_validator("server")
    @classmethod
    def _server(cls, v: str) -> str:
        if not isinstance(v, str) or not SERVER_RE.fullmatch(v):
            raise ValueError("servidor MCP: o nome de um servidor do perfil (letras, dígitos, «-», «_», «.»)")
        return v


class OutboundDelivery(BaseModel):
    """Uma entrega configurada. Desligada por omissão = não entrega."""
    model_config = ConfigDict(extra="forbid")

    id: str
    enabled: StrictBool = False
    label: Optional[str] = None
    when: DeliveryWhen
    to: DeliveryTarget
    record: DeliveryRecord
    process: Optional[DeliveryProcess] = None
    files: DeliveryFiles = Field(default_factory=DeliveryFiles)
    route: Optional[DeliveryRoute] = None

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not isinstance(v, str) or not DELIVERY_ID_RE.fullmatch(v):
            raise ValueError("id da entrega: minúsculas, dígitos, «-» e «_» (até 40)")
        return v

    @field_validator("label")
    @classmethod
    def _label(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _clean_text(v, 80, "nome")


def check_deliveries(v: List[OutboundDelivery]) -> List[OutboundDelivery]:
    if len(v) > MAX_DELIVERIES:
        raise ValueError(f"no máximo {MAX_DELIVERIES} entregas")
    ids = [d.id for d in v]
    if len(ids) != len(set(ids)):
        raise ValueError("entregas com o mesmo id")
    return v


__all__ = ["OutboundDelivery", "DeliveryRecord", "DeliveryValue", "DynamicField", "RecordTo", "RouteTo",
           "DeliveryProcess", "DeliveryRoute", "DeliveryFiles", "DeliveryWhen", "DeliveryTarget",
           "check_deliveries", "CASE_FIELDS", "DELIVERY_EVENTS", "EXTRA_FILES", "MAX_DELIVERIES",
           "MAX_LITERAL", "MAX_TEMPLATE", "PLACEHOLDER_RE", "EMAIL_RE"]
