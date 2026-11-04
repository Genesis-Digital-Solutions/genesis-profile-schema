"""
tests/test_audio_live_transcription.py — transcrição de REUNIÕES em tempo real
pelo microfone (v0.1.69, 23 Set 2026; bloco 7 do CONTEXT_PACK_voz_gpt_live_B §9).

O que protege: nenhum perfil da frota muda de comportamento (OFF por defeito);
o tecto de uma reunião tem PISO de 4 h e nunca desce (decisão do pack: «tecto
por defeito 4 h, configurável, nunca abaixo»); a exposição diz o que foi
decidido — o cliente VÊ o toggle (é matéria de DPA e de custo por hora) mas
não o liga; o tecto é infra nossa; e os dois campos declaram a dependência da
tool `transcribe_audio` para o editor avisar.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema import presentation
from genesis_profile_schema.client_profile_schema import ClientProfileSchema, ProfileAudio
from genesis_profile_schema.ui_text import text_for


def test_off_por_default_e_tecto_de_4h():
    a = ProfileAudio()
    assert a.live_transcription_enabled is False
    assert a.live_max_duration_min == 240
    prof = ClientProfileSchema.model_validate({"client_id": "x"})
    assert prof.audio.live_transcription_enabled is False
    assert prof.model_dump()["audio"]["live_max_duration_min"] == 240


def test_toggle_e_preservado_no_round_trip():
    prof = ClientProfileSchema.model_validate(
        {"client_id": "x", "audio": {"live_transcription_enabled": True,
                                     "live_max_duration_min": 480}})
    assert prof.audio.live_transcription_enabled is True
    assert prof.audio.live_max_duration_min == 480
    assert prof.model_dump()["audio"]["live_transcription_enabled"] is True


def test_o_tecto_nunca_desce_abaixo_de_4h():
    assert ProfileAudio(live_max_duration_min=240).live_max_duration_min == 240
    assert ProfileAudio(live_max_duration_min=600).live_max_duration_min == 600
    with pytest.raises(ValidationError):
        ProfileAudio(live_max_duration_min=239)
    with pytest.raises(ValidationError):
        ProfileAudio(live_max_duration_min=0)


def test_os_dois_campos_dependem_da_tool():
    props = ClientProfileSchema.model_json_schema()["$defs"]["ProfileAudio"]["properties"]
    assert props["live_transcription_enabled"]["requires_tool"] == "transcribe_audio"
    assert props["live_max_duration_min"]["requires_tool"] == "transcribe_audio"


def test_exposicao_decidida():
    assert exp.exposure_of("audio.live_transcription_enabled") == exp.CLIENT_READ
    assert exp.exposure_of("audio.live_max_duration_min") == exp.INTERNAL


def test_controlos_derivados_e_textos_nas_duas_linguas():
    assert presentation.control_for("audio.live_transcription_enabled") == presentation.TOGGLE
    assert presentation.control_for("audio.live_max_duration_min") == presentation.NUMBER
    for loc in ("pt-PT", "en-GB"):
        t = text_for("audio.live_transcription_enabled", loc)
        assert t["label"] and t["help"] and t["note"]
        # o texto tem de dizer as duas coisas que o cliente precisa de saber
        assert "RGPD" in t["help"] or "GDPR" in t["help"]
        assert "USD" in t["help"]
        assert text_for("audio.live_max_duration_min", loc)["help"]


def test_retencao_das_actas_e_audios_v0174():
    """None = a das conversas (tecto 180, aplicado pelo Studio); 1..180."""
    import pytest as _pt
    assert ProfileAudio().files_retention_days is None
    assert ProfileAudio(files_retention_days=30).files_retention_days == 30
    assert ProfileAudio(files_retention_days=180).files_retention_days == 180
    for mau in (0, 181, -1):
        with _pt.raises(Exception):
            ProfileAudio(files_retention_days=mau)


def test_retencao_do_audio_das_reunioes_v01143():
    """30 por omissão (decisão de 2 Nov 2026); 0 = não se guarda; teto 180."""
    import pytest as _pt
    assert ProfileAudio().meeting_audio_retention_days == 30
    assert ProfileAudio(meeting_audio_retention_days=0).meeting_audio_retention_days == 0
    assert ProfileAudio(meeting_audio_retention_days=180).meeting_audio_retention_days == 180
    for mau in (181, -1):
        with _pt.raises(Exception):
            ProfileAudio(meeting_audio_retention_days=mau)


def test_duracao_maxima_de_um_ficheiro_por_omissao_e_4h():
    # v0.1.95: alinhado com o teto fixo do core (4 h por ficheiro); deprecado na
    # v0.1.149, mas um blob antigo com 120 continua a validar (retrocompat).
    assert ProfileAudio().max_duration_min == 240
    assert ProfileAudio(max_duration_min=120).max_duration_min == 120
    # um valor antigo fora dos limites (ou lixo) nunca bloqueia a gravação do perfil
    for mau in (0, 999, "x", None, True):
        assert ProfileAudio(max_duration_min=mau).max_duration_min == 240
    js = ProfileAudio.model_json_schema()["properties"]["max_duration_min"]
    assert (js["minimum"], js["maximum"], js["deprecated"]) == (1, 240, True)
