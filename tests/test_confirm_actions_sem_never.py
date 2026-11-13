"""`mcp.confirm_actions` sem «never» (v0.1.137, relatório STEP, risco 4) nem
«destructive_only» (v0.1.167, F-20, 13 Nov 2026): um perfil antigo com um deles
lê-se como «all_writes» — nunca falha a validação, e nunca volta a sair no dump."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ProfileMCP


@pytest.mark.parametrize("raw", ["never", "NEVER", " never ", None,
                                 "destructive_only", " Destructive_Only "])
def test_retirados_e_null_leem_se_como_all_writes(raw):
    assert ProfileMCP(confirm_actions=raw).confirm_actions == "all_writes"


def test_all_writes_fica():
    assert ProfileMCP(confirm_actions="all_writes").confirm_actions == "all_writes"


def test_canario_o_unico_valor_e_all_writes():
    """Canário de segurança: não pode voltar a existir um valor do perfil que
    deixe uma escrita MCP correr sem confirmação."""
    import typing
    assert typing.get_args(ProfileMCP.model_fields["confirm_actions"].annotation) == ("all_writes",)


def test_retirado_nao_volta_a_sair_no_dump():
    assert ProfileMCP(confirm_actions="destructive_only").model_dump(mode="json")["confirm_actions"] == "all_writes"


def test_valor_desconhecido_recusado():
    with pytest.raises(ValidationError):
        ProfileMCP(confirm_actions="sometimes")
