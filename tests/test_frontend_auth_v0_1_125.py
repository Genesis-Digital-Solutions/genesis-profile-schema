"""
v0.1.125 (18 Out 2026, ponto 0 das variantes): `frontend.auth.stepUp` declarado
(lido só pelo genai-core; False = o de sempre), teto de 50 emissores confiáveis
(o D5 aceita 50 tenants; o fecore guarda até 128 hashes) e o comentário da
`audience` corrigido (vazia → o core ignora o emissor).
"""
import pytest

from genesis_profile_schema import ClientProfileSchema
from genesis_profile_schema.client_profile_schema import MAX_AUTH_PROVIDERS


def _auth(**kw):
    return ClientProfileSchema.model_validate({"frontend": {"auth": kw}}).frontend.auth


def test_step_up_por_omissao_desligado():
    assert _auth().stepUp is False
    assert _auth(stepUp=True).stepUp is True


def test_teto_de_emissores():
    provs = [{"id": f"t{i}", "issuer": f"https://login.microsoftonline.com/t{i}/v2.0", "audience": "api://x"}
             for i in range(MAX_AUTH_PROVIDERS)]
    assert len(_auth(providers=provs).providers) == MAX_AUTH_PROVIDERS
    with pytest.raises(Exception):
        _auth(providers=provs + [{"id": "a-mais", "issuer": "https://x", "audience": "a"}])


def test_step_up_e_interno():
    from genesis_profile_schema.exposure import exposure_of
    assert exposure_of("frontend.auth.stepUp") == exposure_of("frontend.auth.mode")
