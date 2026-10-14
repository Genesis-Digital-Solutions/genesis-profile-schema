"""
Convites da Equipa do GAIBO pela caixa de saída (v0.1.108, 13 Out 2026;
resposta ao BACKLOG gaibo 3.1560 — handoff Genesis (f)–(h)).

Quem é adicionado na página Equipa do GAIBO tem de existir como convidado no
tenant do cliente para conseguir entrar. O GAIBO não tem poder para convidar
(regra da Genesis: a identidade de uma app exposta à internet nunca administra o
diretório). Por isso PEDE ao Studio, pela caixa de saída, e o Studio convida:

    gaibo-outbox/
      invites/<convite>.json         GAIBO   (o pedido, escrito UMA vez)
      invite-results/<convite>.json  Studio  (o estado desse pedido)

As mesmas regras do resto da caixa: um ficheiro novo com `If-None-Match: *`
(nunca se reescreve um pedido); o resultado só com `If-Match` do ETag lido;
um ficheiro que não valida é INVÁLIDO e di-lo-se — nunca é saltado em silêncio.

O pedido leva só o necessário para convidar: o email e o nome a mostrar.
O Studio:
  * valida o email outra vez (nunca confia no que lê da caixa);
  * nunca convida para o tenant da Genesis (clientes alojados no tenant da
    Genesis — demos — recusam-se: `reason_code="genesis_tenant"`);
  * respeita `INVITES_PER_HOUR` por cliente (o excedente fica `pending` e anda
    na hora seguinte, nunca se perde);
  * convida com o email da Microsoft e o regresso ao site do GAIBO do cliente;
  * regista cada convite no audit do Studio.
A ligação da pessoa à Equipa continua a ser feita pelo GAIBO no 1.º início de
sessão, pelo email — este contrato não a muda.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .index_fields import CONTRACT_VERSION

INVITES_PREFIX = "invites/"
INVITE_RESULTS_PREFIX = "invite-results/"

#: Convites que o Studio envia por cliente e por hora (o resto espera, `pending`).
INVITES_PER_HOUR = 20

_INVITE_ID_RE = re.compile(r"^inv-[a-z0-9]{8,40}$")
#: Um email de convite: parte local e domínio com pelo menos um ponto; sem
#: espaços, aspas, `<>` nem controlo. Deliberadamente mais estreito do que o
#: RFC 5322 — um endereço que não passe aqui convida-se à mão.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f<>]")

MAX_EMAIL_LEN = 254
MAX_DISPLAY_NAME_LEN = 120

_CLOSED = ConfigDict(extra="forbid")


def is_valid_invite_id(value: Any) -> bool:
    """`inv-` + 8 a 40 de [a-z0-9]."""
    return isinstance(value, str) and bool(_INVITE_ID_RE.match(value))


def normalize_email(value: Any) -> Optional[str]:
    """O email em minúsculas e sem espaços à volta, ou None se não serve para convite."""
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    if not email or len(email) > MAX_EMAIL_LEN or not _EMAIL_RE.match(email) or ".." in email:
        return None
    return email


def invite_blob(invite_id: str) -> str:
    if not _INVITE_ID_RE.match(invite_id or ""):
        raise ValueError("id de convite inválido")
    return f"{INVITES_PREFIX}{invite_id}.json"


def invite_result_blob(invite_id: str) -> str:
    if not _INVITE_ID_RE.match(invite_id or ""):
        raise ValueError("id de convite inválido")
    return f"{INVITE_RESULTS_PREFIX}{invite_id}.json"


# ── Pedido (escreve o GAIBO) ────────────────────────────────────────────────

class InviteRequest(BaseModel):
    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    invite_id: str
    client_id: str = Field(min_length=1, max_length=80)
    requested_at: AwareDatetime
    # Referência opaca para o audit do GAIBO (quem pediu; nunca o email dele).
    requested_by_ref: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=MAX_EMAIL_LEN)
    display_name: str = Field(default="", max_length=MAX_DISPLAY_NAME_LEN)

    @field_validator("invite_id")
    @classmethod
    def _iid(cls, value: str) -> str:
        if not _INVITE_ID_RE.match(value):
            raise ValueError("id de convite inválido")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        email = normalize_email(value)
        if email is None:
            raise ValueError("email inválido para convite")
        return email

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str) -> str:
        name = " ".join((value or "").split())
        # controlo, `<>` e os invisíveis de formatação/uso privado (Cf/Co: inversão
        # bidirecional U+202E, espaço de largura zero…) — um nome que se faz passar
        # por outro no diretório do cliente
        if _CONTROL_RE.search(name) or any(unicodedata.category(c) in ("Cf", "Co") for c in name):
            raise ValueError("nome com caracteres não aceites")
        return name


# ── Resultado (escreve o Studio) ────────────────────────────────────────────

InviteStatus = Literal[
    "pending",          # recebido; ainda não enviado (fila, limite, ou a ser enviado agora)
    "sent",             # convite enviado; a pessoa ainda não o aceitou
    "already_member",   # a pessoa já é membro ou convidado aceite do tenant
    "refused",          # o Studio não convida (ver reason_code)
    "failed",           # erro ao convidar (ver reason; pode repetir-se com um pedido novo)
    "invalid",          # o pedido não cumpre o contrato
]

InviteReasonCode = Literal[
    "",
    "genesis_tenant",   # cliente no tenant da Genesis: convites só pela Genesis
    "rate_limited",     # limite por hora/dia atingido (fica pending)
    "sending",          # o Studio está a enviar este convite (reserva antes do envio)
    "duplicate",        # o mesmo email já foi convidado há pouco (não se reenvia)
    "expired",          # ficou por enviar demasiado tempo (falta de permissão, Graph em baixo)
    "uncertain",        # o envio foi tentado e o resultado perdeu-se: pode ter sido enviado
    "invalid_email",
    "client_mismatch",  # o client_id do pedido não é o desta caixa
    "not_configured",   # falta a permissão de convite no tenant do cliente
    "graph_error",
]


class InviteResult(BaseModel):
    model_config = _CLOSED

    schema_version: Literal[1] = CONTRACT_VERSION
    invite_id: str
    status: InviteStatus
    updated_at: AwareDatetime
    reason_code: InviteReasonCode = ""
    reason: str = Field(default="", max_length=300)
    sent_at: Optional[AwareDatetime] = None

    @field_validator("invite_id")
    @classmethod
    def _iid(cls, value: str) -> str:
        if not _INVITE_ID_RE.match(value):
            raise ValueError("id de convite inválido")
        return value
