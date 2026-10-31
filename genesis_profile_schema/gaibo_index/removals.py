"""
Documentos do GAIBO apagados pela Genesis no Studio (v0.1.138, 31 Out 2026).

O GAIBO não pode apagar o que o Studio indexou; a Genesis, no Studio, pode apagar
o que o GAIBO indexou (decisão do Bruno, 31 Out 2026) — em dev E em produção,
pelo Gerir Índice desse ambiente. Como os dois nunca se chamam, o Studio deixa um
AVISO na caixa de saída do dev, e o GAIBO acerta o seu registo:

    gaibo-outbox/
      genesis-removals/<aviso>.json   Studio  (escrito UMA vez, If-None-Match: *)

O GAIBO só LÊ este prefixo (a condição ABAC da identidade da API só deixa
escrever em `requests/`, `runs/` e `invites/`). Por aviso:

  * `environment="dev"` — os chunks e o original do documento saíram do índice
    dev e de `gaibo-sources`: o GAIBO marca o documento como removido pela
    Genesis e deixa de o contar na capacidade (`max_documents`, `max_total_mb`).
    O limite MENSAL não devolve nada (o que foi indexado no mês, foi);
  * `environment="prod"` — só a versão PUBLICADA saiu (chunks e original de
    produção); o dev fica como estava. O GAIBO passa a mostrá-lo como «não
    publicado».

Um aviso vale pelo `source_file` E pelo `origin_ref` que lá estava quando o
Studio apagou: se o GAIBO já tiver uma execução mais nova desse documento
(outro `origin_ref`), o aviso não a apaga do registo — diz-se e segue.
Idempotente: o GAIBO guarda os `notice_id` já tratados. O Studio nunca apaga
avisos (ficam como histórico) e nunca reescreve um.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .index_fields import CONTRACT_VERSION, is_gaibo_source
from .outbox import is_valid_origin_ref

REMOVALS_PREFIX = "genesis-removals/"

_NOTICE_ID_RE = re.compile(r"^gr-[a-z0-9]{8,40}$")
_CLOSED = ConfigDict(extra="forbid")


def is_valid_notice_id(value: Any) -> bool:
    """`gr-` + 8 a 40 de [a-z0-9]."""
    return isinstance(value, str) and bool(_NOTICE_ID_RE.match(value))


def removal_blob(notice_id: str) -> str:
    if not _NOTICE_ID_RE.match(notice_id or ""):
        raise ValueError("id de aviso inválido")
    return f"{REMOVALS_PREFIX}{notice_id}.json"


class GenesisRemovalNotice(BaseModel):
    """Um documento do GAIBO apagado pela Genesis num ambiente (escreve o Studio)."""
    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    notice_id: str
    #: o id do cliente de DEV no Studio (`<projeto>-dev`), o mesmo do `PublishRequest`
    client_id: str = Field(min_length=1, max_length=80)
    environment: Literal["dev", "prod"]
    #: a identidade completa do documento (`gaibo/<chave>/<nome>`)
    source_file: str = Field(min_length=1, max_length=400)
    #: a execução que estava no índice quando se apagou; None = não se leu
    origin_ref: Optional[str] = None
    removed_chunks: int = Field(ge=0)
    #: o original em `gaibo-sources` desse ambiente também saiu
    original_removed: bool
    removed_at: AwareDatetime
    #: motivo opcional, para o cliente ver («a pedido do cliente», «conteúdo errado»…)
    reason: str = Field(default="", max_length=300)

    @field_validator("notice_id")
    @classmethod
    def _nid(cls, value: str) -> str:
        if not _NOTICE_ID_RE.match(value):
            raise ValueError("id de aviso inválido")
        return value

    @field_validator("source_file")
    @classmethod
    def _source(cls, value: str) -> str:
        if not is_gaibo_source(value):
            raise ValueError("source_file não é de um documento do GAIBO")
        return value

    @field_validator("origin_ref")
    @classmethod
    def _ref(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not is_valid_origin_ref(value):
            raise ValueError("origin_ref inválido")
        return value
