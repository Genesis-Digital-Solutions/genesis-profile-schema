"""
Mensagens de suporte do GAIBO pela caixa de saída (2 Nov 2026; spec do gaibo
`2026-10-30-support-messages-design.md`, G-1).

Qualquer membro de um cliente escreve, na página «Suporte» do GAIBO, um assunto e
uma descrição; a mensagem chega à caixa de suporte da Genesis por email. O GAIBO
NÃO envia o email (nenhuma credencial de envio da Genesis na subscrição do
cliente; o GAIBO nunca escolhe o destinatário): PEDE ao Studio, pela caixa de
saída, como nos convites, e o Studio envia:

    gaibo-outbox/
      support-messages/<mensagem>.json          GAIBO   (escrito UMA vez)
      support-message-results/<mensagem>.json   Studio  (o estado, com If-Match)

As mesmas regras dos convites (`invites.py`): um ficheiro novo com
`If-None-Match: *`; o resultado só com `If-Match` do ETag lido; um ficheiro que
não valida é INVÁLIDO e di-lo-se. O Studio valida outra vez, recusa um
`client_id` que não seja o da caixa (`invalid`/`client_mismatch`), reserva antes
de enviar (`pending`/`sending`; uma reserva perdida → `failed`/`uncertain`),
respeita `SUPPORT_MESSAGES_PER_HOUR` por cliente (o excedente fica `pending`/
`rate_limited`) e, ao fim de 7 dias por enviar (desde `requested_at`), marca
`failed`/`expired`. Um reenvio no GAIBO é uma mensagem NOVA (`message_id` novo).

O email de quem envia viaja no ficheiro: é o Reply-To, e a mensagem existe para
ser respondida (decisão do Bruno, 2 Nov 2026).

Regras do texto: o assunto é UMA linha aparada (nenhum carácter de controlo nem
separador de linha/parágrafo Unicode, logo sem CR/LF nem injeção de cabeçalhos, e
nenhum invisível Cf/Co); a descrição é
texto simples com várias linhas em que só `\\n` e `\\t` são controlo permitido,
`\\r\\n` passa a `\\n` ANTES da validação (um `\\r` sozinho é recusado), e os
caracteres de inversão bidirecional são recusados (os outros invisíveis passam,
para não partir os emojis compostos). Nada se tira em silêncio além do aparar
das pontas; os comprimentos contam pontos de código.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .index_fields import CONTRACT_VERSION
from .invites import normalize_email

SUPPORT_MESSAGES_PREFIX = "support-messages/"
SUPPORT_MESSAGE_RESULTS_PREFIX = "support-message-results/"

#: Mensagens que o Studio envia por cliente e por hora (o resto espera, `pending`).
SUPPORT_MESSAGES_PER_HOUR = 20

MAX_SUBJECT_LEN = 120
MAX_DESCRIPTION_LEN = 2000
MAX_DISPLAY_NAME_LEN = 120

_ID_RE = re.compile(r"^msg-[a-z0-9]{8,40}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f<>]")
#: inversão bidirecional (U+202A–U+202E, U+2066–U+2069): texto que se lê como outro
_BIDI = frozenset(chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))

_CLOSED = ConfigDict(extra="forbid")


def is_valid_message_id(value: Any) -> bool:
    """`msg-` + 8 a 40 de [a-z0-9]. `fullmatch`: um `\\n` no fim não passa."""
    return isinstance(value, str) and _ID_RE.fullmatch(value) is not None


def support_message_blob(message_id: str) -> str:
    if not is_valid_message_id(message_id):
        raise ValueError("id de mensagem inválido")
    return f"{SUPPORT_MESSAGES_PREFIX}{message_id}.json"


def support_message_result_blob(message_id: str) -> str:
    if not is_valid_message_id(message_id):
        raise ValueError("id de mensagem inválido")
    return f"{SUPPORT_MESSAGE_RESULTS_PREFIX}{message_id}.json"


def _has_invisible(text: str) -> bool:
    # Cf/Co: inversão bidirecional U+202E, espaço de largura zero…
    return any(unicodedata.category(c) in ("Cf", "Co") for c in text)


def clean_subject(value: str) -> str:
    """O assunto aparado, ou `ValueError`. O controlo vê-se ANTES de aparar (um `\\n`
    no fim é recusado, não tirado). O erro nunca repete o texto."""
    # Zl/Zp (U+2028/U+2029) também quebram a linha (`splitlines`): o assunto é UMA linha
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in value) or _has_invisible(value):
        raise ValueError("assunto com caracteres não aceites")
    subject = value.strip()
    if not 1 <= len(subject) <= MAX_SUBJECT_LEN:
        raise ValueError(f"o assunto tem de ter 1 a {MAX_SUBJECT_LEN} caracteres")
    return subject


def clean_description(value: str) -> str:
    """A descrição aparada com `\\r\\n` como `\\n`, ou `ValueError`. Controlo fora de
    `\\n`/`\\t` (um `\\r` sozinho incluído) e inversão bidirecional são recusados."""
    text = value.replace("\r\n", "\n")
    if any((unicodedata.category(c) == "Cc" and c not in "\n\t") or c in _BIDI for c in text):
        raise ValueError("descrição com caracteres não aceites")
    text = text.strip()
    if not 1 <= len(text) <= MAX_DESCRIPTION_LEN:
        raise ValueError(f"a descrição tem de ter 1 a {MAX_DESCRIPTION_LEN} caracteres")
    return text


# ── Mensagem (escreve o GAIBO) ──────────────────────────────────────────────

class SupportMessageSender(BaseModel):
    model_config = _CLOSED

    # O Reply-To: normalizado pela regra dos convites.
    email: str
    display_name: str = Field(default="", max_length=MAX_DISPLAY_NAME_LEN)
    kind: Literal["member", "genesis_support"]

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        email = normalize_email(value)
        if email is None:
            raise ValueError("endereço de resposta inválido")
        return email

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str) -> str:
        # a regra do nome dos convites: espaços colapsados; controlo, `<>` e Cf/Co recusados
        name = " ".join((value or "").split())
        if _CONTROL_RE.search(name) or _has_invisible(name):
            raise ValueError("nome com caracteres não aceites")
        return name


class SupportMessage(BaseModel):
    """O que o GAIBO escreve em `support-messages/<id>.json`, uma vez."""

    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    message_id: str
    client_id: str = Field(min_length=1, max_length=80)
    requested_at: AwareDatetime
    sender: SupportMessageSender
    locale: Literal["pt-PT", "en-GB"]
    subject: str
    description: str

    @field_validator("message_id")
    @classmethod
    def _mid(cls, value: str) -> str:
        if not is_valid_message_id(value):
            raise ValueError("id de mensagem inválido")
        return value

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return clean_subject(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return clean_description(value)


# ── Resultado (escreve o Studio) ────────────────────────────────────────────

SupportMessageStatus = Literal[
    "pending",   # recebida; ainda não enviada (fila, limite, ou a ser enviada agora)
    "sent",      # o email saiu para a caixa de suporte
    "failed",    # não saiu (ver reason_code; o GAIBO deixa reenviar com uma mensagem nova)
    "invalid",   # a mensagem não cumpre o contrato (ou é de outro cliente)
]

SupportMessageReasonCode = Literal[
    "",
    "rate_limited",     # limite por hora/dia atingido (fica pending)
    "sending",          # o Studio está a enviar esta mensagem (reserva antes do envio)
    "uncertain",        # o envio foi tentado e o resultado perdeu-se: pode ter saído
    "not_configured",   # o Studio não tem como enviar (fica pending)
    "client_mismatch",  # o client_id da mensagem não é o desta caixa
    "send_error",       # o serviço de email recusou ou falhou
    "expired",          # ficou por enviar mais de 7 dias
]


class SupportMessageResult(BaseModel):
    """O que o Studio escreve em `support-message-results/<id>.json` (com `If-Match`)."""

    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    message_id: str
    status: SupportMessageStatus
    reason_code: SupportMessageReasonCode = ""
    reason: str = Field(default="", max_length=300)  # texto livre; o GAIBO nunca o mostra
    updated_at: AwareDatetime
    sent_at: Optional[AwareDatetime] = None

    @field_validator("message_id")
    @classmethod
    def _mid(cls, value: str) -> str:
        if not is_valid_message_id(value):
            raise ValueError("id de mensagem inválido")
        return value
