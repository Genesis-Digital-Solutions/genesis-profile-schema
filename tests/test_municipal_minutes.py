"""
tests/test_municipal_minutes.py — ata de ÓRGÃO AUTÁRQUICO (v0.1.76, 30 Set 2026):
o órgão e a lista oficial de membros do mandato vivem no perfil
(`audio.municipal_minutes`); a ata tira daqui nomes, cargos e partidos (regra R4
do pack da transcrição — nunca da fala).
"""

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema.client_profile_schema import ClientProfileSchema, ProfileAudio


def _perfil(mm):
    return ClientProfileSchema.model_validate({"client_id": "x", "audio": {"municipal_minutes": mm}})


def test_desligado_por_omissao_e_sem_membros():
    prof = ClientProfileSchema.model_validate({"client_id": "x"})
    mm = prof.audio.municipal_minutes
    assert mm.enabled is False and mm.members == [] and mm.organ_type == "camara_municipal"


def test_round_trip_com_membros():
    prof = _perfil({"enabled": True, "organ_type": "assembleia_municipal", "organ_name": "Assembleia Municipal de X",
                    "mandate": "2025–2029", "recorder": "Ana",
                    "members": [{"name": "Rui Sousa", "role": "Presidente da Mesa", "party": "PS"},
                                {"name": "Eva Lima", "role": "Membro", "party": "PSD", "substitute": True}]})
    dump = prof.model_dump()["audio"]["municipal_minutes"]
    assert dump["enabled"] is True and dump["organ_type"] == "assembleia_municipal"
    assert [m["name"] for m in dump["members"]] == ["Rui Sousa", "Eva Lima"]
    assert dump["members"][1]["substitute"] is True


def test_tipo_de_orgao_fechado_e_tectos():
    with pytest.raises(ValidationError):
        _perfil({"organ_type": "governo"})
    with pytest.raises(ValidationError):
        _perfil({"members": [{"name": "x" * 121}]})
    with pytest.raises(ValidationError):
        _perfil({"members": [{"name": "m"}] * 81})


def test_depende_da_tool_e_exposicao_decidida():
    props = ClientProfileSchema.model_json_schema()["$defs"]["ProfileAudio"]["properties"]
    assert props["municipal_minutes"]["requires_tool"] == "transcribe_audio"
    assert exp.exposure_of("audio.municipal_minutes.enabled") == exp.CLIENT_READ
    for campo in ("organ_type", "organ_name", "mandate", "recorder", "members.name", "members.role",
                  "members.party", "members.substitute"):
        assert exp.exposure_of(f"audio.municipal_minutes.{campo}") == exp.CLIENT_WRITE, campo
