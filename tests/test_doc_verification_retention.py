"""`tools.config.verify_documents.retention_months` (18 Nov 2026): o prazo de conservação dos casos por frente."""
import pytest
from pydantic import ValidationError

from genesis_profile_schema.exposure import is_client_writable
from genesis_profile_schema.tool_doc_verification import (RETENTION_MAX_MONTHS, RETENTION_MIN_MONTHS,
                                                          ProfileToolDocVerificationConfig as Cfg)


def test_omissao_e_nada_se_apaga():
    assert Cfg().retention_months is None
    assert Cfg.model_validate({"retention_months": None}).retention_months is None


@pytest.mark.parametrize("v", [RETENTION_MIN_MONTHS, 24, RETENTION_MAX_MONTHS])
def test_limites_aceites(v):
    assert Cfg.model_validate({"retention_months": v}).retention_months == v


@pytest.mark.parametrize("v", [0, 5, 121, -1, 24.5, "24", True])
def test_recusas(v):
    with pytest.raises(ValidationError):
        Cfg.model_validate({"retention_months": v})


def test_e_do_cliente():
    assert is_client_writable("tools.config.verify_documents.retention_months")
    assert not is_client_writable("tools.config.verify_documents.deployment")
