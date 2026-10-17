"""
`variantMode` (v0.1.124, fase B das autenticações por variante, 17 Out 2026):
Partilhada (None/"shared", o de sempre) ou Separada ("separate", o genai-core
funde só DEFAULT + variante). O risco que isto guarda: um default preenchido
mudar a frota, um `null` gravado recusar o perfil, ou o campo aparecer ao
cliente (é `internal`).
"""
import pytest
from pydantic import ValidationError

from genesis_profile_schema import ClientProfileSchema
from genesis_profile_schema.exposure import exposure_of


def test_por_omissao_e_none_e_o_dump_nao_preenche_nada():
    p = ClientProfileSchema.model_validate({})
    assert p.variantMode is None
    assert p.model_dump(mode="json")["variantMode"] is None


@pytest.mark.parametrize("v", ["shared", "separate", None])
def test_valores_aceites(v):
    assert ClientProfileSchema.model_validate({"variantMode": v}).variantMode == v


@pytest.mark.parametrize("v", ["Separate", "isolada", "", 1, True])
def test_outros_valores_recusados(v):
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate({"variantMode": v})


def test_e_interno():
    assert exposure_of("variantMode") == "internal"
