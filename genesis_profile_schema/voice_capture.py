"""
genesis_profile_schema/voice_capture.py — captura das CHAMADAS (v0.1.169, 14
Nov 2026; pack «Voz: gravação e transcrição completa», decisões D2–D9 do
Bruno): gravação do áudio, prova da autorização escrita do cliente e o aviso
falado no início da chamada.

Consumidor: genai-core `voice/capture_gate.py` — a GARANTIA vive lá (falha
fechada em cada chamada). O validador aqui é a camada de cima: recusa gravar um
perfil que liga a transcrição do munícipe ou a gravação sem a prova completa e
o aviso. Não recusa a transcrição só do assistente (`phone`) sem prova: essa
já existia gravada em perfis (callagent-dev), e um validador novo que a
recusasse faria o save de QUALQUER tab desse perfil dar 422 (regra do
CAPACIDADES) — o core já não a deixa capturar.

A prova é deliberadamente LENIENTE na forma (tudo opcional, sem limites que
partam o carregamento): a completude só se exige quando há captura pedida, e as
regras são as MESMAS do core (`consent_problem`), com os códigos iguais.
Todos os campos são `internal` (`exposure.py`): só o Studio os escreve.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, field_validator

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_BLOB_RE = re.compile(r"voice-consent/[A-Za-z0-9._-]{1,200}")
_EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
DEPLOYMENT_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
MAX_NOTICE_CHARS = 400
MAX_TEXT_CHARS = 500
RECORDING_DEFAULT_DAYS = 30
RECORDING_MAX_DAYS = 180


class ProfileVoiceRecording(BaseModel):
    """Gravação do áudio da chamada (fase 2 do pack — só depois da medição
    M1). OFF por omissão. Dias: 30 por omissão, 1–180, e o core nunca guarda
    mais do que a retenção das conversas. `channels`: `stereo` = munícipe à
    esquerda, assistente à direita (D5)."""
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    retention_days: int = RECORDING_DEFAULT_DAYS
    channels: str = "stereo"

    @field_validator("retention_days", mode="before")
    @classmethod
    def _dias(cls, v):
        # Normaliza em vez de recusar: um valor mau nunca impede o perfil de carregar.
        if v is None or v == "" or isinstance(v, bool):
            return RECORDING_DEFAULT_DAYS
        try:
            n = int(v)
        except (TypeError, ValueError):
            return RECORDING_DEFAULT_DAYS
        return max(1, min(n, RECORDING_MAX_DAYS))

    @field_validator("channels", mode="before")
    @classmethod
    def _canais(cls, v):
        return v if v in ("stereo", "mono") else "stereo"


class ProfileVoiceCaptureConsent(BaseModel):
    """Prova da autorização ESCRITA do cliente para captar as chamadas (D8):
    documento guardado no storage do cliente (`voice-consent/…`, com sha256) OU
    o registo do email (remetente, data AAAA-MM-DD, assunto) — mais a base
    legal, a finalidade, as três confirmações e quem registou e quando.
    Escrita só pelo Studio. `email_sender`/`recorded_by` são dados pessoais:
    nunca vão para logs (o core só audita códigos)."""
    model_config = ConfigDict(extra="allow")
    kind: Optional[str] = None                 # "document" | "email"
    document_sha256: Optional[str] = None
    document_blob: Optional[str] = None
    # Recibo HMAC do core (64 hex, `voice/consent_receipt.py`), escrito pelo core ao guardar o
    # documento e copiado pelo Studio para o perfil; o `voice/capture_gate.py` só aceita a prova
    # «documento» com o recibo certo. Declarado no bump seguinte à v0.1.169 (até lá ia pelo
    # `extra="allow"`). Leniente como as irmãs: a verificação vive no core (a chave só lá existe).
    document_receipt: Optional[str] = None
    email_sender: Optional[str] = None
    email_date: Optional[str] = None
    email_subject: Optional[str] = None
    legal_basis: Optional[str] = None
    purpose: Optional[str] = None
    dpa_updated: bool = False
    notice_ack: bool = False
    retention_ack: bool = False
    recorded_by: Optional[str] = None
    recorded_at: Optional[str] = None


#: Texto do aviso: vai entre aspas para as instruções do modelo — sem aspas,
#: quebras de linha nem caracteres de controlo (é texto legal, não precisa).
_NOTICE_FORBIDDEN_RE = re.compile(r'["\x00-\x1f\x7f]')


def _real_date(v: Any) -> bool:
    """AAAA-MM-DD com dígitos ASCII e data que existe."""
    if not (isinstance(v, str) and _DATE_RE.fullmatch(v)):
        return False
    from datetime import date
    try:
        date.fromisoformat(v)
    except ValueError:
        return False
    return True


def _iso_instant(v: Any) -> bool:
    """Instante ISO 8601 (ex.: 2026-11-14T12:00:00Z), dígitos ASCII."""
    if not (isinstance(v, str) and 10 <= len(v) <= 40 and v.isascii()):
        return False
    from datetime import datetime
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _text(v: Any, max_chars: int = MAX_TEXT_CHARS) -> str:
    return v.strip() if isinstance(v, str) and 0 < len(v.strip()) <= max_chars else ""


def consent_problem(consent: Any) -> str:
    """'' se a prova está completa; senão o código (os MESMOS do core)."""
    if isinstance(consent, BaseModel):
        consent = consent.model_dump()
    if not isinstance(consent, Mapping):
        return "consent_missing"
    kind = consent.get("kind")
    if kind == "document":
        sha = consent.get("document_sha256")
        if not (isinstance(sha, str) and _SHA256_RE.fullmatch(sha)):
            return "consent_document_hash"
        blob = consent.get("document_blob")
        if not (isinstance(blob, str) and _BLOB_RE.fullmatch(blob) and ".." not in blob):
            return "consent_document_path"
    elif kind == "email":
        sender = consent.get("email_sender")
        if not (isinstance(sender, str) and len(sender) <= 254 and _EMAIL_RE.fullmatch(sender)):
            return "consent_email_sender"
        if not _real_date(consent.get("email_date")):
            return "consent_email_date"
        if not _text(consent.get("email_subject"), 300):
            return "consent_email_subject"
    else:
        return "consent_kind"
    if not _text(consent.get("legal_basis")):
        return "consent_legal_basis"
    if not _text(consent.get("purpose")):
        return "consent_purpose"
    for ack in ("dpa_updated", "notice_ack", "retention_ack"):
        if consent.get(ack) is not True:
            return f"consent_{ack}"
    if not _text(consent.get("recorded_by"), 254) or not _iso_instant(consent.get("recorded_at")):
        return "consent_recorded_by"
    return ""


def notice_problem(notice: Any) -> str:
    """O aviso existe (str ou {lang: texto}) e cada texto cabe em 400."""
    if isinstance(notice, str):
        texts = [notice]
    elif isinstance(notice, Mapping):
        texts = [v for v in notice.values()]
    else:
        return "notice_missing"
    texts = [t.strip() for t in texts if isinstance(t, str) and t.strip()]
    if not texts:
        return "notice_missing"
    if any(len(t) > MAX_NOTICE_CHARS for t in texts):
        return "notice_too_long"
    if any(_NOTICE_FORBIDDEN_RE.search(t) for t in texts):
        return "notice_invalid"
    return ""
