"""
`channels.outbound` (v0.1.172, carril C2-mín do pack dos canais): um interruptor
por tipo de saída NOVO (D19). Desligado por omissão; o aviso de IA não é
configurável; `null` nunca se grava (um core com a v0.1.171 recusava o perfil).
"""

from typing import get_args

import pytest
from pydantic import ValidationError

from genesis_profile_schema import channels as C
from genesis_profile_schema.channels import OUTBOUND_KINDS, OUTBOUND_LANGUAGES, ChannelsOutbound, ProfileChannels
from genesis_profile_schema.client_profile_schema import ClientProfileSchema as ClientProfile
from genesis_profile_schema.exposure import exposure_of

ROTA = {"id": "r", "to": {"module": "queue", "queue": "fila"}}


def test_sem_saida_nao_se_grava_a_chave():
    """Um core com a v0.1.171 (`extra="forbid"`) recusava `"outbound": null` e,
    com ele, o save do perfil inteiro."""
    ch = ProfileChannels.model_validate({"routes": [ROTA]})
    assert ch.outbound is None
    assert "outbound" not in ch.model_dump(mode="json")
    blob = ClientProfile.model_validate({"channels": {"routes": [ROTA]}}).to_blob_dict()
    assert "outbound" not in blob["channels"]


def test_tipo_declarado_nasce_desligado_e_na_lingua_da_pessoa():
    out = ChannelsOutbound.model_validate({"kinds": [{"kind": "routine.report"}]})
    assert out.kinds[0].enabled is False
    assert out.kinds[0].language == "person"


def test_forma_completa_volta_a_validar_igual():
    raw = {"routes": [ROTA], "outbound": {"kinds": [
        {"kind": "contact.ask", "enabled": True, "language": "person"},
        {"kind": "document.deliver", "enabled": True, "language": "front"}]}}
    ch = ProfileChannels.model_validate(raw)
    dump = ch.model_dump(mode="json")
    assert dump["outbound"]["kinds"][1] == {"kind": "document.deliver", "enabled": True, "language": "front"}
    assert ProfileChannels.model_validate(dump) == ch
    blob = ClientProfile.model_validate({"channels": raw}).to_blob_dict()
    assert blob["channels"]["outbound"]["kinds"][0]["kind"] == "contact.ask"


@pytest.mark.parametrize("bad", [
    {"kinds": [{"kind": "capture_notice"}]},                     # emissor de hoje: não passa por aqui (D19)
    {"kinds": [{"kind": "contact.ask"}, {"kind": "contact.ask"}]},
    {"kinds": [{"kind": "contact.ask", "language": "pt"}]},
    {"kinds": [{"kind": "contact.ask", "ai_notice": False}]},    # o aviso de IA não se desliga
    {"kinds": [{"kind": "contact.ask", "enabled": "sim"}]},
    {"kinds": [{"kind": "contact.ask", "enabled": "true"}]},        # interruptor estrito
    {"kinds": [{"kind": "contact.ask", "enabled": 1}]},
    {"kinds": [{}]},
    {"kinds": [], "extra": 1},
])
def test_formas_invalidas(bad):
    with pytest.raises(ValidationError):
        ChannelsOutbound.model_validate(bad)


def test_listas_fechadas_publicadas():
    assert OUTBOUND_KINDS == ("contact.ask", "contact.tell", "document.deliver", "routine.report")
    assert OUTBOUND_LANGUAGES == ("person", "front")
    # As constantes e os tipos não derivam um do outro.
    assert set(get_args(C.OutboundKindName)) == set(OUTBOUND_KINDS)
    assert set(get_args(C.OutboundLanguage)) == set(OUTBOUND_LANGUAGES)


def test_saida_vazia_tambem_nao_se_grava():
    ch = ProfileChannels.model_validate({"routes": [ROTA], "outbound": {"kinds": []}})
    assert "outbound" not in ch.model_dump(mode="json")


def test_a_saida_e_da_genesis():
    for path in ("channels.outbound.kinds.kind", "channels.outbound.kinds.enabled",
                 "channels.outbound.kinds.language"):
        assert exposure_of(path) == "internal"
