"""v0.1.115 — registo durável das ações (`actionLedger`, F3 do pack das Ações)."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.action_ledger import (
    ERASED, GENESIS_HASH, ProfileActionLedger, chain_start, entry_hash, ledger_policy, params_digest,
    result_code, salted_digest, verify_chain,
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
             "salt": f"s{i}", "params_digest": params_digest({"total": i}, f"s{i}"), "prev_hash": prev}
        e["hash"] = entry_hash(prev, e)
        prev = e["hash"]
        out.append(e)
    return out


def test_cadeia_valida_e_rgpd_nao_a_parte():
    rows = _chain(4)
    r = verify_chain(rows)
    assert (r["ok"], r["checked"], r["broken_at"], r["last_seq"]) == (True, 4, None, 4)
    rows[1].update(params=ERASED, salt=ERASED, who=ERASED)   # apagamento RGPD: só o digest conta
    assert verify_chain(rows)["ok"] is True


def test_sal_torna_o_digest_impossivel_de_adivinhar():
    assert params_digest({"total": 500}, "a") != params_digest({"total": 500}, "b")
    assert salted_digest("x", "ana@x.pt") != salted_digest("", "ana@x.pt")


def test_cadeia_partida_diz_onde():
    rows = _chain(4)
    rows[2]["action"] = "erp.apagar"
    assert verify_chain(rows)["broken_at"] == 3 and verify_chain(rows)["reason"] == "hash_mismatch"
    rows = _chain(4)
    del rows[1]
    assert verify_chain(rows)["broken_at"] == 2 and verify_chain(rows)["reason"] == "missing_entry"
    rows = _chain(3)
    assert verify_chain(rows[1:], start_prev=rows[0]["hash"])["ok"] is True



def test_verificar_por_paginas():
    rows = _chain(6)
    a = verify_chain(rows[:3])
    b = verify_chain(rows[3:], start_prev=a["last_hash"], expect_seq=a["last_seq"] + 1)
    assert a["ok"] and b["ok"] and b["checked"] == 3
    c = verify_chain(rows[4:], start_prev=a["last_hash"], expect_seq=a["last_seq"] + 1)
    assert c["ok"] is False and c["broken_at"] == 4 and c["reason"] == "missing_entry"


def test_inicio_expirado_vs_tirado():
    rows = _chain(3)
    first = dict(rows[1], prev_expires_at=100)
    assert chain_start(first, now=200)["ok"] is True                       # a anterior já expirou
    assert chain_start(first, now=50) == {"ok": False, "start_prev": "", "reason": "missing_entry"}
    assert chain_start(dict(rows[1], prev_expires_at=None), now=200)["ok"] is False
    assert chain_start(rows[0], now=0)["start_prev"] == GENESIS_HASH


def test_codigo_do_resultado_nunca_e_a_mensagem():
    assert result_code("timeout") == "timeout"
    assert result_code("Cliente 'Ana Silva' NIF 123 não existe") == "error"
    assert result_code("") == ""


def test_evento_checked_da_releitura_do_sistema():
    """v0.1.131 (A2 do core agêntico): a releitura depois de uma escrita."""
    from genesis_profile_schema.action_ledger import EVENTS, result_code
    assert "checked" in EVENTS
    for code in ("verified", "unverified", "contradicted"):
        assert result_code(code) == code
