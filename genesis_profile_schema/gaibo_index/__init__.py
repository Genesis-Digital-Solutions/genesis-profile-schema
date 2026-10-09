"""
genesis_profile_schema/gaibo_index — CONTRATO da indexação pelo GAIBO
(v0.1.92, 6 Out 2026; resposta ao BACKLOG gaibo 3.1302).

O GAIBO indexa os documentos que o cliente carrega no índice DEV do cliente
(o mesmo que o Studio enche), e só o Studio publica em produção, a pedido do
GAIBO e com aprovação da Genesis. Os dois lados nunca se chamam: falam por uma
caixa de saída na storage do cliente.

Este pacote é a ÚNICA fonte das regras partilhadas — o GAIBO usa-o para
escrever, o Studio para proteger as suas rotinas e para validar o que publica,
o core para mostrar as fontes. Uma regra que só exista de um lado não protege.

- `index_fields` — como é um chunk do GAIBO no índice (campos, ids, origem,
  nomes, o JSON `metadata` que o core lê) e `chunk_problems()`.
- `outbox` — a caixa de saída: contentores, caminhos e os modelos dos pedidos
  de publicação, resultados, limites e relatórios de indexação.

Documento legível: `docs/contrato-indexacao-gaibo.md`.
"""

from .index_fields import (
    CHUNK_ID_PREFIX,
    CHUNKING,
    CONTRACT_VERSION,
    DI_MODELS,
    EXTRACTION_BY_EXTENSION,
    FORBIDDEN_CONTENT_TYPES,
    FORBIDDEN_IDS,
    GAIBO_WRITABLE_FIELDS,
    ORIGIN_FIELD,
    ORIGIN_GAIBO,
    ORIGIN_REF_FIELD,
    REQUIRED_METADATA_KEYS,
    SOURCE_PREFIX,
    SOURCES_CONTAINER,
    chunk_id,
    chunk_problems,
    display_name,
    extraction_for,
    file_name_problems,
    is_gaibo_source,
    is_valid_doc_key,
    parent_doc_id,
    parse_source_file,
    source_file_for,
)
from .outbox import (
    SETTINGS_BLOB,
    OUTBOX_CONTAINER,
    REQUESTS_PREFIX,
    RESULTS_PREFIX,
    RUNS_PREFIX,
    TIER_DEFAULTS,
    GaiboSettings,
    PublishItem,
    PublishItemOutcome,
    PublishRequest,
    PublishResult,
    RunDocument,
    RunReport,
    request_blob,
    result_blob,
    run_blob,
)

__all__ = [
    "CHUNK_ID_PREFIX", "CHUNKING", "CONTRACT_VERSION", "DI_MODELS", "EXTRACTION_BY_EXTENSION",
    "FORBIDDEN_CONTENT_TYPES", "FORBIDDEN_IDS", "GAIBO_WRITABLE_FIELDS",
    "ORIGIN_FIELD", "ORIGIN_GAIBO", "ORIGIN_REF_FIELD", "REQUIRED_METADATA_KEYS",
    "SOURCE_PREFIX", "SOURCES_CONTAINER", "chunk_id", "chunk_problems",
    "display_name", "extraction_for", "file_name_problems", "is_gaibo_source", "is_valid_doc_key",
    "parent_doc_id", "parse_source_file", "source_file_for",
    "SETTINGS_BLOB", "OUTBOX_CONTAINER", "REQUESTS_PREFIX", "RESULTS_PREFIX",
    "RUNS_PREFIX", "TIER_DEFAULTS", "GaiboSettings", "PublishItem",
    "PublishItemOutcome", "PublishRequest", "PublishResult", "RunDocument",
    "RunReport", "request_blob", "result_blob", "run_blob",
]
