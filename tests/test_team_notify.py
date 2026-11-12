"""`team.notify` (v0.1.165): avisos por email à equipa por área — desligados por omissão,
client_write (o cliente liga no GAIBO), com nome no ecrã."""

from genesis_profile_schema.exposure import CLIENT_WRITE, exposure_of
from genesis_profile_schema.team import ProfileTeam, TeamNotify


def test_desligado_por_omissao_e_perfis_antigos_validam():
    t = ProfileTeam.model_validate({"enabled": True})
    assert t.notify.queues.new is False and t.notify.queues.stale is False
    assert t.notify.docver.new is False and t.notify.docver.stale is False


def test_liga_por_area():
    t = ProfileTeam.model_validate({"notify": {"docver": {"new": True}}})
    assert t.notify.docver.new is True and t.notify.docver.stale is False and t.notify.queues.new is False


def test_o_cliente_muda_no_gaibo():
    for area in ("queues", "docver"):
        for flag in ("new", "stale"):
            assert exposure_of(f"team.notify.{area}.{flag}") == CLIENT_WRITE


def test_modelo_exportado():
    assert set(TeamNotify.model_fields) == {"queues", "docver"}


def test_client_directory_formal_interno_e_so_true_literal():
    # v0.1.165 (Finding 38 do core): o campo formal; o core só conta `true` literal.
    from genesis_profile_schema.client_profile_schema import ProfileAuthProvider
    from genesis_profile_schema.exposure import INTERNAL
    assert ProfileAuthProvider().client_directory is False
    assert ProfileAuthProvider.model_validate({"client_directory": True}).client_directory is True
    assert exposure_of("frontend.auth.providers.client_directory") == INTERNAL
