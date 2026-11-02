"""Mensagens de suporte do GAIBO pela caixa de saída (spec do gaibo G-1, 2 Nov 2026)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from genesis_profile_schema import gaibo_index as gi

NOW = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
MID = "msg-" + "0123456789abcdef" * 2


def _msg(**over):
    base = {"message_id": MID, "client_id": "genesis-ai-dev", "requested_at": NOW.isoformat(),
            "sender": {"email": "Ana.Silva@Remax.PT", "display_name": "Ana  Silva", "kind": "member"},
            "locale": "pt-PT", "subject": "  A pesquisa não encontra o regulamento  ",
            "description": "Linha 1\r\nLinha 2\n\tcom tab  "}
    base.update(over)
    return base


def test_mensagem_valida_normaliza():
    m = gi.SupportMessage.model_validate(_msg())
    assert m.schema_version == 1
    assert m.sender.email == "ana.silva@remax.pt" and m.sender.display_name == "Ana Silva"
    assert m.subject == "A pesquisa não encontra o regulamento"
    assert m.description == "Linha 1\nLinha 2\n\tcom tab"


@pytest.mark.parametrize("subject", ["a\nb", "fim\n", "a\rb", "a\x00", "a‮b", "a​b",
                                     "a b", "a b", "", "   ", "x" * 121])
def test_assunto_recusado(subject):
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(subject=subject))


def test_assunto_no_limite():
    assert gi.SupportMessage.model_validate(_msg(subject="é" * 120)).subject == "é" * 120


@pytest.mark.parametrize("description", ["a\rb", "a\x00b", "a\x1bb", "a‮b", "a⁦b",
                                         "", " \n\t ", "x" * 2001])
def test_descricao_recusada(description):
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(description=description))


def test_descricao_aceita_emoji_composto_e_limite():
    family = "\U0001F468‍\U0001F469‍\U0001F467"   # ZWJ (Cf) dentro de um emoji
    assert family in gi.SupportMessage.model_validate(_msg(description=f"obrigado {family}")).description
    assert len(gi.SupportMessage.model_validate(_msg(description="x" * 2000)).description) == 2000


def test_remetente():
    for bad in ({"email": "sem-arroba", "kind": "member"},
                {"email": "a@x.pt", "kind": "admin"},
                {"email": "a@x.pt", "kind": "member", "display_name": "<b>"},
                {"email": "a@x.pt", "kind": "member", "display_name": "An​a"},
                {"email": "a@x.pt", "kind": "member", "extra": 1}):
        with pytest.raises(ValidationError):
            gi.SupportMessage.model_validate(_msg(sender=bad))
    m = gi.SupportMessage.model_validate(_msg(sender={"email": "s@genesis.pt", "kind": "genesis_support"}))
    assert m.sender.display_name == ""


def test_contrato_fechado_locale_e_ids():
    for over in ({"extra": 1}, {"locale": "pt-BR"}, {"message_id": "msg-ABC12345"},
                 {"message_id": "inv-abcdefgh12"}, {"message_id": MID + "\n"}, {"schema_version": 2},
                 {"requested_at": "2026-11-02T18:00:00"}, {"client_id": ""}):
        with pytest.raises(ValidationError):
            gi.SupportMessage.model_validate(_msg(**over))
    assert gi.is_valid_message_id("msg-abcdefgh") and not gi.is_valid_message_id("msg-abc")
    assert not gi.is_valid_message_id(None)


def test_caminhos():
    assert gi.support_message_blob(MID) == f"support-messages/{MID}.json"
    assert gi.support_message_result_blob(MID) == f"support-message-results/{MID}.json"
    for bad in ("../x", "msg-a/b", ""):
        with pytest.raises(ValueError):
            gi.support_message_blob(bad)
        with pytest.raises(ValueError):
            gi.support_message_result_blob(bad)
    # a condição ABAC da API usa `StringStartsWith`: o prefixo do GAIBO nunca pode cobrir o do Studio
    assert not gi.SUPPORT_MESSAGE_RESULTS_PREFIX.startswith(gi.SUPPORT_MESSAGES_PREFIX)


def test_resultado():
    r = gi.SupportMessageResult.model_validate({"message_id": MID, "status": "sent",
                                                "updated_at": NOW.isoformat(), "sent_at": NOW.isoformat()})
    assert r.reason_code == "" and r.reason == "" and r.sent_at == NOW
    for over in ({"status": "refused"}, {"reason_code": "duplicate"}, {"reason": "x" * 301},
                 {"extra": 1}, {"message_id": "msg-x"}):
        with pytest.raises(ValidationError):
            gi.SupportMessageResult.model_validate({"message_id": MID, "status": "failed",
                                                    "updated_at": NOW.isoformat(), **over})
    assert gi.SupportMessageResult.model_validate({"message_id": MID, "status": "failed", "reason_code": "expired",
                                                   "updated_at": NOW.isoformat()}).sent_at is None


def test_limite_por_hora():
    assert gi.SUPPORT_MESSAGES_PER_HOUR == 20


def test_nomes_exportados_que_o_gaibo_usa():
    for name in ("clean_subject", "clean_description", "SupportMessageStatus", "SupportMessageReasonCode",
                 "MAX_SUBJECT_LEN", "MAX_DESCRIPTION_LEN"):
        assert hasattr(gi, name), name


# ── do PR #7 da equipa GAIBO (Giovanni, 2 Nov 2026) ─────────────────────────

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


def test_destino_nunca_vem_do_ficheiro():
    with pytest.raises(ValidationError):
        gi.SupportMessage.model_validate(_msg(to="outra@x.pt"))          # o destino é do Studio
