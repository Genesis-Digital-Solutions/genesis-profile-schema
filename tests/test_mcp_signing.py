"""`mcp.servers[].signing` (v0.1.154, épico «Agente colega» I3): desligado ou `None`
não sai no dump — o `to_blob_dict` gravava `"signing": null` em todos os servidores e
um core anterior (`extra="forbid"`) recusava a config MCP inteira."""
import pytest

from genesis_profile_schema.client_profile_schema import ProfileMCPServer

SRV = {"name": "sap", "url": "https://mcp"}


@pytest.mark.parametrize("raw", [{}, {"signing": None}, {"signing": {"enabled": False}}])
def test_desligado_nao_sai(raw):
    assert "signing" not in ProfileMCPServer.model_validate(dict(SRV, **raw)).model_dump(mode="json")


def test_ligado_sai_e_so_com_enabled():
    m = ProfileMCPServer.model_validate(dict(SRV, signing={"enabled": True}))
    assert m.model_dump(mode="json")["signing"] == {"enabled": True}
    with pytest.raises(Exception):
        ProfileMCPServer.model_validate(dict(SRV, signing={"enabled": True, "require": True}))
