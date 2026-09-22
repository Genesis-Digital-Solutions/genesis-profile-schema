"""
tests/test_voice_web_engine.py — motor da voz no widget e transcrição das
sessões (v0.1.68, 22 Set 2026, caminho B do parecer Astra).

O que protege: nenhum perfil da frota muda de comportamento (default
`realtime`, transcrição OFF); o motor é uma lista fechada; a retenção tem
piso; e a exposição diz o que foi decidido — motor interno (infra nossa),
transcrição visível ao cliente mas não editável (é matéria de DPA).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema import presentation
from genesis_profile_schema.client_profile_schema import (
    ClientProfileSchema, ProfileVoiceTranscription, ProfileVoiceWeb,
)
from genesis_profile_schema.ui_text import text_for


def test_defaults_nao_mudam_a_frota():
    web = ProfileVoiceWeb()
    assert web.enabled is False and web.engine == "realtime" and web.live_deployment == ""
    tr = ProfileVoiceTranscription()
    assert tr.enabled is False and tr.retention_days is None and tr.model is None
    prof = ClientProfileSchema.model_validate({"client_id": "x", "voice": {"web": {"enabled": True}}})
    assert prof.voice.web.engine == "realtime"


def test_motor_live_e_aceite_e_preservado():
    prof = ClientProfileSchema.model_validate(
        {"client_id": "x", "voice": {"web": {"enabled": True, "engine": "live",
                                              "live_deployment": "gpt-live-1"}}})
    assert prof.voice.web.engine == "live" and prof.voice.web.live_deployment == "gpt-live-1"
    assert prof.model_dump()["voice"]["web"]["engine"] == "live"


def test_motor_e_lista_fechada():
    with pytest.raises(ValidationError):
        ProfileVoiceWeb(engine="gpt-live")


def test_retencao_da_transcricao_normaliza_em_vez_de_recusar():
    """Sem `ge=1`: um 0 gravado por um GAIBO com pin antigo não pode impedir o
    perfil inteiro de gravar (422 em qualquer tab). 0, negativo, vazio ou lixo
    → None = a retenção das conversas; o perfil continua a carregar e a gravar."""
    assert ProfileVoiceTranscription(enabled=True, retention_days=30).retention_days == 30
    assert ProfileVoiceTranscription(retention_days="30").retention_days == 30
    for bad in (0, -5, "", "abc", None, True):
        assert ProfileVoiceTranscription(retention_days=bad).retention_days is None
    prof = ClientProfileSchema.model_validate(
        {"client_id": "x", "voice": {"transcription": {"enabled": True, "retention_days": 0}}})
    assert prof.voice.transcription.retention_days is None


def test_exposicao_decidida():
    assert exp.exposure_of("voice.web.engine") == exp.INTERNAL
    assert exp.exposure_of("voice.web.live_deployment") == exp.INTERNAL
    assert exp.exposure_of("voice.transcription.enabled") == exp.CLIENT_READ
    assert exp.exposure_of("voice.transcription.retention_days") == exp.CLIENT_READ
    assert exp.exposure_of("voice.transcription.model") == exp.INTERNAL


def test_o_motor_e_um_select_com_nomes_nas_duas_linguas():
    assert presentation.control_for("voice.web.engine") == "select"
    for loc in ("pt-PT", "en-GB"):
        t = text_for("voice.web.engine", loc)
        assert set(t["options"]) == {"realtime", "live"}
        assert "GPT-Live" in t["options"]["live"]
        label = str(text_for("voice.transcription", loc)["label"]).lower()
        assert "reservado" not in label and "reserved" not in label
