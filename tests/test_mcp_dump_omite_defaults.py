"""`mcp.servers[]`: `chat`, `read_tools` e `trusted_data` só saem no dump quando NÃO
são o default (v0.1.161, 8 Nov 2026) — o mesmo que o `MCPServerConfig` do core faz.

Medido na Indaqua dev: uma aprovação do Studio gravou pelo `/admin/profile/save`
(`to_blob_dict`) `"chat": true, "read_tools": [], "trusted_data": false` num servidor
que não os tinha. Um core anterior a um destes campos (`extra="forbid"`) recusava a
config MCP inteira numa promoção ou num rollback."""
import pytest

from genesis_profile_schema.client_profile_schema import ClientProfileSchema, ProfileMCPServer

SRV = {"name": "db", "url": "https://mcp"}


@pytest.mark.parametrize("raw", [
    {}, {"chat": True}, {"read_tools": []}, {"read_tools": None},
    {"trusted_data": False}, {"chat": True, "read_tools": [], "trusted_data": False},
])
def test_defaults_nao_saem(raw):
    d = ProfileMCPServer.model_validate(dict(SRV, **raw)).model_dump(mode="json")
    for k in ("chat", "read_tools", "trusted_data"):
        assert k not in d, k


def test_valores_nao_default_saem():
    d = ProfileMCPServer.model_validate(
        dict(SRV, chat=False, read_tools=["db_query_items"], trusted_data=True)).model_dump(mode="json")
    assert d["chat"] is False
    assert d["read_tools"] == ["db_query_items"]
    assert d["trusted_data"] is True


def test_ida_e_volta_mantem_o_comportamento():
    m = ProfileMCPServer.model_validate(SRV)
    de_novo = ProfileMCPServer.model_validate(m.model_dump(mode="json"))
    assert (de_novo.chat, de_novo.read_tools, de_novo.trusted_data) == (True, [], False)


def test_o_caminho_real_do_save_to_blob_dict():
    """É o `to_blob_dict` que o `/admin/profile/save` do core grava."""
    perfil = ClientProfileSchema.model_validate({"client_id": "x", "mcp": {"servers": [SRV]}})
    srv = perfil.to_blob_dict()["mcp"]["servers"][0]
    for k in ("chat", "read_tools", "trusted_data", "signing"):
        assert k not in srv, k
