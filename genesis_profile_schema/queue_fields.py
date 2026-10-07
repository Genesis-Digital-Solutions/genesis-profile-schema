"""
genesis_profile_schema/queue_fields.py — os campos do detalhe de um pedido da fila
(`reviewQueues.<fila>.fields`, v0.1.98; épico Plataforma de módulos §3).

Até à v0.1.97 era `List[Dict[str, Any]]` sem regras, e nenhum ecrã o lia. Passa a
ser uma lista da definição de campo ÚNICA do produto (`field_definition.py`): a
mesma do Intake, do cabeçalho de um caso e dos formulários do chat.

O que cada campo diz ao detalhe do pedido (fecore `/fila`):
  - `key`: a chave no `payload` do pedido (ex.: `nif`, `total`, `items`);
  - `label`/`help`: o rótulo por língua, em vez do nome técnico da chave;
  - `type`, `options`, `columns`, `currencies`, `min`/`max`: como se desenha e
    como o core valida o valor que o operador grava;
  - `order`/`group`: a ordem e os grupos no ecrã;
  - `editable=False`: mostra-se mas o operador não muda; `hidden=True`: não se mostra;
  - `required`: o core recusa gravar o pedido com esse campo vazio.

Compatibilidade: uma fila SEM `fields` fica exatamente como antes (o detalhe mostra
as chaves do payload com o nome técnico). Com `fields`, as chaves do payload que
não estão declaradas continuam a aparecer no fim, como hoje.
"""

from __future__ import annotations

from typing import Annotated, List

from pydantic import AfterValidator, Field

from .field_definition import FieldDefinition

MAX_QUEUE_FIELDS = 200


def _unique_keys(value: List[FieldDefinition]) -> List[FieldDefinition]:
    keys = [f.key for f in value]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        raise ValueError(f"campos da fila repetidos: {', '.join(dup[:5])}")
    return value


QueueFields = Annotated[
    List[FieldDefinition],
    Field(max_length=MAX_QUEUE_FIELDS),
    AfterValidator(_unique_keys),
]

__all__ = ["MAX_QUEUE_FIELDS", "QueueFields"]
