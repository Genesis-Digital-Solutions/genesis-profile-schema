"""tests/test_queue_fields.py — `reviewQueues.<fila>.fields` tipado (v0.1.98)."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ClientProfileSchema, ProfileReviewQueue
from genesis_profile_schema.queue_fields import MAX_QUEUE_FIELDS


def _f(key, **kw):
    return {"key": key, "label": {"pt": key.upper(), "en": key}, **kw}


def test_fila_sem_fields_fica_como_antes():
    assert ProfileReviewQueue().fields is None
    assert ProfileReviewQueue(label="Encomendas").model_dump(exclude_none=True).get("fields") is None


def test_campos_tipados_com_tabela_moeda_e_escolha():
    q = ProfileReviewQueue(fields=[
        _f("nif", required=True, order=1, group="Cliente"),
        _f("total", type="money", currencies=["EUR"], min=0),
        _f("estado_pagamento", type="select", options=[{"value": "pago", "label": {"pt": "Pago"}}]),
        _f("items", type="table", columns=[{"key": "ref", "label": {"pt": "Ref."}},
                                            {"key": "qtd", "label": {"pt": "Qtd."}, "type": "number"}]),
        _f("_interno", hidden=True) if False else _f("nota", editable=False),
    ])
    assert [f.key for f in q.fields] == ["nif", "total", "estado_pagamento", "items", "nota"]


@pytest.mark.parametrize("fields", [
    [_f("a"), _f("a")],                                   # chave repetida
    [_f("a", foo=1)],                                     # chave inventada
    [{"name": "a"}],                                      # forma livre antiga
    [_f("_a")],                                           # chave interna do payload
    [_f("a", type="select")],                             # escolha sem opções
    [_f("a", type="html")],                               # tipo fora da allowlist
    [_f("a", label={"pt": "<script>x</script>" * 500})],  # rótulo acima do tecto
])
def test_recusas(fields):
    with pytest.raises(ValidationError):
        ProfileReviewQueue(fields=fields)


def test_tecto_de_campos():
    with pytest.raises(ValidationError):
        ProfileReviewQueue(fields=[_f(f"c{i}") for i in range(MAX_QUEUE_FIELDS + 1)])


def test_perfil_completo_valida_com_fields():
    p = ClientProfileSchema.model_validate({"reviewQueues": {"faturas": {"label": "Faturas", "fields": [_f("nif")]}}})
    assert p.reviewQueues["faturas"].fields[0].key == "nif"
