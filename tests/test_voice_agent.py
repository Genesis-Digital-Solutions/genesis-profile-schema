"""
tests/test_voice_agent.py — ponte voz → agente completo (`voice.agent`,
v0.1.64, Bloco D do parecer Astra).

O que protege: OFF por default (a voz de toda a frota continua igual sem
ninguém ligar nada); `mode` fala o vocabulário do `runtime.agent_mode`; os
tectos têm piso (um perfil não pode pôr a voz a desistir do core ao fim de 2 s
nem a cortar respostas a 50 caracteres); e a exposição deixa o cliente ver o
interruptor e o modo, mas não afinar os tectos.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema.client_profile_schema import (
    ClientProfileSchema,
    ProfileVoice,
    ProfileVoiceAgent,
)


def test_off_por_default_e_no_perfil_inteiro():
    assert ProfileVoiceAgent().enabled is False
    assert ProfileVoice().agent.enabled is False
    prof = ClientProfileSchema.model_validate({"client_id": "x"})
    assert prof.voice.agent.enabled is False
    assert prof.voice.agent.mode == "fast"
    assert prof.voice.agent.timeout_s == 30
    assert prof.voice.agent.max_speech_chars == 900


def test_mode_fala_o_vocabulario_do_agent_mode():
    for m in ("fast", "balanced", "thinking", "max", "auto"):
        assert ProfileVoiceAgent(mode=m).mode == m
    with pytest.raises(ValidationError):
        ProfileVoiceAgent(mode="xhigh")          # esforço técnico não entra aqui
    with pytest.raises(ValidationError):
        ProfileVoiceAgent(mode="pro")


def test_tectos_tem_piso():
    assert ProfileVoiceAgent(timeout_s=10).timeout_s == 10
    assert ProfileVoiceAgent(timeout_s=120).timeout_s == 120
    with pytest.raises(ValidationError):
        ProfileVoiceAgent(timeout_s=2)
    assert ProfileVoiceAgent(max_speech_chars=300).max_speech_chars == 300
    with pytest.raises(ValidationError):
        ProfileVoiceAgent(max_speech_chars=50)


def test_perfil_antigo_sem_o_bloco_carrega():
    """Perfis da frota não têm `voice.agent` — o default_factory cobre."""
    prof = ClientProfileSchema.model_validate(
        {"client_id": "x", "voice": {"enabled": True, "deployment": "gpt-realtime-2.1-mini"}}
    )
    assert prof.voice.agent.enabled is False


def test_exposicao():
    assert exp.exposure_of("voice.agent.enabled") == "client_read"
    assert exp.exposure_of("voice.agent.mode") == "client_read"
    assert exp.exposure_of("voice.agent.timeout_s") == "internal"
    assert exp.exposure_of("voice.agent.max_speech_chars") == "internal"
    assert exp.is_client_visible("voice.agent.mode") and not exp.is_client_writable("voice.agent.mode")
