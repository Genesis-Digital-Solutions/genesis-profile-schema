"""
`frontend.anonymousDataRetentionDays` (security-audit fecore T2, 13 Nov 2026):
prazo, em dias, dos dados de anónimos guardados no browser. Opcional — None
quer dizer «o valor por omissão do fecore» (30), porque um campo novo chega
como null aos blobs já gravados.
"""
import pytest
from pydantic import ValidationError

from genesis_profile_schema import ClientProfileSchema
from genesis_profile_schema.client_profile_schema import ProfileFrontend
from genesis_profile_schema.exposure import exposure_of


def test_por_omissao_e_none_e_vai_como_null_para_o_blob():
    assert ProfileFrontend().anonymousDataRetentionDays is None
    blob = ClientProfileSchema().to_blob_dict()
    assert "anonymousDataRetentionDays" in blob["frontend"]
    assert blob["frontend"]["anonymousDataRetentionDays"] is None


def test_null_num_blob_gravado_carrega():
    p = ClientProfileSchema.model_validate({"frontend": {"anonymousDataRetentionDays": None}})
    assert p.frontend.anonymousDataRetentionDays is None


def test_limites():
    for ok in (1, 7, 30, 365):
        assert ProfileFrontend(anonymousDataRetentionDays=ok).anonymousDataRetentionDays == ok
    for bad in (0, -1, 366, 999999):
        with pytest.raises(ValidationError):
            ProfileFrontend(anonymousDataRetentionDays=bad)


def test_o_cliente_ve_mas_nao_altera_como_os_outros_prazos_de_retencao():
    assert exposure_of("frontend.anonymousDataRetentionDays") == exposure_of(
        "compliance.retention.conversations_anonymous_days")
