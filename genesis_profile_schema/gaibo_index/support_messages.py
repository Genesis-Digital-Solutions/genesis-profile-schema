"""
Mensagens de Suporte do GAIBO pela caixa de saída (2 Nov 2026; G-1 da spec
gaibo `2026-10-30-support-messages-design.md`, escolhas do Bruno).

Na página «Suporte» do GAIBO, um membro do cliente escreve um assunto e uma
descrição para o suporte da Genesis. O GAIBO não envia email (nenhuma credencial
de envio da Genesis vive na subscrição do cliente, e o GAIBO não escolhe o
destinatário): ESCREVE um pedido na caixa de saída e o Studio envia.

    gaibo-outbox/
      support-messages/<mensagem>.json         GAIBO   (o pedido, escrito UMA vez)
      support-message-results/<mensagem>.json  Studio  (o estado desse pedido)

As mesmas regras dos convites: um pedido novo com `If-None-Match: *` (nunca se
reescreve); o resultado só com `If-Match` do ETag lido; um ficheiro que não
valida é INVÁLIDO e di-lo-se — nunca é saltado em silêncio. Um reenvio no GAIBO
é um pedido NOVO (outro `message_id`), nunca o mesmo ficheiro reescrito.

O pedido leva o email de quem envia (é o Reply-To: a mensagem existe para ser
respondida) e o texto tal como foi escrito. O Studio:
  * valida outra vez (nunca confia no que lê da caixa) e recusa um `client_id`
    que não seja o desta caixa (`invalid` + `client_mismatch`);
  * tira o nome do cliente e o URL da instância do SEU registo, nunca do ficheiro;
  * respeita `SUPPORT_MESSAGES_PER_HOUR` por cliente (e um teto diário de 50); o
    excedente fica `pending` + `rate_limited` e anda depois, nunca se perde;
  * reserva cada mensagem (`pending` + `sending`) ANTES de a enviar, para nunca a
    mandar duas vezes; se o envio foi tentado e o resultado se perdeu, fica
    `failed` + `uncertain` (um Reenviar pode então dar um email duplicado — no
    suporte é aceitável);
  * uma mensagem que passe 7 dias por enviar, contados desde o `requested_at`,
    fica `failed` + `expired`;
  * envia por ACS, em texto simples, para a caixa de suporte da Genesis (sem BCC),
    com Reply-To = `sender.email` e assunto `[<nome do cliente>] <assunto>`;
  * regista cada envio no audit do Studio.
Retenção: os resultados nunca se apagam; os pedidos (email e texto) apagam-se aos
180 dias por uma regra de ciclo de vida. O GAIBO nunca volta a ler um pedido
depois de o escrever.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .index_fields import CONTRACT_VERSION
from .invites import MAX_DISPLAY_NAME_LEN, normalize_email

SUPPORT_MESSAGES_PREFIX = "support-messages/"
SUPPORT_MESSAGE_RESULTS_PREFIX = "support-message-results/"

#: Mensagens que o Studio envia por cliente e por hora (o resto espera, `pending`).
SUPPORT_MESSAGES_PER_HOUR = 20

MAX_SUBJECT_LEN = 120
MAX_DESCRIPTION_LEN = 2000

_MESSAGE_ID_RE = re.compile(r"^msg-[a-z0-9]{8,40}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f<>]")
#: Inversão bidirecional (U+202A–U+202E, U+2066–U+2069): texto que se lê como
#: outra coisa. Na descrição só estes se recusam — os outros invisíveis (largura
#: zero, seletores de variação) fazem parte dos emojis compostos.
_BIDI = frozenset(chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))

_CLOSED = ConfigDict(extra="forbid")


def is_valid_message_id(value: Any) -> bool:
    """`msg-` + 8 a 40 de [a-z0-9]. `fullmatch`: uma quebra de linha no fim não passa."""
    return isinstance(value, str) and _MESSAGE_ID_RE.fullmatch(value) is not None


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
    """O assunto aparado, ou `ValueError`. Uma linha: nenhum carácter de controlo (nem CR/LF —
    vai para o cabeçalho do email) nem invisíveis Cf/Co. O controlo verifica-se ANTES de aparar,
    para uma quebra de linha no fim ser recusada e não retirada em silêncio."""
    if any(unicodedata.category(c) == "Cc" for c in value) or _has_invisible(value):
        raise ValueError("assunto com caracteres não aceites")
    subject = value.strip()
    if not 1 <= len(subject) <= MAX_SUBJECT_LEN:
        raise ValueError(f"o assunto tem de ter 1 a {MAX_SUBJECT_LEN} caracteres")
    return subject


def clean_description(value: str) -> str:
    """A descrição aparada, com `\\r\\n` como `\\n`, ou `ValueError`. Texto simples em várias
    linhas: dos caracteres de controlo só `\\n` e `\\t` (um `\\r` sozinho recusa-se); recusa a
    inversão bidirecional. Nada se retira em silêncio além do aparar: o que chega é o que foi
    escrito. Os comprimentos contam pontos de código."""
    text = value.replace("\r\n", "\n")
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in text):
        raise ValueError("descrição com caracteres não aceites")
    if any(c in _BIDI for c in text):
        raise ValueError("descrição com caracteres não aceites")
    text = text.strip()
    if not 1 <= len(text) <= MAX_DESCRIPTION_LEN:
        raise ValueError(f"a descrição tem de ter 1 a {MAX_DESCRIPTION_LEN} caracteres")
    return text


# ── Pedido (escreve o GAIBO) ────────────────────────────────────────────────

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
            raise ValueError("email de resposta inválido")
        return email

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str) -> str:
        # a regra do nome dos convites: espaços colapsados; sem controlo, `<>` nem Cf/Co
        name = " ".join((value or "").split())
        if _CONTROL_RE.search(name) or _has_invisible(name):
            raise ValueError("nome com caracteres não aceites")
        return name


class SupportMessage(BaseModel):
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
    "sent",      # email entregue ao ACS
    "failed",    # não saiu (ver reason_code); o GAIBO deixa reenviar com um pedido novo
    "invalid",   # o pedido não cumpre o contrato
]

SupportMessageReasonCode = Literal[
    "",
    "rate_limited",     # limite por hora/dia atingido (fica pending)
    "sending",          # o Studio está a enviar esta mensagem (reserva antes do envio)
    "uncertain",        # failed: o envio foi tentado e o resultado perdeu-se — pode ter saído
    "not_configured",   # falta a configuração de envio do lado do Studio
    "client_mismatch",  # o client_id do pedido não é o desta caixa
    "send_error",       # o ACS recusou ou falhou
    "expired",          # failed: 7 dias por enviar desde o requested_at
]


class SupportMessageResult(BaseModel):
    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    message_id: str
    status: SupportMessageStatus
    updated_at: AwareDatetime
    reason_code: SupportMessageReasonCode = ""
    reason: str = Field(default="", max_length=300)  # texto livre; o GAIBO nunca o mostra
    sent_at: Optional[AwareDatetime] = None

    @field_validator("message_id")
    @classmethod
    def _mid(cls, value: str) -> str:
        if not is_valid_message_id(value):
            raise ValueError("id de mensagem inválido")
        return value
