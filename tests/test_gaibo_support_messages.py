"""Mensagens de Suporte do GAIBO pela caixa de saída."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from genesis_profile_schema import gaibo_index as gi

NOW = datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)


def _msg(**over):
    base = {"message_id": "msg-abcdefgh12", "client_id": "remax-v2-prod", "requested_at": NOW.isoformat(),
            "sender": {"email": "Ana.Silva@Remax.PT", "display_name": "Ana  Silva", "kind": "member"},
            "locale": "pt-PT", "subject": "  A pesquisa não encontra o regulamento ", "description": "Linha 1\r\nLinha 2\t"}
    base.update(over)
    return base


def test_pedido_valido_normaliza():
    m = gi.SupportMessage.model_validate(_msg())
    assert m.schema_version == 1
    assert m.sender.email == "ana.silva@remax.pt" and m.sender.display_name == "Ana Silva"
    assert m.subject == "A pesquisa não encontra o regulamento"
    assert m.description == "Linha 1\nLinha 2"


@pytest.mark.parametrize("bad", ["a\nb", "a\rb", "fim\n", "a\x00", "a‮b", "a​b", "a\u2028b", "a\u2029b",
                                 "", "   ", "x" * 121])
def test_assunto_recusado(bad):
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(subject=bad))


@pytest.mark.parametrize("cp", [0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069])
def test_descricao_recusa_inversao_bidirecional(cp):
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(description=f"abc{chr(cp)}def"))


def test_descricao_aceita_emojis_compostos_e_recusa_controlo():
    family = "👩‍👩‍👧"           # ZWJ
    heart = "❤️"                     # seletor de variação
    assert gi.clean_description(f"obrigado {family} {heart}") == f"obrigado {family} {heart}"
    for bad in ("a\rb", "a\x00b", "a\x1bb", "", "x" * 2001):
        with pytest.raises(ValueError):
            gi.clean_description(bad)
    assert len(gi.clean_description("😀" * 2000)) == 2000   # conta pontos de código


def test_remetente_fechado():
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(sender={"email": "sem-arroba", "kind": "member"}))
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(sender={"email": "a@x.pt", "kind": "admin"}))
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(sender={"email": "a@x.pt", "kind": "member", "display_name": "<b>"}))
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(sender={"email": "a@x.pt", "kind": "member", "oid": "x"}))


def test_contrato_fechado_e_ids():
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(to="outra@x.pt"))          # o destino é do Studio
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(message_id="inv-abcdefgh12"))
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(requested_at="2026-11-02T16:00:00"))   # sem fuso
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(locale="pt-BR"))
    assert gi.is_valid_message_id("msg-abcdefgh") and not gi.is_valid_message_id("msg-ABCDEFGH")
    assert not gi.is_valid_message_id("msg-abcdefgh\n")
    assert gi.support_message_blob("msg-abcdefgh12") == "support-messages/msg-abcdefgh12.json"
    assert gi.support_message_result_blob("msg-abcdefgh12") == "support-message-results/msg-abcdefgh12.json"
    with pytest.raises(ValueError):
        gi.support_message_blob("../x")


def test_resultado():
    res = gi.SupportMessageResult(message_id="msg-abcdefgh12", status="sent", updated_at=NOW, sent_at=NOW)
    assert res.model_dump(mode="json")["status"] == "sent" and res.sent_at == NOW
    assert gi.SupportMessageResult(message_id="msg-abcdefgh12", status="failed", updated_at=NOW,
                                   reason_code="uncertain").sent_at is None
    with pytest.raises(ValidationError):
        gi.SupportMessageResult(message_id="msg-abcdefgh12", status="refused", updated_at=NOW)
    with pytest.raises(ValidationError):
        gi.SupportMessageResult(message_id="msg-abcdefgh12", status="failed", updated_at=NOW, reason_code="outro")
    with pytest.raises(ValidationError):
        gi.SupportMessageResult(message_id="msg-abcdefgh12", status="failed", updated_at=NOW, reason="x" * 301)
    with pytest.raises(ValidationError):
        gi.SupportMessageResult(message_id="msg-abcdefgh12", status="sent", updated_at=NOW, extra=1)


def test_exportacoes_e_tipos():
    from typing import get_args
    from genesis_profile_schema.gaibo_index import support_messages as sm
    assert set(get_args(gi.SupportMessageStatus)) == {"pending", "sent", "failed", "invalid"}
    assert "client_mismatch" in get_args(gi.SupportMessageReasonCode)
    assert sm.MAX_DISPLAY_NAME_LEN == gi.invites.MAX_DISPLAY_NAME_LEN == 120


def test_prefixos_nao_colidem_com_os_outros():
    mine = (gi.SUPPORT_MESSAGES_PREFIX, gi.SUPPORT_MESSAGE_RESULTS_PREFIX)
    others = (gi.REQUESTS_PREFIX, gi.RESULTS_PREFIX, gi.RUNS_PREFIX, gi.INVITES_PREFIX,
              gi.INVITE_RESULTS_PREFIX, gi.REMOVALS_PREFIX)
    assert all(not p.startswith(o) and not o.startswith(p) for p in mine for o in others)
    assert not mine[0].startswith(mine[1]) and not mine[1].startswith(mine[0])
    assert gi.SUPPORT_MESSAGES_PER_HOUR == 20
