"""v0.1.177 (24 Nov 2026): `voice.transcription.filtered` — a transcrição
FILTRADA das chamadas sem a autorização do cliente. Desligada por defeito,
grava-se sem prova nem aviso (como o chat) e o cliente só a lê."""

from __future__ import annotations

from genesis_profile_schema.client_profile_schema import ProfileVoice
from genesis_profile_schema.exposure import EXPOSURE


def test_desligada_por_defeito():
    assert ProfileVoice().transcription.filtered is False


def test_liga_sem_prova_nem_aviso():
    v = ProfileVoice(transcription={"filtered": True, "caller_model": "gpt-4o-transcribe"})
    assert v.transcription.filtered is True
    assert v.transcription.caller is False      # nunca liga a transcrição completa


def test_cliente_le_mas_nao_escreve():
    assert EXPOSURE["voice.transcription.filtered"] == EXPOSURE["voice.transcription.phone"]
