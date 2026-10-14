"""v0.1.115 — registo durável das ações (`actionLedger`, F3 do pack das Ações)."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.action_ledger import (
    GENESIS_HASH, ProfileActionLedger, entry_hash, ledger_policy, params_digest, verify_chain,
)
from genesis_profile_schema.client_profile_schema import ClientProfileSchema


def test_desligado_por_omissao_e_null_no_blob():
    p = ClientProfileSchema.model_validate({})
    assert p.actionLedger is None
    assert ClientProfileSchema.model_validate({"actionLedger": None}).actionLedger is None
    assert ledger_policy({}) == {"on": False, "required": False, "retention_days": 365}


def test_retencao_minima_de_seis_meses():
    with pytest.raises(ValidationError):
        ProfileActionLedger(retention_days=90)
    assert ProfileActionLedger().retention_days == 365


def test_alto_risco_regista_sempre_com_a_retencao_do_alto_risco():
    hi = {"compliance": {"classification": {"risk_level": "high"}, "high_risk": {"log_retention_days": 400}},
          "actionLedger": {"enabled": False, "retention_days": 200}}
    assert ledger_policy(hi) == {"on": True, "required": True, "retention_days": 400}
    hi2 = {"compliance": {"high_risk": {"enabled": True}}}
    assert ledger_policy(hi2)["required"] is True and ledger_policy(hi2)["retention_days"] == 365


def test_ligado_fora_do_alto_risco():
    p = {"actionLedger": {"enabled": True, "retention_days": 500}}
    assert ledger_policy(p) == {"on": True, "required": False, "retention_days": 500}
    assert ledger_policy({"actionLedger": {"enabled": True, "retention_days": "x"}})["retention_days"] == 365
    assert ledger_policy({"actionLedger": "lixo"})["on"] is False


def _chain(n):
    prev, out = GENESIS_HASH, []
    for i in range(1, n + 1):
        e = {"seq": i, "ts": 1000 + i, "client_id": "c", "variant_slug": "", "event": "executed",
             "action": "erp.criar", "actor": {"kind": "user", "id": "u"}, "ref": "act_1", "rule_id": "",
             "decision": "", "approver": None, "result": {"ok": True}, "params": {"total": i},
             "params_digest": params_digest({"total": i}), "prev_hash": prev}
        e["hash"] = entry_hash(prev, e)
        prev = e["hash"]
        out.append(e)
    return out


def test_cadeia_valida_e_rgpd_nao_a_parte():
    rows = _chain(4)
    assert verify_chain(rows) == {"ok": True, "checked": 4, "broken_at": None, "reason": ""}
    rows[1]["params"] = "[apagado]"                          # apagamento RGPD: só o digest conta
    assert verify_chain(rows)["ok"] is True


def test_cadeia_partida_diz_onde():
    rows = _chain(4)
    rows[2]["action"] = "erp.apagar"
    assert verify_chain(rows)["broken_at"] == 3 and verify_chain(rows)["reason"] == "hash_mismatch"
    rows = _chain(4)
    del rows[1]
    assert verify_chain(rows)["broken_at"] == 2 and verify_chain(rows)["reason"] == "missing_entry"
    rows = _chain(3)
    assert verify_chain(rows[1:], start_prev=rows[0]["hash"])["ok"] is True
