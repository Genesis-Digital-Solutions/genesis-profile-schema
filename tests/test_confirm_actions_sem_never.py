"""`mcp.confirm_actions` sem o valor «never» (v0.1.137, relatório STEP, risco 4):
um perfil antigo com «never» lê-se como «all_writes» — nunca falha a validação."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ProfileMCP


@pytest.mark.parametrize("raw", ["never", "NEVER", " never ", None])
def test_never_e_null_leem_se_como_all_writes(raw):
    assert ProfileMCP(confirm_actions=raw).confirm_actions == "all_writes"


@pytest.mark.parametrize("raw", ["all_writes", "destructive_only"])
def test_valores_validos_ficam(raw):
    assert ProfileMCP(confirm_actions=raw).confirm_actions == raw


def test_valor_desconhecido_recusado():
    with pytest.raises(ValidationError):
        ProfileMCP(confirm_actions="sometimes")
