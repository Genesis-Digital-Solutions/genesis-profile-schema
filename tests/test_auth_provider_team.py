"""Equipa F4 (v0.1.123, 16 Out 2026): emissores de confiança para a equipa e
apps aceites por emissor (`frontend.auth.providers[]`)."""
import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ProfileAuthProvider, ProfileFrontendAuth
from genesis_profile_schema.exposure import INTERNAL, exposure_of


def _p(**kw):
    base = {"id": "okta", "type": "oidc", "issuer": "https://acme.okta.com", "audience": "api://x"}
    base.update(kw)
    return ProfileAuthProvider(**base)


def test_por_omissao_nao_vale_para_a_equipa_nem_filtra_apps():
    p = ProfileAuthProvider()
    assert p.team_email_domains == [] and p.allowed_client_ids == []


def test_dominios_normalizados_sem_repetidos():
    p = _p(team_email_domains=[" @Acme.PT", "acme.pt", "sub.acme.pt", ""])
    assert p.team_email_domains == ["acme.pt", "sub.acme.pt"]


@pytest.mark.parametrize("bad", ["acme", "a@b.pt", "acme..pt", "-acme.pt", "acme.pt/x", "x" * 300 + ".pt"])
def test_dominio_invalido_recusado(bad):
    with pytest.raises(ValidationError):
        _p(team_email_domains=[bad])


def test_emissor_da_equipa_precisa_de_id():
    with pytest.raises(ValidationError, match="precisa de um id"):
        _p(id="", team_email_domains=["acme.pt"])
    assert _p(id="", team_email_domains=[]).id == ""          # perfis antigos (Indaqua) continuam


def test_apps_aceites_validadas():
    assert _p(allowed_client_ids=[" 1b2c-3d ", "1b2c-3d"]).allowed_client_ids == ["1b2c-3d"]
    with pytest.raises(ValidationError):
        _p(allowed_client_ids=["tem espaço"])


def test_ids_preenchidos_nao_se_repetem_vazios_sim():
    ProfileFrontendAuth(providers=[{"id": ""}, {"id": ""}, {"id": "a"}])
    with pytest.raises(ValidationError, match="id repetido"):
        ProfileFrontendAuth(providers=[{"id": "a"}, {"id": "a"}])


def test_campos_novos_sao_internos():
    assert exposure_of("frontend.auth.providers.team_email_domains") == INTERNAL
    assert exposure_of("frontend.auth.providers.allowed_client_ids") == INTERNAL
