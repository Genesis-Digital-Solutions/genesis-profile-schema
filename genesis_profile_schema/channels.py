"""
channels.py — o bloco `channels` do perfil: ENTRADAS e ENCAMINHAMENTO (v0.1.163,
carril C1a do `codigo/CONTEXT_PACK_canais_entrada_saida.md`, passo 5B do épico
«Agente colega»).

O canal só recebe, normaliza e entrega; o módulo só conhece a sua porta; o
encaminhamento é configuração (isto). Ausente/`null` = hoje: o core traduz em
memória o `ingest.sources` de sempre (cada fonte = uma entrada `email`, com o
encaminhamento por rótulo/triagem que ela já tem) e NADA muda.

  inputs[]   de onde se recebe. C1a: só `email`, sempre ligada a uma fonte
             existente do `ingest.sources` (`ingest_source`) — a caixa, o
             segredo e os filtros continuam lá. A entrada pode ter id próprio;
             sem entradas declaradas, o id da fonte é o id da entrada.
  routes[]   para onde vai, por ORDEM — a 1.ª rota ligada que casa ganha.
             Nenhuma casa → o encaminhamento de hoje da fonte (fila da fonte,
             rótulos, triagem): nada se perde e nada muda em silêncio.
             `inputs` vazio = vale só para as entradas do PRINCIPAL (as que não
             são de nenhuma variante — o core, `core/platform/inbound/routing.py`);
             uma rota para entradas de uma variante lista-as. `when` vazio = casa
             sempre (rota de recurso de uma entrada).

Gramática das condições (`when: {all, any}`, D16 do pack — substitui, não soma,
a do `accept_filter`, que fica como tradução): `all` = todas têm de bater; `any`
= pelo menos uma (vazia = não restringe). Cada condição `{field, op, value}`
com `field` e `op` FECHADOS (campo ou operador desconhecido = erro de schema,
nunca silêncio). Como o core avalia (`core/platform/inbound/routing.py`):
  • texto (`subject`, `body`, `attachments.name`, `attachments.mime`,
    `classifier.label`, `content.language`, `front`): sem maiúsculas nem
    acentos.
  • endereços (`from.address`, `from.domain`, `to`): só `equals`, `in_list` e
    `exists`, com o endereço/domínio EXATO (só minúsculas), como o
    `accept_filter` — nunca substring («exemplo.pt» não casa
    «exemplo.pt.atacante.com»); `from.address` aceita um domínio («@d»).
  • listas (`to`, `attachments.*`): basta UM elemento bater.
  • `exists` (value true/false): o campo tem/não tem valor.
  • `time.hour`: a hora de receção no fuso do cliente (0–23).
  • SEM `regex` (revisão de 11 Nov 2026): o padrão seria avaliado sobre texto
    de quem envia, o `re` do Python não tem tempo limite e nenhuma lista de
    padrões proibidos fecha o ReDoS (alternâncias como `(a|aa)+`, repetições encadeadas…) — um só email
    parava o job de ingestão do cliente. Volta quando houver um motor com
    tempo limite.
`classifier.label` só existe quando a fonte tem classificador.

Destinos (`to.module`, v0.1.164 — carril C1b): `queue` (pedido numa fila,
`to.queue`) e `doc_verification` (abre um caso da Verificação Documental por
reclamar, com as peças em quarentena — `to.front` = a frente onde o caso nasce;
vazio/ausente = a frente dona da caixa; `to.join` = quando um email novo se junta
a um caso ainda por reclamar em vez de abrir outro: `reference` (a referência do
recibo no assunto — o critério fiável), `thread` (o mesmo fio de email) e
`sender` (o mesmo remetente), dentro de `window_days`; `to.receipt` = o recibo ao
remetente com o número do caso e as peças recebidas e, com `list_refused`, as
recusadas e porquê). O recibo só sai pela resposta automática fixa da fonte
(DMARC + anti-ciclo do core).

Exposição: as ENTRADAS são da Genesis (`internal` — caixas, fontes, segredos);
as ROTAS são do cliente (`client_write`, v0.1.164): condições, destino, frente,
junção e recibo. ⚠️ GAIBO: com folhas `client_write`, `channels` deixa de ser uma
área inteiramente interna e o teste das áreas do GAIBO JÁ NÃO falha fechado ao
subir o pin — as rotas abrir-se-iam sozinhas. O re-pin do GAIBO para ≥ 0.1.164
leva no MESMO commit a área `channels` no `AREA_FLOOR` (que fecha a escrita da
área inteira) e as rotas abertas por exceção, por decisão (handoff
`codigo/HANDOFF_gaibo_channels_area_floor.md`). `channels.routes.inputs` aponta
para ids de entradas que o cliente não lista (são internas): o GAIBO precisa de
outra fonte para os nomes.

Gravação: o `RouteTarget` só grava os campos com valor (`queue` na fila;
`front`/`join`/`receipt` na VD) — um perfil com rotas de fila escrito por esta
versão relê-se num core com a v0.1.163 (`extra="forbid"` recusava as chaves
`null` novas). Numa rota de fila, `join`/`receipt` (mesmo desligados) e `front`
são recusados: o editor só os envia com `module: doc_verification`.

SAÍDA (`outbound`, v0.1.172 — carril C2-mín, D19: só kinds NOVOS; nenhum emissor
de hoje passa por aqui): `outbound.kinds[]` = um interruptor por tipo de saída
(`contact.ask`/`contact.tell` — o agente contacta uma pessoa, passo 6 do épico;
`document.deliver` — entregar um documento a um sistema externo, §6.6;
`routine.report` — relatório de uma rotina, passo 7). Desligado por omissão:
um kind que não está aqui ligado NÃO envia nada (falha fechada). `language`
= `person` (a língua da pessoa à frente: contacto › membro da equipa › item ›
frente › principal › pt) ou `front` (sempre a língua da frente).
O aviso de que a mensagem foi escrita por IA (AI Act art. 50) NÃO é
configurável: o core põe-no sempre que quem escreve é o agente — um interruptor
deixaria desligá-lo. Destinatários, níveis de consentimento por kind,
idempotência e registo vivem no core (`core/platform/outbound/`), nunca aqui.
`outbound.deliveries[]` (mesma versão, C2-mín fase 5) = entregas de um documento emitido a um
sistema de gestão documental pelo servidor MCP (`channels_deliveries.py`, onde está a forma).
Exposição `internal` (a Genesis liga; o GAIBO só com handoff). Grava-se só
quando tem tipos: `channels` sem `outbound` relê-se num core com a v0.1.171 e
num GAIBO com a v0.1.170 (com `outbound`, ambos o recusam — pins primeiro).

POLÍTICA DE CONTACTO (`outbound.contact`, v0.1.174 — passo 6 do épico, decisão do Bruno de 19 Nov 2026: a
política vive AQUI, não num `agentic.contact`), do cliente (`client_write`):
  • `hours: {start: "09:00", end: "19:00", business_days_only: true}` — quando o agente pode contactar pessoas,
    na hora do cliente (`identity.timezone`) e, com `business_days_only`, só nos dias úteis do `calendar` (fim
    de semana e feriados). Fora da janela, a tarefa do agente que quer perguntar ou informar uma pessoa
    (`contact.ask`/`contact.tell`) ESPERA pela próxima abertura (nada se agenda na saída). Os tipos
    transacionais (`document.deliver`) nunca esperam. A janela não atravessa a meia-noite (`start` < `end`).
    Ausente = sem restrição (o de hoje);
  • `answer_max_hours` (1–168; ausente = 72) — quanto tempo, no máximo, o agente espera pela resposta de uma
    pessoa antes de desistir e passar o assunto a alguém da equipa; o agente pode pedir menos, nunca mais.
Fora das listas de propósito: numa lista a escrita do cliente substituía também os campos internos (`kinds`).
Grava-se só o que tem valor (um core com a v0.1.173 recusava as chaves novas, mesmo nulas).

⚠️ ORDEM DE ROLLOUT (a mesma regra do `mcp.servers[].signing`): os modelos são
`extra="forbid"` e a gramática é fechada, logo um core com ESTE pin recusa um
`channels` escrito por uma versão futura (um módulo, campo ou operador novo) —
e com ele o save do perfil inteiro (400), também numa promoção dev→prod para um
core de prod mais atrasado ou num rollback da imagem. Por isso: nada de valores
de uma versão nova no perfil antes de o core (e o GAIBO) terem o pin; o Studio
só escreve o que o core alvo anuncia; promoção e clone conferem o pin do
destino. O `routing.parse` do core, ao ler, falha à vista e fica o
encaminhamento de hoje.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import (BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_serializer,
                      model_validator)

from .channels_deliveries import OutboundDelivery, check_deliveries

#: Canais conhecidos (allowlist). O core só LÊ os de `LIVE_CHANNELS`; os outros
#: validam (o Studio pode prepará-los desligados) e ficam inertes com aviso.
CHANNEL_KINDS: Tuple[str, ...] = ("email", "sms", "whatsapp", "voice", "teams", "http",
                                  "web", "mcp", "a2a", "tester")
LIVE_CHANNELS: Tuple[str, ...] = ("email",)
#: Portas dos módulos (cresce um carril de cada vez: C1b juntou `doc_verification`).
MODULES: Tuple[str, ...] = ("queue", "doc_verification")
#: Como um email se junta a um caso ainda por reclamar (C1b). Fechado.
JOIN_BY: Tuple[str, ...] = ("reference", "thread", "sender")
JOIN_WINDOW_DAYS_DEFAULT = 7
JOIN_WINDOW_DAYS_MAX = 90
#: Slug de uma frente — o das frentes que o core cria (`core/handlers/profile_front_write.py`:
#: começa por letra ou dígito, até 40). Avaliado com `fullmatch`.
FRONT_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")

#: Campo → tipo. Fechado.
ROUTE_FIELDS: Dict[str, str] = {
    "from.address": "address",
    "from.domain": "address",
    "to": "address",
    "subject": "text",
    "body": "text",
    "attachments.name": "text",
    "attachments.mime": "text",
    "attachments.size": "number",
    "classifier.label": "text",
    "thread.is_reply": "bool",
    "content.language": "text",
    "time.hour": "number",
    "front": "text",
}
#: Operadores permitidos por tipo de campo.
OPS_BY_KIND: Dict[str, Tuple[str, ...]] = {
    "text": ("equals", "in_list", "contains", "exists"),
    "address": ("equals", "in_list", "exists"),
    "number": ("equals", "gte", "lte", "exists"),
    "bool": ("equals", "exists"),
}
OPS: Tuple[str, ...] = ("equals", "in_list", "contains", "gte", "lte", "exists")

#: Ids de entradas e rotas. Aceita os ids das fontes do Studio (maiúsculas,
#: hífen, sublinhado, até 64 — sem entradas declaradas, o id da fonte é o da
#: entrada). Avaliado com `fullmatch` (um `$` aceitava uma quebra de linha no fim).
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
MAX_INPUTS = 50
MAX_ROUTES = 100
MAX_CONDITIONS = 20
MAX_LIST_VALUES = 200
MAX_TEXT_VALUE = 200
MAX_LABEL = 80
MAX_QUEUE = 64
#: Tipos de saída do C2-mín (D19: só kinds novos). Fechado: um kind novo entra
#: com o código que o emite.
OUTBOUND_KINDS: Tuple[str, ...] = ("contact.ask", "contact.tell", "document.deliver", "routine.report")
#: De onde vem a língua de uma saída.
OUTBOUND_LANGUAGES: Tuple[str, ...] = ("person", "front")
OutboundKindName = Literal["contact.ask", "contact.tell", "document.deliver", "routine.report"]
OutboundLanguage = Literal["person", "front"]

ChannelKind = Literal["email", "sms", "whatsapp", "voice", "teams", "http", "web", "mcp", "a2a",
                      "tester"]
RouteField = Literal["from.address", "from.domain", "to", "subject", "body", "attachments.name",
                     "attachments.mime", "attachments.size", "classifier.label", "thread.is_reply",
                     "content.language", "time.hour", "front"]
RouteOp = Literal["equals", "in_list", "contains", "gte", "lte", "exists"]


def _check_id(v: str, what: str) -> str:
    if not isinstance(v, str) or not ID_RE.fullmatch(v):
        raise ValueError(f"id {what}: letras, dígitos, «-» e «_», a começar por letra ou dígito (até 64)")
    return v


def _check_label(v: Optional[str]) -> Optional[str]:
    if v is not None and len(v) > MAX_LABEL:
        raise ValueError(f"nome até {MAX_LABEL} caracteres")
    return v


class ChannelCondition(BaseModel):
    """`{field, op, value}` — ver a gramática no topo do módulo."""
    # `allow_inf_nan=False`: um `Infinity` gravado não é JSON válido (parte o
    # editor do Studio) e um `NaN` nunca casa, em silêncio.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    field: RouteField
    op: RouteOp
    value: Union[bool, float, str, List[str], None] = None

    @model_validator(mode="after")
    def _shape(self) -> "ChannelCondition":
        kind = ROUTE_FIELDS[self.field]
        if self.op not in OPS_BY_KIND[kind]:
            raise ValueError(f"o operador «{self.op}» não serve o campo «{self.field}»")
        v = self.value
        if self.op == "exists":
            if not isinstance(v, bool):
                raise ValueError("«exists» leva true ou false")
        elif self.op == "in_list":
            if not isinstance(v, list) or not v or len(v) > MAX_LIST_VALUES:
                raise ValueError(f"«in_list» leva uma lista de 1 a {MAX_LIST_VALUES} textos")
            if any(not isinstance(x, str) or not x.strip() or len(x) > MAX_TEXT_VALUE for x in v):
                raise ValueError(f"«in_list»: textos não vazios, até {MAX_TEXT_VALUE} caracteres")
        elif kind == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"«{self.field}» compara com um número")
            if self.field == "time.hour" and not 0 <= v <= 23:
                raise ValueError("«time.hour» vai de 0 a 23")
            if self.field == "attachments.size" and v < 0:
                raise ValueError("«attachments.size» não é negativo")
        elif kind == "bool":
            if not isinstance(v, bool):
                raise ValueError(f"«{self.field}» compara com true ou false")
        else:                                           # texto/endereço: equals, contains
            if not isinstance(v, str) or not v.strip() or len(v) > MAX_TEXT_VALUE:
                raise ValueError(f"«{self.op}» leva um texto não vazio até {MAX_TEXT_VALUE} caracteres")
        return self


class RouteWhen(BaseModel):
    """`all` (todas) e `any` (pelo menos uma). Vazio = casa sempre."""
    model_config = ConfigDict(extra="forbid")

    # Os nomes do perfil são `all`/`any` (sem alias: o `to_blob_dict` grava
    # pelos nomes dos campos).
    all: List[ChannelCondition] = Field(default_factory=list)
    any: List[ChannelCondition] = Field(default_factory=list)

    @field_validator("all", "any")
    @classmethod
    def _cap(cls, v: List[ChannelCondition]) -> List[ChannelCondition]:
        if len(v) > MAX_CONDITIONS:
            raise ValueError(f"no máximo {MAX_CONDITIONS} condições por lista")
        return v


class CaseJoin(BaseModel):
    """Quando um email se junta a um caso da VD ainda por reclamar (C1b)."""
    model_config = ConfigDict(extra="forbid")

    by: List[Literal["reference", "thread", "sender"]] = Field(default_factory=lambda: ["reference"])
    window_days: StrictInt = JOIN_WINDOW_DAYS_DEFAULT

    @field_validator("by")
    @classmethod
    def _by(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("pelo menos um critério de junção (sem junção = não enviar o bloco `join`)")
        if len(v) != len(set(v)):
            raise ValueError("critério de junção repetido")
        return v

    @field_validator("window_days")
    @classmethod
    def _window(cls, v: int) -> int:
        if not 1 <= int(v) <= JOIN_WINDOW_DAYS_MAX:
            raise ValueError(f"janela de junção entre 1 e {JOIN_WINDOW_DAYS_MAX} dias")
        return int(v)


class CaseReceipt(BaseModel):
    """O recibo ao remetente com o número do caso (C1b). Desligado por omissão."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    list_refused: bool = True


class RouteTarget(BaseModel):
    """A porta do módulo e o que ela precisa: `queue` (a fila) ou
    `doc_verification` (caso da VD por reclamar; frente, junção e recibo)."""
    model_config = ConfigDict(extra="forbid")

    module: Literal["queue", "doc_verification"]
    queue: Optional[str] = None
    front: Optional[str] = None
    join: Optional[CaseJoin] = None
    receipt: Optional[CaseReceipt] = None

    @field_validator("queue")
    @classmethod
    def _queue(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if len(v) > MAX_QUEUE:
            raise ValueError(f"fila até {MAX_QUEUE} caracteres")
        return v or None       # vazia = sem fila; o validador por módulo diz se faz falta

    @field_validator("front")
    @classmethod
    def _front(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if v and not FRONT_RE.fullmatch(v):
            raise ValueError("frente inválida (slug: minúsculas, dígitos e hífen, até 40)")
        return v or None

    @model_validator(mode="after")
    def _per_module(self) -> "RouteTarget":
        if self.module == "queue":
            if not self.queue:
                raise ValueError("uma rota para a fila precisa da fila (to.queue)")
            if self.front or self.join or self.receipt:
                raise ValueError("frente, junção e recibo só servem a Verificação Documental")
        else:
            if self.queue:
                raise ValueError("uma rota para a Verificação Documental não leva fila (to.queue)")
        return self

    @model_serializer(mode="wrap")
    def _so_com_valor(self, handler):
        # Só grava o que tem valor (revisão de 11 Nov 2026): o `to_blob_dict` gravava
        # `"front": null, "join": null, "receipt": null` em TODAS as rotas de fila e um
        # core com a v0.1.163 (`extra="forbid"`) recusava então o `channels` — e com ele
        # o save do perfil inteiro — sem nenhum valor novo. O padrão do `signing` do MCP.
        dados = handler(self)
        if isinstance(dados, dict):
            for k in ("queue", "front", "join", "receipt"):
                if dados.get(k) is None:
                    dados.pop(k, None)
        return dados


class ChannelInput(BaseModel):
    """Uma ENTRADA. `email` = uma fonte do `ingest.sources` (`ingest_source`)."""
    model_config = ConfigDict(extra="forbid")

    id: str
    channel: ChannelKind
    enabled: bool = True
    ingest_source: Optional[str] = None
    label: Optional[str] = None

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return _check_id(v, "da entrada")

    @field_validator("label")
    @classmethod
    def _label(cls, v: Optional[str]) -> Optional[str]:
        return _check_label(v)

    @field_validator("ingest_source")
    @classmethod
    def _source(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _email_has_source(self) -> "ChannelInput":
        if self.channel == "email" and not (self.ingest_source or "").strip():
            raise ValueError(f"a entrada de email «{self.id}» precisa da fonte (ingest_source)")
        if self.channel != "email" and self.ingest_source:
            raise ValueError(f"«ingest_source» só serve entradas de email («{self.id}»)")
        return self


class ChannelRoute(BaseModel):
    """Uma ROTA: `inputs` (vazio = só as entradas do principal) + `when` → `to`."""
    model_config = ConfigDict(extra="forbid")

    id: str
    enabled: bool = True
    inputs: List[str] = Field(default_factory=list)
    when: RouteWhen = Field(default_factory=RouteWhen)
    to: RouteTarget
    label: Optional[str] = None

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return _check_id(v, "da rota")

    @field_validator("inputs")
    @classmethod
    def _inputs(cls, v: List[str]) -> List[str]:
        if len(v) > MAX_INPUTS:
            raise ValueError(f"no máximo {MAX_INPUTS} entradas por rota")
        for x in v:
            _check_id(x, "da entrada da rota")
        if len(v) != len(set(v)):
            raise ValueError("a mesma entrada repetida na rota")
        return v

    @field_validator("label")
    @classmethod
    def _label(cls, v: Optional[str]) -> Optional[str]:
        return _check_label(v)


class OutboundKind(BaseModel):
    """Um tipo de saída (C2-mín). Desligado por omissão = não envia."""
    model_config = ConfigDict(extra="forbid")

    kind: OutboundKindName
    # Estrito: um interruptor de envio que falha fechado não aceita «yes»/«on»/1.
    enabled: StrictBool = False
    language: OutboundLanguage = "person"


#: Quanto tempo, no máximo, o agente espera pela resposta de uma pessoa (`contact.ask`).
ANSWER_MAX_HOURS_CAP = 168
HHMM_PATTERN = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"


class OutboundContactHours(BaseModel):
    """`channels.outbound.contact.hours` (v0.1.174): quando o agente pode contactar pessoas — ver o topo."""
    model_config = ConfigDict(extra="forbid")

    start: str = Field(default="09:00", pattern=HHMM_PATTERN)
    end: str = Field(default="19:00", pattern=HHMM_PATTERN)
    business_days_only: StrictBool = True

    @model_validator(mode="after")
    def _janela(self) -> "OutboundContactHours":
        if self.start >= self.end:
            raise ValueError("o início tem de ser antes do fim (a janela não atravessa a meia-noite)")
        return self


class OutboundContact(BaseModel):
    """`channels.outbound.contact` (v0.1.174): a política de contacto do agente — ver o topo."""
    model_config = ConfigDict(extra="forbid")

    hours: Optional[OutboundContactHours] = None
    answer_max_hours: Optional[StrictInt] = Field(default=None, ge=1, le=ANSWER_MAX_HOURS_CAP)

    @model_serializer(mode="wrap")
    def _so_com_valor(self, handler):
        dados = handler(self)
        if isinstance(dados, dict):
            for k in ("hours", "answer_max_hours"):
                if dados.get(k) is None:
                    dados.pop(k, None)
        return dados


class ChannelsOutbound(BaseModel):
    """`channels.outbound` (v0.1.172): um interruptor por tipo de saída e as ENTREGAS a sistemas de
    gestão documental (`deliveries`, `channels_deliveries.py`)."""
    model_config = ConfigDict(extra="forbid")

    kinds: List[OutboundKind] = Field(default_factory=list)
    deliveries: List[OutboundDelivery] = Field(default_factory=list)
    contact: Optional[OutboundContact] = None

    @model_serializer(mode="wrap")
    def _deliveries_so_com_valor(self, handler):
        dados = handler(self)
        if isinstance(dados, dict) and not dados.get("deliveries"):
            dados.pop("deliveries", None)
        if isinstance(dados, dict) and dados.get("contact") is None:
            dados.pop("contact", None)
        return dados

    @field_validator("deliveries")
    @classmethod
    def _deliveries(cls, v: List[OutboundDelivery]) -> List[OutboundDelivery]:
        return check_deliveries(v)

    @field_validator("kinds")
    @classmethod
    def _kinds(cls, v: List[OutboundKind]) -> List[OutboundKind]:
        names = [k.kind for k in v]
        if len(names) != len(set(names)):
            raise ValueError("o mesmo tipo de saída repetido")
        return v


class ProfileChannels(BaseModel):
    """`channels` do perfil. `null`/ausente = o encaminhamento de hoje (`ingest.sources`)."""
    model_config = ConfigDict(extra="forbid")

    inputs: List[ChannelInput] = Field(default_factory=list)
    routes: List[ChannelRoute] = Field(default_factory=list)
    outbound: Optional[ChannelsOutbound] = None

    @model_serializer(mode="wrap")
    def _outbound_so_com_valor(self, handler):
        # Um core com a v0.1.171 (`extra="forbid"`) recusava `"outbound": null` — e
        # com ele o save do perfil inteiro — sem nenhum valor novo. O padrão do
        # `RouteTarget` e do `signing` do MCP.
        # `{kinds: [], deliveries: []}` vale o mesmo que ausente: também não se grava.
        dados = handler(self)
        if isinstance(dados, dict):
            out = dados.get("outbound")
            # `contact` por identidade (`is None`), nunca por veracidade: um horário gravado igual ao de
            # omissão (ou `{}`) é uma restrição — perdê-lo deixava o agente contactar a qualquer hora.
            if out is None or (isinstance(out, dict) and not out.get("kinds") and not out.get("deliveries")
                               and out.get("contact") is None):
                dados.pop("outbound", None)
        return dados

    @field_validator("inputs")
    @classmethod
    def _inputs(cls, v: List[ChannelInput]) -> List[ChannelInput]:
        if len(v) > MAX_INPUTS:
            raise ValueError(f"no máximo {MAX_INPUTS} entradas")
        ids = [i.id for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("entradas com o mesmo id")
        srcs = [i.ingest_source for i in v if i.ingest_source]
        if len(srcs) != len(set(srcs)):
            raise ValueError("duas entradas para a mesma fonte de email")
        return v

    @field_validator("routes")
    @classmethod
    def _routes(cls, v: List[ChannelRoute]) -> List[ChannelRoute]:
        if len(v) > MAX_ROUTES:
            raise ValueError(f"no máximo {MAX_ROUTES} rotas")
        ids = [r.id for r in v]
        if len(ids) != len(set(ids)):
            raise ValueError("rotas com o mesmo id")
        return v

    @model_validator(mode="after")
    def _route_inputs_known(self) -> "ProfileChannels":
        # Sem entradas declaradas, as rotas apontam para os ids das fontes do
        # `ingest.sources` (traduzidas pelo core) — não se veem daqui; o Studio
        # e o core confirmam. Com entradas declaradas, têm de existir.
        if not self.inputs:
            return self
        known = {i.id for i in self.inputs}
        for r in self.routes:
            unknown = [x for x in r.inputs if x not in known]
            if unknown:
                raise ValueError(f"a rota «{r.id}» aponta para entradas que não existem: {', '.join(unknown)}")
        return self


__all__ = ["ProfileChannels", "ChannelInput", "ChannelRoute", "RouteWhen", "RouteTarget",
           "ChannelCondition", "CaseJoin", "CaseReceipt", "ChannelsOutbound", "OutboundKind",
           "OUTBOUND_KINDS", "OUTBOUND_LANGUAGES", "CHANNEL_KINDS", "LIVE_CHANNELS", "MODULES",
           "ROUTE_FIELDS", "OPS_BY_KIND", "OPS", "ID_RE", "MAX_INPUTS", "MAX_ROUTES", "MAX_CONDITIONS",
           "JOIN_BY", "JOIN_WINDOW_DAYS_DEFAULT", "JOIN_WINDOW_DAYS_MAX", "FRONT_RE"]
