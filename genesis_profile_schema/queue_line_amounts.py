"""
genesis_profile_schema/queue_line_amounts.py — valor por linha CALCULADO de uma
fila (`reviewQueues.<fila>.lineAmounts`, v0.1.179, 25 Nov 2026).

O PRODUTOR do contrato é o genai-core:
  - `core/managers/review_queue_summaries.py` (`public_line_amounts`) valida a
    forma e passa-a ao fecore em `queue_options[<fila>].line_amounts`;
  - o fecore (`review-queue-line-amounts.ts`) calcula AO VIVO preço ×
    quantidade na coluna `target` de cada linha (o Guardar grava-a), lendo os
    números como o `price_number` do genesis-mcp lê na gravação.

PORQUE (Salmon, 25 Nov 2026): o preço de cada linha vem do ERP (PR00 do SAP,
ex.: 98,93 EUR por «1000 KG») e o operador pode mudá-lo; o valor da linha tem
de acompanhar a mudança no ecrã. Genérico: qualquer fila com linhas de preço.

O core larga uma entrada partida em silêncio (só aviso no log) e a fila
desenha-se sem ela; aqui as MESMAS regras recusam-na ao gravar, com a razão —
nunca cortar em silêncio. Limites iguais aos do core (5 entradas; nomes de
coluna `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, ASCII).

Forma de uma entrada:
    {
      "source": "artigos",          # array de linhas do payload
      "target": "preco",            # coluna que RECEBE o valor (só de leitura na /fila)
      "price": "preco_unitario",    # preço unitário
      "priceUnit": "preco_unidade", # unidade COM a base («1000 KG»)
      "quantity": "quantidade",
      "quantityUnit": "unidade",
      "weightTons": "toneladas"     # opcional: peso da linha em toneladas, para um
    }                               #   preço de massa sobre paletes/sacos
Regras entre entradas da MESMA tabela (`source`): o `target` não pode ser uma
coluna lida por nenhuma entrada (o cálculo de uma apagava a entrada de outra e
o resultado dependia da ordem) e não se repete. `target` interno (`_…`) não
existe: o padrão já o recusa (começa por letra ou algarismo).
"""

from __future__ import annotations

import re
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, field_validator

#: O mesmo padrão do core (`_KEY_RE` em review_queue_summaries.py), só ASCII.
_COL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", re.ASCII)
#: Teto de entradas do core (`_MAX_TABLES`): acima dele o core cortava sem dizer.
LINE_AMOUNTS_MAX = 5
_READ = ("price", "priceUnit", "quantity", "quantityUnit", "weightTons")


class ProfileQueueLineAmount(BaseModel):
    """Uma coluna calculada (preço × quantidade) nas linhas de `source`."""
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    price: str
    priceUnit: str
    quantity: str
    quantityUnit: str
    weightTons: Optional[str] = None

    @field_validator("source", "target", "price", "priceUnit", "quantity",
                     "quantityUnit", "weightTons")
    @classmethod
    def _col(cls, v, info):
        if v is None:
            return v
        s = v.strip() if isinstance(v, str) else v
        if not isinstance(s, str) or not _COL_RE.fullmatch(s):
            raise ValueError(
                f"lineAmounts.{info.field_name}: nome de coluna inválido — letras, "
                f"algarismos, «.», «_» ou «-», até 64, a começar por letra ou "
                f"algarismo")
        return s

    def read_columns(self) -> List[str]:
        return [getattr(self, k) for k in _READ if getattr(self, k)]


def _check_entries(v: List[ProfileQueueLineAmount]) -> List[ProfileQueueLineAmount]:
    if len(v) > LINE_AMOUNTS_MAX:
        raise ValueError(f"lineAmounts: no máximo {LINE_AMOUNTS_MAX} entradas "
                         f"(recebidas {len(v)})")
    lidas: dict[str, set[str]] = {}
    for e in v:
        lidas.setdefault(e.source, set()).update(e.read_columns())
    vistos: set[tuple[str, str]] = set()
    for e in v:
        if e.target in lidas[e.source]:
            raise ValueError(
                f"lineAmounts: o target «{e.target}» é uma coluna LIDA por uma "
                f"entrada da tabela «{e.source}» — escolher outra coluna para o "
                f"valor calculado")
        if (e.source, e.target) in vistos:
            raise ValueError(
                f"lineAmounts: o target «{e.target}» repete-se na tabela "
                f"«{e.source}»")
        vistos.add((e.source, e.target))
    return v


QueueLineAmounts = Annotated[List[ProfileQueueLineAmount], AfterValidator(_check_entries)]
