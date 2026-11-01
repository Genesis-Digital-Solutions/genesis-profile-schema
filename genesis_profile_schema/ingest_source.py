"""
genesis_profile_schema/ingest_source.py — a FORMA de uma fonte de ingestão de email
(`ingest.sources[i]`), tal como o genai-core a lê (31 Out 2026; inventário feito no código do core,
`ingest/` + `core/managers/queue_sla.py`, `review_queue_*`).

PORQUÊ À PARTE
──────────────
`ProfileIngest.sources` continua `List[Dict[str, Any]]`: este modelo NÃO entra na validação do
perfil. Tipar a validação de uma vez arriscava recusar o save de perfis de produção com valores
antigos (ex.: `numbers_rule: true`, `reconcile` em dict). Aqui fica a forma — para o percurso de
configuração (`module_guides/ingest.json`, cobertura: toda a chave lida pelo core tem passo), para
o ecrã e para quem escreve a fonte. Passar a validar é uma decisão à parte, com a frota medida.

Tudo opcional com `None` por omissão: os valores por omissão são os do CORE, não deste modelo —
cada campo diz qual é. `extra="allow"` em todo o lado (o editor preserva chaves que não conhece).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

_OPEN = ConfigDict(extra="allow", populate_by_name=True)


class IngestImap(BaseModel):
    model_config = _OPEN
    folder: Optional[str] = None                 # omissão do core: «INBOX» (só leitura)


class IngestIgnore(BaseModel):
    model_config = _OPEN
    senders: Optional[List[str]] = None          # endereços exatos
    domains: Optional[List[str]] = None
    subject_patterns: Optional[List[str]] = None  # expressões regulares


class IngestAcceptRule(BaseModel):
    model_config = _OPEN
    # Onde procurar: from, to, cc, subject, body, attachment_name, attachment_content.
    in_: Optional[List[str]] = Field(default=None, alias="in")
    contains: Optional[List[str]] = None


class IngestAccept(BaseModel):
    model_config = _OPEN
    rules: Optional[List[IngestAcceptRule]] = None
    ocr: Optional[bool] = None                    # OCR pago só para filtrar pelo conteúdo dos anexos


class IngestTriage(BaseModel):
    model_config = _OPEN
    urgency: Optional[List[str]] = None           # lista fechada (máx. 50 × 60 caracteres)
    departments: Optional[List[str]] = None


class IngestClassifier(BaseModel):
    model_config = _OPEN
    labels: Optional[List[str]] = None            # omissão: encomenda, retificacao, ignorar
    labels_process: Optional[List[str]] = None    # omissão: encomenda, retificacao
    hints: Optional[str] = None
    triage: Optional[IngestTriage] = None


class IngestRoute(BaseModel):
    model_config = _OPEN
    label: Optional[str] = None
    queue: Optional[str] = None


class IngestSchemaField(BaseModel):
    model_config = _OPEN
    key: Optional[str] = None
    hint: Optional[str] = None


class IngestExtractionSchema(BaseModel):
    model_config = _OPEN
    header: Optional[List[IngestSchemaField]] = None
    artigos: Optional[List[IngestSchemaField]] = None


class IngestAttachments(BaseModel):
    model_config = _OPEN
    enabled: Optional[bool] = None                # omissão do core: desligado
    allowed: Optional[List[str]] = None           # omissão: pdf, docx, txt, png, jpg, jpeg, tif, tiff
    max_files: Optional[int] = None               # omissão: 5
    max_chars_per_file: Optional[int] = None      # omissão: 30000 (só para cima)
    ocr: Optional[Literal["off", "auto", "always"]] = None   # omissão: auto
    ocr_incomplete: Optional[bool] = None
    vision: Optional[Literal["off", "auto"]] = None          # omissão: off
    vision_max_pages: Optional[int] = None        # 1–10, omissão 3
    vision_dpi: Optional[int] = None              # ≥ 72, omissão 200


class IngestExtraction(BaseModel):
    model_config = _OPEN
    # `schema` no perfil (o nome choca com o `BaseModel.schema` do pydantic).
    schema_: Optional[IngestExtractionSchema] = Field(default=None, alias="schema")
    prompt: Optional[str] = None
    deployment: Optional[str] = None              # vazio = o modelo do agente
    ensure_fields: Optional[List[str]] = None
    required_fields: Optional[List[str]] = None
    numbers_rule: Optional[Union[bool, Literal["verbatim"]]] = None
    reconcile: Optional[Union[bool, Dict[str, Any]]] = None
    derive: Optional[Dict[str, Dict[str, Any]]] = None
    split_by: Optional[Dict[str, Any]] = None
    split_attachments: Optional[bool] = None
    attachments: Optional[IngestAttachments] = None


class IngestArchive(BaseModel):
    model_config = _OPEN
    enabled: Optional[bool] = None                # omissão do core: desligado
    include_eml: Optional[bool] = None            # só `false` desliga
    include_attachments: Optional[bool] = None
    allowed: Optional[List[str]] = None           # omissão: a lista da extração
    container: Optional[str] = None


class IngestAgentReply(BaseModel):
    model_config = _OPEN
    enabled: Optional[bool] = None
    mode: Optional[Literal["draft", "auto"]] = None


class IngestReply(BaseModel):
    model_config = _OPEN
    enabled: Optional[bool] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    channel: Optional[Literal["", "graph", "acs"]] = None    # vazio = ACS
    agent: Optional[IngestAgentReply] = None


class IngestPostProcess(BaseModel):
    model_config = _OPEN
    move_to_folder: Optional[str] = None
    move_ignored: Optional[bool] = None
    move_failed_to_folder: Optional[str] = None


class IngestLearn(BaseModel):
    model_config = _OPEN
    enabled: Optional[bool] = None
    domains: Optional[bool] = None
    ttl_days: Optional[int] = None                # 1–3650, omissão 365


class IngestResolver(BaseModel):
    model_config = _OPEN
    learn_from_operator: Optional[IngestLearn] = None


class IngestSource(BaseModel):
    """Uma fonte de `ingest.sources` — as 20 chaves de topo que o core lê."""
    model_config = _OPEN

    id: Optional[str] = None                      # obrigatório no core (IMAP: ^[A-Za-z0-9-]{1,64}$)
    enabled: Optional[bool] = None                # ausente = ligada; só `false` desliga
    mailbox: Optional[str] = None                 # obrigatório no core
    queue: Optional[str] = None                   # omissão: = id
    variant_slug: Optional[str] = None            # vazio = o perfil principal
    transport: Optional[str] = None               # vazio = Microsoft 365 (Graph); «imap»
    imap: Optional[IngestImap] = None
    lookback_hours: Optional[int] = None
    max_body_chars: Optional[int] = None          # omissão 20000 (nunca abaixo)
    ignore: Optional[IngestIgnore] = None
    accept: Optional[IngestAccept] = None
    classifier: Optional[IngestClassifier] = None
    routes: Optional[List[IngestRoute]] = None
    triage_queue: Optional[str] = None
    triage_min_confidence: Optional[float] = None  # 0–1, omissão 0.6
    extraction: Optional[IngestExtraction] = None
    archive: Optional[IngestArchive] = None
    reply: Optional[IngestReply] = None
    post_process: Optional[IngestPostProcess] = None
    resolver: Optional[IngestResolver] = None


__all__ = ["IngestSource"]
