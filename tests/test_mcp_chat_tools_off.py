"""`mcp.servers[].chat_tools_off` (v0.1.167, F-20 do genesis-mcp, 13 Nov 2026): o
interruptor por tool do chat. Vazio/null/ausente = todas as tools no chat, como
sempre — e por isso nunca sai no dump."""
import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ClientProfileSchema, ProfileMCPServer

SRV = {"name": "sap", "url": "https://mcp"}


@pytest.mark.parametrize("raw", [{}, {"chat_tools_off": None}, {"chat_tools_off": []}])
def test_omissao_e_null_sao_tudo_ligado(raw):
    m = ProfileMCPServer.model_validate(dict(SRV, **raw))
    assert m.chat_tools_off == []
    assert "chat_tools_off" not in m.model_dump(mode="json")


def test_lista_limpa_sem_repetidos_e_sai_no_dump():
    m = ProfileMCPServer.model_validate(
        dict(SRV, chat_tools_off=[" erp_simulate_sales_order ", "erp_get_VK13", "erp_get_VK13"]))
    assert m.chat_tools_off == ["erp_simulate_sales_order", "erp_get_VK13"]
    assert m.model_dump(mode="json")["chat_tools_off"] == ["erp_simulate_sales_order", "erp_get_VK13"]


@pytest.mark.parametrize("raw", ["erp_get_VK13", {"a": 1}, [""], ["x" * 129], [None], [5], [{"a": 1}]])
def test_formas_invalidas_recusadas(raw):
    with pytest.raises(ValidationError):
        ProfileMCPServer.model_validate(dict(SRV, chat_tools_off=raw))


def test_mais_de_500_recusado():
    with pytest.raises(ValidationError):
        ProfileMCPServer.model_validate(dict(SRV, chat_tools_off=[f"t{i}" for i in range(501)]))


def test_nao_mexe_no_chat_nem_no_read_tools():
    m = ProfileMCPServer.model_validate(dict(SRV, chat_tools_off=["a"], read_tools=["a"]))
    assert m.chat is True and m.read_tools == ["a"]


def test_ida_e_volta_pelo_to_blob_dict():
    perfil = ClientProfileSchema.model_validate(
        {"client_id": "x", "mcp": {"servers": [dict(SRV, chat_tools_off=["a"])]}})
    srv = perfil.to_blob_dict()["mcp"]["servers"][0]
    assert srv["chat_tools_off"] == ["a"]
