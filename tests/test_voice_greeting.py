"""
tests/test_voice_greeting.py — `voice.greeting` aceita a `str` de sempre E o
mapa i18n `{lang: texto}` (v0.1.66, 22 Set 2026).

O que protege: nenhum perfil da frota parte (todos têm `str`); o mapa segue o
mesmo padrão de `frontend.welcomeMessage`, para o editor do Studio reutilizar
o botão ✨ de tradução; e a exposição não muda (o cliente escreve a saudação).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema.client_profile_schema import ClientProfileSchema, ProfileVoice


def test_a_str_de_sempre_continua_valida_e_e_o_default():
    assert ProfileVoice().greeting == ""
    prof = ClientProfileSchema.model_validate(
        {"client_id": "x", "voice": {"greeting": "Bom dia, em que posso ajudar?"}})
    assert prof.voice.greeting == "Bom dia, em que posso ajudar?"


def test_o_mapa_por_lingua_e_aceite_e_preservado():
    mapa = {"pt": "Bom dia!", "en": "Good morning!", "ar": "صباح الخير"}
    prof = ClientProfileSchema.model_validate({"client_id": "x", "voice": {"greeting": mapa}})
    assert prof.voice.greeting == mapa
    # round-trip sem perder chaves (o blob é a fonte de verdade)
    assert prof.model_dump()["voice"]["greeting"] == mapa


def test_o_mapa_e_de_texto_para_texto():
    with pytest.raises(ValidationError):
        ProfileVoice(greeting={"pt": ["lista", "não"]})
    with pytest.raises(ValidationError):
        ProfileVoice(greeting=42)


def test_a_exposicao_nao_mudou():
    """O cliente escreve a saudação (era `client_write`, continua a ser)."""
    assert exp.exposure_of("voice.greeting") == exp.CLIENT_WRITE
