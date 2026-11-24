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


# ── v0.1.174 (passo 6 do épico): a política de contacto do agente ─────────────────────────────────

def test_politica_de_contacto_valida_e_regrava():
    raw = {"kinds": [{"kind": "contact.ask", "enabled": True}],
           "contact": {"hours": {"start": "08:30", "end": "18:00", "business_days_only": False},
                       "answer_max_hours": 48}}
    out = ChannelsOutbound.model_validate(raw)
    assert out.contact.answer_max_hours == 48 and out.contact.hours.start == "08:30"
    dumped = out.model_dump(mode="json")
    assert dumped["contact"] == raw["contact"]
    assert ChannelsOutbound.model_validate(dumped).model_dump(mode="json") == dumped


def test_sem_politica_nada_novo_se_grava():
    """Um core com a v0.1.173 (`extra="forbid"`) recusava as chaves novas, mesmo nulas."""
    dumped = ChannelsOutbound.model_validate({"kinds": [{"kind": "contact.ask"}]}).model_dump(mode="json")
    assert "contact" not in dumped
    only_deadline = ChannelsOutbound.model_validate({"contact": {"answer_max_hours": 24}}).model_dump(mode="json")
    assert only_deadline["contact"] == {"answer_max_hours": 24}


@pytest.mark.parametrize("kw", [{}, {"exclude_unset": True}, {"exclude_defaults": True}])
def test_horario_igual_ao_de_omissao_nunca_se_perde(kw):
    """Revisão: «ausente» = sem restrição — perder um horário gravado deixava o agente contactar a qualquer hora."""
    for raw in ({"contact": {"hours": {}}}, {"contact": {"hours": {"start": "09:00", "end": "19:00"}}}):
        dumped = ProfileChannels.model_validate({"outbound": raw}).model_dump(mode="json", **kw)
        assert "outbound" in dumped and "contact" in dumped["outbound"], (raw, kw)
    blob = ClientProfile.model_validate({"channels": {"outbound": {"contact": {"hours": {}}}}}).to_blob_dict()
    assert blob["channels"]["outbound"]["contact"]["hours"]["end"] == "19:00"


@pytest.mark.parametrize("hours", [
    {"start": "19:00", "end": "09:00"}, {"start": "09:00", "end": "09:00"}, {"start": "9:00"},
    {"start": "24:00"}, {"end": "18:60"}, {"business_days_only": "yes"}, {"extra": 1}, {"start": 900}])
def test_horario_invalido_recusa(hours):
    with pytest.raises(ValidationError):
        ChannelsOutbound.model_validate({"contact": {"hours": hours}})


@pytest.mark.parametrize("hours", [0, 169, True, "24", 24.0])
def test_prazo_dentro_dos_limites(hours):
    with pytest.raises(ValidationError):
        ChannelsOutbound.model_validate({"contact": {"answer_max_hours": hours}})


def test_from_chat_so_se_grava_com_valor_e_e_interno():
    """v0.1.177 (peça 3): ausente = desligado; nulo nunca se grava (um core com a v0.1.176 recusava a chave)."""
    assert "from_chat" not in ChannelsOutbound.model_validate(
        {"contact": {"answer_max_hours": 24}}).model_dump(mode="json")["contact"]
    on = ChannelsOutbound.model_validate({"contact": {"from_chat": True}}).model_dump(mode="json")
    assert on["contact"] == {"from_chat": True}
    assert ChannelsOutbound.model_validate(on).model_dump(mode="json") == on
    for bad in ("yes", 1, "true"):
        with pytest.raises(ValidationError):
            ChannelsOutbound.model_validate({"contact": {"from_chat": bad}})
    assert exposure_of("channels.outbound.contact.from_chat") == "internal"


def test_reply_source_e_um_id_de_fonte_interno():
    """v0.1.177 (peça 4): o id de uma fonte de ingestão; nulo nunca se grava; interno."""
    ok = ChannelsOutbound.model_validate({"contact": {"reply_source": "caixa-geral_1"}}).model_dump(mode="json")
    assert ok["contact"] == {"reply_source": "caixa-geral_1"}
    assert "reply_source" not in ChannelsOutbound.model_validate(
        {"contact": {"answer_max_hours": 24}}).model_dump(mode="json")["contact"]
    for bad in ("", "a b", "x" * 65, "../x", "caixa@cliente.pt"):
        with pytest.raises(ValidationError):
            ChannelsOutbound.model_validate({"contact": {"reply_source": bad}})
    assert exposure_of("channels.outbound.contact.reply_source") == "internal"


def test_politica_e_do_cliente_e_o_resto_continua_interno():
    for p in ("channels.outbound.contact.hours.start", "channels.outbound.contact.hours.end",
              "channels.outbound.contact.hours.business_days_only", "channels.outbound.contact.answer_max_hours"):
        assert exposure_of(p) == "client_write", p
    assert exposure_of("channels.outbound.kinds.enabled") == "internal"


def test_hora_com_forma_no_json_schema():
    props = C.OutboundContactHours.model_json_schema()["properties"]
    assert props["start"]["pattern"] == C.HHMM_PATTERN and props["end"]["pattern"] == C.HHMM_PATTERN


@pytest.mark.parametrize("name", ["contact", "Contact", " contact "])
def test_servidor_mcp_contact_e_reservado(name):
    """Passo 6: `contact.ask`/`contact.tell` são as ferramentas nativas do agente — um servidor com o nome confundia-as."""
    from genesis_profile_schema.client_profile_schema import ProfileMCPServer
    with pytest.raises(ValidationError):
        ProfileMCPServer.model_validate({"name": name, "url": "https://x.pt/mcp"})
    assert ProfileMCPServer.model_validate({"name": "contacts", "url": "https://x.pt/mcp"}).name == "contacts"
