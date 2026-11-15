"""v0.1.169 (14 Nov 2026, pack «Voz: gravação e transcrição completa»): a
transcrição do munícipe e a gravação não se gravam no perfil sem a prova da
autorização escrita do cliente e o aviso falado. Canário: com o schema anterior
(sem o validador) o primeiro teste falha."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ProfileVoice
from genesis_profile_schema.voice_capture import consent_problem, notice_problem

DOC = {"kind": "document", "document_sha256": "a" * 64,
       "document_blob": "voice-consent/autorizacao.pdf",
       "legal_basis": "Interesse público", "purpose": "Qualidade do atendimento",
       "dpa_updated": True, "notice_ack": True, "retention_ack": True,
       "recorded_by": "operador@genesis.pt", "recorded_at": "2026-11-14T12:00:00Z"}
NOTICE = {"pt": "Esta chamada é transcrita e guardada trinta dias."}


def test_municipe_sem_prova_e_recusado():
    with pytest.raises(ValidationError) as e:
        ProfileVoice(transcription={"caller": True, "caller_model": "gpt-4o-transcribe"})
    assert "consent_missing" in str(e.value)


@pytest.mark.parametrize("over,code", [
    ({"capture_notice": ""}, "notice_missing"),
    ({"capture_notice": {"pt": 'diz "olá"'}}, "notice_invalid"),
    ({"capture_notice": {"pt": "x" * 401}}, "notice_too_long"),
    ({"capture_consent": {**DOC, "dpa_updated": False}}, "consent_dpa_updated"),
    ({"capture_consent": {**DOC, "recorded_at": "ontem"}}, "consent_recorded_by"),
    ({"transcription": {"caller": True}}, "caller_model_missing"),
])
def test_cada_falta_tem_o_seu_codigo(over, code):
    base = {"transcription": {"caller": True, "caller_model": "gpt-4o-transcribe"},
            "capture_consent": DOC, "capture_notice": NOTICE}
    with pytest.raises(ValidationError) as e:
        ProfileVoice(**{**base, **over})
    assert code in str(e.value)


def test_com_prova_e_aviso_aceita():
    v = ProfileVoice(transcription={"caller": True, "caller_model": "gpt-4o-transcribe"},
                     capture_consent=DOC, capture_notice=NOTICE, recording={"enabled": True})
    assert v.transcription.caller and v.recording.enabled and v.recording.retention_days == 30


def test_transcricao_so_do_assistente_continua_a_gravar_sem_prova():
    """Já existia gravada (callagent-dev): recusá-la aqui dava 422 em qualquer
    save desse perfil. O core é que a bloqueia na chamada."""
    assert ProfileVoice(transcription={"phone": True}).transcription.phone is True


def test_gravacao_normaliza_sem_recusar():
    v = ProfileVoice(recording={"retention_days": 999, "channels": "5.1"})
    assert v.recording.retention_days == 180 and v.recording.channels == "stereo"
    assert ProfileVoice(recording={"retention_days": "x"}).recording.retention_days == 30
    assert ProfileVoice(transcription={"caller_model": "a b;c"}).transcription.caller_model is None


def test_prova_mal_formada_nao_parte_o_carregamento_sem_captura():
    """Sem captura pedida, uma prova incompleta não impede o perfil de carregar."""
    v = ProfileVoice(capture_consent={"kind": "whatsapp"})
    assert v.capture_consent.kind == "whatsapp"


def test_regras_iguais_as_do_core():
    """Os códigos e as regras são os do core (`voice/capture_gate.py`)."""
    assert consent_problem(DOC) == ""
    assert consent_problem({**DOC, "document_sha256": "٣" * 64}) == "consent_document_hash"
    assert consent_problem({**DOC, "document_blob": "voice-consent/../x"}) == "consent_document_path"
    assert consent_problem({**DOC, "kind": "email", "email_sender": "a@b.pt",
                            "email_date": "2026-02-30", "email_subject": "x"}) == "consent_email_date"
    assert notice_problem(NOTICE) == "" and notice_problem({"pt": "a\nb"}) == "notice_invalid"


# ── recibo do documento (declarado no bump seguinte à v0.1.169) ─────────────

def test_recibo_do_documento_declarado_opcional_e_interno():
    """O core escreve `document_receipt` (64 hex, `voice/consent_receipt.py`) e o Studio copia-o
    para o perfil; até aqui ia pelo `extra="allow"`. Declarado: o valor sobrevive ao dump, um
    perfil sem ele (ou com `null`) carrega igual, e fica `internal` (só o Studio o escreve)."""
    from genesis_profile_schema.exposure import exposure_of
    from genesis_profile_schema.voice_capture import ProfileVoiceCaptureConsent
    assert "document_receipt" in ProfileVoiceCaptureConsent.model_fields
    assert ProfileVoiceCaptureConsent().document_receipt is None
    assert ProfileVoiceCaptureConsent(document_receipt=None).document_receipt is None
    rec = "b" * 64
    v = ProfileVoice(transcription={"caller": True, "caller_model": "gpt-4o-transcribe"},
                     capture_consent={**DOC, "document_receipt": rec}, capture_notice=NOTICE)
    assert v.capture_consent.document_receipt == rec
    assert v.model_dump()["capture_consent"]["document_receipt"] == rec
    # a verificação do recibo vive no core (a chave só lá existe): o schema não a repete
    assert consent_problem({**DOC, "document_receipt": None}) == ""
    assert exposure_of("voice.capture_consent.document_receipt") == "internal"
