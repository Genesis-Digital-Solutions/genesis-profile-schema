"""
tests/test_access_and_ciam.py — v0.1.72: bloco `access` (quem pode entrar) e
`tenantMode: "ciam"` (Entra External ID). Contrato 42 / 41.

O que importa proteger: o DEFAULT do schema é o DEFAULT_PROFILE do genai-core.
Um `access` preenchido por omissão (mesmo `{}`) exigiria identidade forte a
TODA a frota — o default tem de ser None.
"""

import pytest
from pydantic import ValidationError

from genesis_profile_schema import ClientProfileSchema


def test_access_por_omissao_e_none():
    assert ClientProfileSchema().to_blob_dict()["access"] is None


def test_access_valido_e_listas_de_texto():
    p = ClientProfileSchema.model_validate({"access": {"allowedRoles": ["Analista"]}})
    d = p.to_blob_dict()["access"]
    assert d["allowedRoles"] == ["Analista"] and d["allowedGroups"] == []


def test_access_com_tipos_errados_recusado():
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate({"access": {"allowedRoles": "Analista"}})


def test_tenant_ciam_aceite_e_outros_recusados():
    ok = ClientProfileSchema.model_validate({"frontend": {"auth": {"tenantMode": "ciam"}}})
    assert ok.frontend.auth.tenantMode == "ciam"
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate({"frontend": {"auth": {"tenantMode": "outro"}}})
