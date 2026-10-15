"""v0.1.119 (15 Out 2026, auditoria D3/D10) — interruptores do que vem junto
com o `create_ticket`: `status_lookup` (I19, `check_ticket_status`) e
`no_info_offer` (I20, chip «Quero abrir um pedido sobre isto»).

O que protege: None (ausente/null) é o comportamento de antes — os clientes que
já têm o create_ticket não mudam; `false`/`true` explícitos sobrevivem ao
round-trip (o `tools.config` grava-se byte-fiel, sem materializar a chave); os
valores não-booleanos são recusados pelo modelo tipado; e há texto nas duas
línguas."""
import pytest

from genesis_profile_schema import exposure as exp
from genesis_profile_schema.client_profile_schema import (
    ClientProfileSchema, ProfileToolCreateTicketConfig)
from genesis_profile_schema.ui_text import text_for

FIELDS = ("status_lookup", "no_info_offer")


def test_ausente_e_none():
    cfg = ProfileToolCreateTicketConfig()
    for f in FIELDS:
        assert getattr(cfg, f) is None


def test_bloco_antigo_nao_ganha_as_chaves_no_blob():
    """Um perfil antigo gravado de novo continua sem as chaves — o core lê
    ausente = ligado, como antes."""
    prof = ClientProfileSchema.model_validate(
        {"client_id": "x", "tools": {"enabled": ["create_ticket"],
                                     "config": {"create_ticket": {"queue": "t"}}}})
    blob = prof.to_blob_dict()["tools"]["config"]["create_ticket"]
    assert blob == {"queue": "t"}


@pytest.mark.parametrize("value", [True, False, None])
def test_round_trip_explicito(value):
    raw = {"queue": "t", "status_lookup": value, "no_info_offer": value}
    prof = ClientProfileSchema.model_validate(
        {"client_id": "x", "tools": {"config": {"create_ticket": raw}}})
    assert prof.to_blob_dict()["tools"]["config"]["create_ticket"] == raw


def test_valor_que_nao_e_booleano_e_recusado():
    with pytest.raises(Exception):
        ClientProfileSchema.model_validate(
            {"client_id": "x", "tools": {"config": {"create_ticket": {"status_lookup": "talvez"}}}})


def test_forma_e_textos():
    formas = exp.tool_config_shapes()
    for f in FIELDS:
        path = f"tools.config.create_ticket.{f}"
        assert path in formas
        for loc in ("pt-PT", "en-GB"):
            t = text_for(path, loc)
            assert t and t.get("label") and t.get("help") and len(t["help"]) <= 240
