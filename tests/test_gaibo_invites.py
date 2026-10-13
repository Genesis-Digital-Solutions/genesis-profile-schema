"""Convites da Equipa do GAIBO pela caixa de saída (v0.1.108)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from genesis_profile_schema import gaibo_index as gi

NOW = datetime(2026, 10, 13, 22, 0, tzinfo=timezone.utc)


def _req(**over):
    base = {"invite_id": "inv-abcdefgh12", "client_id": "remax-v2-prod", "requested_at": NOW.isoformat(),
            "requested_by_ref": "u-123", "email": "Ana.Silva@Remax.PT", "display_name": "Ana  Silva"}
    base.update(over)
    return base


def test_pedido_valido_normaliza_email_e_nome():
    r = gi.InviteRequest.model_validate(_req())
    assert r.email == "ana.silva@remax.pt" and r.display_name == "Ana Silva" and r.schema_version == 1


@pytest.mark.parametrize("email", ["sem-arroba", "a@b", "a b@x.pt", "a@x..pt", "<a>@x.pt", "a@-x.pt",
                                   "a\"@x.pt", "x" * 65 + "@x.pt", "a@" + "b" * 250 + ".pt", ""])
def test_email_que_nao_serve_para_convite(email):
    assert gi.normalize_email(email) is None
    with pytest.raises(ValidationError):
        gi.InviteRequest.model_validate(_req(email=email or "x"))


def test_nome_com_html_ou_controlo_recusa():
    for bad in ("<script>", "Ana\x00", "a\nb>"):
        with pytest.raises(ValidationError):
            gi.InviteRequest.model_validate(_req(display_name=bad))


def test_contrato_fechado_e_ids():
    with pytest.raises(ValidationError):
        gi.InviteRequest.model_validate(_req(role="admin"))          # nada além do email e do nome
    with pytest.raises(ValidationError):
        gi.InviteRequest.model_validate(_req(invite_id="pr-abcdefgh12"))
    with pytest.raises(ValidationError):
        gi.InviteRequest.model_validate(_req(requested_at="2026-10-13T22:00:00"))   # sem fuso
    assert gi.is_valid_invite_id("inv-abcdefgh") and not gi.is_valid_invite_id("inv-ABC")
    assert gi.invite_blob("inv-abcdefgh12") == "invites/inv-abcdefgh12.json"
    assert gi.invite_result_blob("inv-abcdefgh12") == "invite-results/inv-abcdefgh12.json"
    with pytest.raises(ValueError):
        gi.invite_blob("../x")


def test_resultado():
    res = gi.InviteResult(invite_id="inv-abcdefgh12", status="refused", updated_at=NOW,
                          reason_code="genesis_tenant", reason="cliente no tenant da Genesis")
    assert res.model_dump(mode="json")["status"] == "refused"
    with pytest.raises(ValidationError):
        gi.InviteResult(invite_id="inv-abcdefgh12", status="ok", updated_at=NOW)
    with pytest.raises(ValidationError):
        gi.InviteResult(invite_id="inv-abcdefgh12", status="failed", updated_at=NOW, reason_code="outro")


def test_prefixos_nao_colidem_com_os_da_publicacao():
    assert gi.INVITES_PREFIX == "invites/" and gi.INVITE_RESULTS_PREFIX == "invite-results/"
    others = (gi.REQUESTS_PREFIX, gi.RESULTS_PREFIX, gi.RUNS_PREFIX)
    assert all(not p.startswith(o) and not o.startswith(p)
               for p in (gi.INVITES_PREFIX, gi.INVITE_RESULTS_PREFIX) for o in others)
    assert gi.INVITES_PER_HOUR == 20
