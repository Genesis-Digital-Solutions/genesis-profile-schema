"""tools.config das três tools do email original (31 Out 2026): só `queue`, como o core lê."""

import pytest

from genesis_profile_schema.client_profile_schema import ProfileTools

TOOLS = ("get_email_content", "list_email_files_names", "get_email_file_content")


@pytest.mark.parametrize("tool", TOOLS)
def test_fila_valida_e_extras_preservados(tool):
    t = ProfileTools.model_validate({"enabled": [tool], "config": {tool: {"queue": "encomendas", "outra": 1}}})
    assert t.config[tool]["queue"] == "encomendas" and t.config[tool]["outra"] == 1


@pytest.mark.parametrize("tool", TOOLS)
def test_sem_fila_continua_valido(tool):
    ProfileTools.model_validate({"enabled": [tool], "config": {tool: {}}})
    ProfileTools.model_validate({"enabled": [tool], "config": {tool: {"queue": None}}})


def test_fila_que_nao_e_texto_recusada():
    with pytest.raises(ValueError, match="get_email_content"):
        ProfileTools.model_validate({"config": {"get_email_content": {"queue": ["a"]}}})


def test_forma_para_o_ecra():
    from genesis_profile_schema import exposure
    shapes = exposure.tool_config_shapes()
    for tool in TOOLS:
        assert shapes[f"tools.config.{tool}.queue"]["type"] == "string"
