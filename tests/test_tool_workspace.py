"""tools.config.workspace (v0.1.187, 28 Nov 2026): desligado por omissão; um «ligado» só por um booleano verdadeiro."""

import pytest

from genesis_profile_schema.client_profile_schema import ClientProfileSchema, _KNOWN_TOOL_CONFIG_MODELS
from genesis_profile_schema.exposure import exposure_of
from genesis_profile_schema.tool_workspace import ProfileToolWorkspaceConfig


def test_desligado_por_omissao():
    assert ProfileToolWorkspaceConfig().chat_doc_verification is False


def test_no_mapa_das_configs_tipadas():
    assert _KNOWN_TOOL_CONFIG_MODELS["workspace"] is ProfileToolWorkspaceConfig


@pytest.mark.parametrize("value", ["true", 1, "1", "yes"])
def test_so_booleano_estrito(value):
    with pytest.raises(Exception):
        ClientProfileSchema.model_validate({"tools": {"config": {"workspace": {"chat_doc_verification": value}}}})


def test_perfil_com_o_campo_ligado_valida():
    p = ClientProfileSchema.model_validate({"tools": {"config": {"workspace": {"chat_doc_verification": True}}}})
    assert p.tools.config["workspace"]["chat_doc_verification"] is True


def test_interno():
    # Decisão de acesso a dados: só a Genesis liga (Studio), nunca o cliente pelo GAIBO.
    assert exposure_of("tools.config.workspace.chat_doc_verification") == "internal"
