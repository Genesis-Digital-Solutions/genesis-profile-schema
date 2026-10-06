"""
Como é um chunk do GAIBO no índice DEV do cliente (contrato v1).

Tudo o que aqui está foi medido no produtor do outro lado, a 6 Out 2026:
- o Studio escreve os chunks em `DocIndexer._index_semantic_chunks` e o JSON
  `metadata` em `_build_chunk_metadata` (backend/azure_infra/indexer.py);
- o core lê os metadados de um resultado SÓ do JSON `metadata`
  (langchain-community 0.4.2, `azuresearch.py`): os campos de topo
  `source_file`/`url`/`document_title` são ignorados no caminho principal, e um
  `metadata` nulo ou inválido rebenta a pesquisa desse índice;
- o core agrupa as citações por `metadata.source` e filtra por
  `source_file eq '<metadata.source>'` — por isso os dois têm de ser iguais.

O prefixo `gaibo/<chave>/` separa os documentos do GAIBO dos do Studio em tudo
o que compara por igualdade (citações, substituição e remoção por fonte,
vizinhos). A chave é base32 em minúsculas (sem 0, 1, 8 e 9): nunca contém uma
sequência que pareça um ano (19xx/20xx), que o core e o modelo leem nos
caminhos.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

CONTRACT_VERSION = 1

ORIGIN_FIELD = "origin"
ORIGIN_REF_FIELD = "origin_ref"
ORIGIN_GAIBO = "gaibo"

SOURCE_PREFIX = "gaibo/"
CHUNK_ID_PREFIX = "gaibo_"

# Contentor dos ORIGINAIS na storage do cliente (a mesma conta do core, para o
# core conseguir assinar o link da fonte). Nunca o `input` do Studio: as
# reindexações agendadas apanhá-los-iam uma segunda vez.
SOURCES_CONTAINER = "gaibo-sources"

# Chave estável de UM documento do GAIBO: substituir o ficheiro com o MESMO
# nome mantém o `source_file` e, por isso, os mesmos ids (as correções que
# apontam para eles não partem). Os ids derivam do `source_file` completo:
# mudar o nome é uma identidade nova (remove + publish).
# `j-` + base32 minúsculo sem 0/1/8/9.
_DOC_KEY_RE = re.compile(r"^j-[a-z2-7]{8,26}$")
_ORIGIN_REF_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FILE_NAME_MAX = 200
# `%` fica de fora: o fecore descodifica nomes de URL sem rede de segurança.
_FILE_NAME_BAD = re.compile(r"[/\\%\x00-\x1f\x7f]")

# Chaves que o JSON `metadata` TEM de ter (as que o Studio escreve e o core lê).
# `doc_version` de um chunk do GAIBO = sha256 (hex) dos bytes do original: a
# publicação confirma que o original copiado para produção é o que os chunks
# descrevem.
_DOC_VERSION_RE = re.compile(r"^[0-9a-f]{64}$")

REQUIRED_METADATA_KEYS = (
    "source", "page", "url", "document_title", "document_type",
    "parent_doc_id", "global_chunk_index", ORIGIN_FIELD,
)

# Campos de topo que o GAIBO pode escrever. Os restantes são do Studio
# (visão, categorias por pasta, linhagem de migração) ou não existem.
GAIBO_WRITABLE_FIELDS = frozenset({
    "id", "content", "enriched_content", "content_vector", "metadata",
    "source_file", "page", "page_end", "document_title", "document_type",
    "url", "section", "section_title", "content_type", "chunk_index",
    "global_chunk_index", "parent_doc_id", "page_in_pdf", "indexed_at",
    "doc_version", "source_last_modified", ORIGIN_FIELD, ORIGIN_REF_FIELD,
})

# Catálogos de datasets mandam o core para tabelas MCP que o GAIBO não tem.
FORBIDDEN_CONTENT_TYPES = frozenset({"dataset_catalog", "dataset_vocabulario"})
# A sentinela do índice (modelo de embeddings) é do Studio.
FORBIDDEN_IDS = frozenset({"genesis_meta", "__meta__"})

# Os mesmos números do Studio (indexer.py: CHUNK_SIZE/CHUNK_OVERLAP e
# CHUNK_SIZE_TABLE; tabela acima do teto parte com sobreposição de 300 e
# repete o cabeçalho em cada pedaço). Tokens, não caracteres.
CHUNKING = {
    "text_tokens": 512,
    "text_overlap_tokens": 100,
    "table_max_tokens": 2000,
    "table_overlap_tokens": 300,
    "table_repeat_header": True,
}

# Extração por tipo (desenho de 3 Out 2026). O Layout compensa a falta de
# Vision nas tabelas; custa mais por página do que o Read.
EXTRACTION_BY_EXTENSION = {
    ".pdf": "prebuilt-layout", ".pptx": "prebuilt-layout",
    ".xlsx": "prebuilt-layout", ".png": "prebuilt-layout",
    ".jpg": "prebuilt-layout", ".jpeg": "prebuilt-layout",
    ".tif": "prebuilt-layout", ".tiff": "prebuilt-layout",
    ".docx": "prebuilt-read",
    ".txt": "text", ".md": "text",
}

_PAGE_FRAGMENT_RE = re.compile(r"^page=\d{1,6}$")


def is_valid_doc_key(value: Any) -> bool:
    return isinstance(value, str) and bool(_DOC_KEY_RE.match(value))


def file_name_problems(name: Any) -> List[str]:
    """Problemas do nome ORIGINAL do ficheiro (lista vazia = aceite)."""
    if not isinstance(name, str) or not name.strip():
        return ["nome vazio"]
    out = []
    if name != name.strip():
        out.append("espaços no início ou no fim")
    if len(name) > FILE_NAME_MAX:
        out.append(f"mais de {FILE_NAME_MAX} caracteres")
    if _FILE_NAME_BAD.search(name):
        out.append("caracteres proibidos (/ \\ % ou de controlo)")
    if name in (".", "..") or name.endswith("."):
        out.append("nome reservado ou a acabar em ponto")
    # Invisíveis e de direção (U+202E fingia a extensão na citação), controlos
    # C1 e separadores de linha: nada disto se mostra ao utilizador.
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in name):
        out.append("caracteres invisíveis ou de controlo")
    if unicodedata.normalize("NFC", name) != name:
        out.append("nome não está em Unicode NFC")
    return out


def source_file_for(doc_key: str, file_name: str) -> str:
    """`gaibo/<chave>/<nome>` — o valor de `source_file` E de `metadata.source`."""
    if not is_valid_doc_key(doc_key):
        raise ValueError("chave de documento inválida")
    problems = file_name_problems(file_name)
    if problems:
        raise ValueError("nome de ficheiro inválido: " + "; ".join(problems))
    return f"{SOURCE_PREFIX}{doc_key}/{file_name}"


def parse_source_file(value: Any) -> Optional[Tuple[str, str]]:
    """(chave, nome) de um `source_file` do GAIBO; None se não for um."""
    if not isinstance(value, str) or not value.startswith(SOURCE_PREFIX):
        return None
    rest = value[len(SOURCE_PREFIX):]
    key, sep, name = rest.partition("/")
    if not sep or not is_valid_doc_key(key) or file_name_problems(name):
        return None
    return key, name


def is_gaibo_source(value: Any) -> bool:
    return parse_source_file(value) is not None


def display_name(source: Any) -> Any:
    """Nome a mostrar (ao modelo e ao utilizador) — sem a chave interna."""
    parsed = parse_source_file(source)
    return parsed[1] if parsed else source


def chunk_id(source_file: str, page: int, chunk_index: Any) -> str:
    """Id do chunk: a fórmula do Studio com o prefixo do GAIBO."""
    raw = f"{source_file}_{page}_{chunk_index}".encode("utf-8")
    return CHUNK_ID_PREFIX + hashlib.md5(raw).hexdigest()


def parent_doc_id(source_file: str) -> str:
    """Igual ao `_make_parent_doc_id` do Studio (o prefixo já o separa)."""
    return "doc_" + hashlib.md5(source_file.encode("utf-8")).hexdigest()[:16]


def _url_problems(url: Any) -> List[str]:
    if not isinstance(url, str) or not url:
        return ["url vazio"]
    parts = urlsplit(url)
    out = []
    if parts.scheme != "https" or not parts.netloc.lower().endswith(".blob.core.windows.net"):
        out.append("url tem de ser https numa conta de blob storage")
    if parts.query:
        out.append("url com query (nunca SAS: quem assina é o core)")
    if parts.fragment and not _PAGE_FRAGMENT_RE.match(parts.fragment):
        out.append("fragmento do url só pode ser #page=N")
    segments = parts.path.lstrip("/").split("/")
    if segments[0] != SOURCES_CONTAINER:
        out.append(f"url fora do contentor {SOURCES_CONTAINER}")
    if any(unquote(seg) in (".", "..") or "\\" in unquote(seg) for seg in segments[1:]):
        out.append("url com segmentos . ou .. ou \\")
    return out


def chunk_problems(doc: Dict[str, Any]) -> List[str]:
    """Valida um documento do índice escrito pelo GAIBO (vazio = conforme).

    O GAIBO corre-a antes de enviar; o Studio volta a corrê-la sobre o que
    está no dev antes de publicar (o que não passa não vai para produção).
    """
    if not isinstance(doc, dict):
        return ["não é um objeto"]
    out: List[str] = []
    extra = sorted(set(doc) - GAIBO_WRITABLE_FIELDS)
    if extra:
        out.append("campos não permitidos: " + ", ".join(extra))
    if doc.get(ORIGIN_FIELD) != ORIGIN_GAIBO:
        out.append(f"{ORIGIN_FIELD} tem de ser '{ORIGIN_GAIBO}'")
    ref = doc.get(ORIGIN_REF_FIELD)
    if not isinstance(ref, str) or not _ORIGIN_REF_RE.match(ref):
        out.append(f"{ORIGIN_REF_FIELD} inválido")
    source = doc.get("source_file")
    if not is_gaibo_source(source):
        out.append("source_file fora do formato gaibo/<chave>/<nome>")
    did = doc.get("id")
    if not isinstance(did, str) or did in FORBIDDEN_IDS or not did.startswith(CHUNK_ID_PREFIX):
        out.append(f"id tem de começar por {CHUNK_ID_PREFIX}")
    ctype = doc.get("content_type")
    if ctype is not None and (not isinstance(ctype, str) or ctype in FORBIDDEN_CONTENT_TYPES):
        out.append("content_type inválido ou reservado aos catálogos de datasets")
    # O core expande aos vizinhos filtrando pelos campos de TOPO.
    for key in ("page", "global_chunk_index"):
        val = doc.get(key)
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            out.append(f"{key} de topo obrigatório (inteiro ≥ 0)")
    dv = doc.get("doc_version")
    if not isinstance(dv, str) or not _DOC_VERSION_RE.match(dv):
        out.append("doc_version obrigatório: sha256 (hex minúsculo) do original")
    title = doc.get("document_title")
    if not isinstance(title, str) or len(title.strip()) < 3:
        out.append("document_title obrigatório")
    out.extend(_url_problems(doc.get("url")))

    raw = doc.get("metadata")
    try:
        meta = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        meta = None
    if not isinstance(meta, dict):
        out.append("metadata tem de ser JSON de um objeto")
        return out
    missing = [k for k in REQUIRED_METADATA_KEYS if k not in meta]
    if missing:
        out.append("metadata sem: " + ", ".join(missing))
    if "tier" in meta:
        out.append("metadata.tier não é permitido (passava à frente do Studio)")
    for key, top in (("source", "source_file"), ("url", "url"),
                     ("document_title", "document_title"),
                     ("parent_doc_id", "parent_doc_id"),
                     ("global_chunk_index", "global_chunk_index"),
                     ("page", "page"), ("document_type", "document_type"),
                     (ORIGIN_FIELD, ORIGIN_FIELD)):
        if key in meta and top in doc and meta[key] != doc[top]:
            out.append(f"metadata.{key} diferente de {top}")
    if isinstance(source, str) and doc.get("parent_doc_id") != parent_doc_id(source):
        out.append("parent_doc_id não é o derivado do source_file")
    return out
