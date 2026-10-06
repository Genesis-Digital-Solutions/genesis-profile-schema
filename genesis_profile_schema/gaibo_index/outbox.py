"""
A caixa de saída entre o GAIBO e o Studio (contrato v1).

Um contentor na storage do cliente. Ninguém se chama: cada lado escreve só os
seus ficheiros e lê os do outro.

    gaibo-outbox/
      settings.json              Studio  (limites, índice, embeddings)
      requests/<pedido>.json     GAIBO   (pedido de publicação, escrito UMA vez)
      results/<pedido>.json      Studio  (estado e resultado desse pedido)
      runs/<execução>.json       GAIBO   (relatório de cada indexação, UMA vez)

Escritas: um ficheiro novo com `If-None-Match: *` (nunca se reescreve um
pedido nem um relatório); o `results/` e o `settings.json` só com `If-Match`
do ETag lido. Quem lê um ficheiro que não valida contra o modelo trata-o como
inválido e di-lo — nunca o salta em silêncio.

O pedido diz O QUÊ (manifesto), não só QUANDO: o Studio publica exatamente as
entradas do pedido, e só se o dev ainda tiver, para cada uma, a mesma execução
(`origin_ref`) e o mesmo número de chunks. Uma entrada que não bata fica por
publicar com o motivo; nada é apagado de produção por estar ausente do dev.
As remoções são entradas explícitas.
"""

from __future__ import annotations

import re
from typing import List, Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .index_fields import CONTRACT_VERSION, is_gaibo_source

OUTBOX_CONTAINER = "gaibo-outbox"
SETTINGS_BLOB = "settings.json"
REQUESTS_PREFIX = "requests/"
RESULTS_PREFIX = "results/"
RUNS_PREFIX = "runs/"

_REQUEST_ID_RE = re.compile(r"^pr-[a-z0-9]{8,40}$")
_RUN_ID_RE = re.compile(r"^run-[a-z0-9]{8,40}$")
_ORIGIN_REF_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_EXT_RE = re.compile(r"^\.[a-z0-9]{1,8}$")

MAX_ITEMS_PER_REQUEST = 5000
MAX_CHUNKS_PER_DOCUMENT = 20000

_CLOSED = ConfigDict(extra="forbid")


def request_blob(request_id: str) -> str:
    if not _REQUEST_ID_RE.match(request_id or ""):
        raise ValueError("id de pedido inválido")
    return f"{REQUESTS_PREFIX}{request_id}.json"


def result_blob(request_id: str) -> str:
    if not _REQUEST_ID_RE.match(request_id or ""):
        raise ValueError("id de pedido inválido")
    return f"{RESULTS_PREFIX}{request_id}.json"


def run_blob(run_id: str) -> str:
    if not _RUN_ID_RE.match(run_id or ""):
        raise ValueError("id de execução inválido")
    return f"{RUNS_PREFIX}{run_id}.json"


# ── Limites e definições (escreve o Studio) ─────────────────────────────────

# Valores por omissão do tier (pricing de Out 2026, PROVISÓRIOS). Os efetivos de
# cada cliente estão no settings.json — o GAIBO nunca usa estes diretamente.
TIER_DEFAULTS = {
    "starter": {
        "enabled": True, "max_documents": 100, "max_total_mb": 50,
        "max_file_mb": 5, "allowed_extensions": [".pdf", ".docx", ".txt", ".md"],
    },
    "professional": {
        "enabled": True, "max_documents": 1000, "max_total_mb": 500,
        "max_file_mb": 25,
        "allowed_extensions": [".pdf", ".docx", ".txt", ".md", ".xlsx", ".pptx",
                               ".png", ".jpg", ".jpeg", ".tif", ".tiff"],
    },
    # Enterprise: a indexação é feita pela Genesis no Studio. Desligado por
    # omissão; a Genesis pode ligá-lo (sem limites de tier) se o contrato pedir.
    "enterprise": {
        "enabled": False, "max_documents": None, "max_total_mb": None,
        "max_file_mb": None, "allowed_extensions": [],
    },
}


class GaiboSettings(BaseModel):
    """`settings.json` — o que o GAIBO pode fazer neste cliente.

    Também diz em que índice escrever e com que modelo de embeddings: nos
    índices migrados da plataforma antiga não há sentinela `genesis_meta`, por
    isso o modelo não pode ser lido do índice.
    """

    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    enabled: bool = False
    auto_approve: bool = False
    tier: Optional[str] = Field(default=None, max_length=40)
    max_documents: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    max_total_mb: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    max_file_mb: Optional[int] = Field(default=None, ge=0, le=10_000)
    allowed_extensions: List[str] = Field(default_factory=list, max_length=40)
    search_service: str = Field(default="", max_length=128)
    dev_index: str = Field(default="", max_length=128)
    embedding_deployment: str = Field(default="", max_length=128)
    embedding_dimensions: Optional[int] = Field(default=None, ge=1, le=8192)
    # Muda sempre que o índice dev é recriado (mesmo com o mesmo nome e o mesmo
    # modelo): quando muda, o GAIBO volta a indexar a sua parte.
    dev_index_generation: str = Field(default="", max_length=128)
    updated_at: Optional[AwareDatetime] = None

    @field_validator("allowed_extensions")
    @classmethod
    def _exts(cls, value: List[str]) -> List[str]:
        out = []
        for ext in value:
            ext = (ext or "").strip().lower()
            if not _EXT_RE.match(ext):
                raise ValueError(f"extensão inválida: {ext!r}")
            if ext not in out:
                out.append(ext)
        return out


# ── Pedido de publicação (escreve o GAIBO) ──────────────────────────────────

class PublishItem(BaseModel):
    model_config = _CLOSED

    source_file: str = Field(max_length=300)
    action: Literal["publish", "remove"]
    # Execução que produziu os chunks que o cliente aprovou no dev.
    origin_ref: Optional[str] = None
    chunk_count: Optional[int] = Field(default=None, ge=1, le=MAX_CHUNKS_PER_DOCUMENT)

    @model_validator(mode="after")
    def _check(self) -> "PublishItem":
        if not is_gaibo_source(self.source_file):
            raise ValueError("source_file fora do formato gaibo/<chave>/<nome>")
        if self.action == "publish":
            if not self.origin_ref or not _ORIGIN_REF_RE.match(self.origin_ref):
                raise ValueError("publish exige origin_ref")
            if self.chunk_count is None:
                raise ValueError("publish exige chunk_count")
        elif self.origin_ref is not None or self.chunk_count is not None:
            raise ValueError("remove não leva origin_ref nem chunk_count")
        return self


class PublishRequest(BaseModel):
    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    request_id: str
    client_id: str = Field(min_length=1, max_length=80)
    requested_at: AwareDatetime
    # Referência opaca para o audit do GAIBO (nunca o email nem o nome).
    requested_by_ref: str = Field(min_length=1, max_length=128)
    items: List[PublishItem] = Field(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)

    @field_validator("request_id")
    @classmethod
    def _rid(cls, value: str) -> str:
        if not _REQUEST_ID_RE.match(value):
            raise ValueError("id de pedido inválido")
        return value

    @model_validator(mode="after")
    def _unique(self) -> "PublishRequest":
        seen = set()
        for item in self.items:
            if item.source_file in seen:
                raise ValueError(f"source_file repetido: {item.source_file}")
            seen.add(item.source_file)
        return self


# ── Resultado (escreve o Studio) ────────────────────────────────────────────

ItemOutcome = Literal[
    "published",     # copiado para produção tal como estava no dev
    "removed",       # apagado de produção
    "not_in_dev",    # o dev já não tem este documento
    "mismatch",      # o dev tem outra execução, outro número de chunks, ou o
                     # original já não é o que os chunks descrevem (doc_version)
    "invalid",       # chunks no dev que não cumprem o contrato
    "not_in_prod",   # remoção de algo que produção não tem (nada a fazer)
    "failed",        # erro ao copiar ou apagar (ver detail)
    "skipped",       # pedido recusado ou interrompido antes desta entrada
]


class PublishItemOutcome(BaseModel):
    model_config = _CLOSED

    source_file: str = Field(max_length=300)
    action: Literal["publish", "remove"]
    outcome: ItemOutcome
    origin_ref: Optional[str] = Field(default=None, max_length=64)
    chunks: int = Field(default=0, ge=0)
    detail: str = Field(default="", max_length=300)


class PublishResult(BaseModel):
    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    request_id: str
    # `publishing` = aprovado e já em execução (nunca volta a `approved`).
    status: Literal["pending_approval", "approved", "publishing", "refused",
                    "published", "partially_published", "failed", "invalid"]
    updated_at: AwareDatetime
    decided_at: Optional[AwareDatetime] = None
    reason: str = Field(default="", max_length=500)
    # Momento em que o Studio leu o dev para publicar (o "o quê" efetivo está
    # em cada item: origin_ref + chunks).
    dev_checked_at: Optional[AwareDatetime] = None
    published_at: Optional[AwareDatetime] = None
    items: List[PublishItemOutcome] = Field(default_factory=list,
                                            max_length=MAX_ITEMS_PER_REQUEST)


# ── Relatório de cada indexação (escreve o GAIBO) ───────────────────────────

class RunDocument(BaseModel):
    model_config = _CLOSED

    source_file: str = Field(max_length=300)
    action: Literal["indexed", "replaced", "deleted", "failed"]
    chunks: int = Field(default=0, ge=0)
    bytes: int = Field(default=0, ge=0)
    content_sha256: str = Field(default="", max_length=64)
    error: str = Field(default="", max_length=300)


class RunReport(BaseModel):
    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    run_id: str
    origin_ref: str = Field(min_length=1, max_length=64)
    started_at: AwareDatetime
    finished_at: Optional[AwareDatetime] = None
    status: Literal["succeeded", "partial", "failed"]
    documents: List[RunDocument] = Field(default_factory=list, max_length=MAX_ITEMS_PER_REQUEST)
    # Custo real, medido por execução (o Studio soma-o ao consumo do cliente).
    di_pages_read: int = Field(default=0, ge=0)
    di_pages_layout: int = Field(default=0, ge=0)
    enrichment_input_tokens: int = Field(default=0, ge=0)
    enrichment_output_tokens: int = Field(default=0, ge=0)
    embedding_tokens: int = Field(default=0, ge=0)
    enrichment_deployment: str = Field(default="", max_length=128)
    embedding_deployment: str = Field(default="", max_length=128)

    @field_validator("run_id")
    @classmethod
    def _run(cls, value: str) -> str:
        if not _RUN_ID_RE.match(value):
            raise ValueError("id de execução inválido")
        return value

    @field_validator("origin_ref")
    @classmethod
    def _ref(cls, value: str) -> str:
        if not _ORIGIN_REF_RE.match(value):
            raise ValueError("origin_ref inválido")
        return value
