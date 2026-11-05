"""tests/test_untrusted_values.py — v0.1.158 (5 Nov 2026): defesa contra prompt
injection ao nível do VALOR — `actionRules.untrusted_values.mode`, os
`sensitive_params` da regra, a cadeia v4 do registo (`provenance_digest`) e a forma
fechada do registo de proveniência."""

from genesis_profile_schema import action_ledger as al
from genesis_profile_schema import action_rules as ar
from genesis_profile_schema.client_profile_schema import ClientProfileSchema
from genesis_profile_schema.exposure import EXPOSURE


# ── modo ────────────────────────────────────────────────────────────────────

def test_modo_por_omissao_e_so_registar():
    assert ar.untrusted_values_mode({}) == "log"
    assert ar.untrusted_values_mode(None) == "log"
    assert ar.untrusted_values_mode({"untrusted_values": None}) == "log"
    assert ar.untrusted_values_mode({"untrusted_values": {"mode": None}}) == "log"
    assert ar.untrusted_values_mode({"untrusted_values": {}}) == "log"


def test_modo_valido_e_desconhecido_falha_fechado():
    for m in ("off", "log", "approve"):
        assert ar.untrusted_values_mode({"untrusted_values": {"mode": m}}) == m
    assert ar.untrusted_values_mode({"untrusted_values": {"mode": "whatever"}}) == "approve"


def test_modelo_aceita_o_bloco_e_o_campo_da_regra():
    m = ClientProfileSchema.model_validate({"actionRules": {
        "enabled": True, "untrusted_values": {"mode": "approve"},
        "rules": [{"id": "r1", "action": "sap.create_vendor", "mode": "allow",
                   "sensitive_params": ["bank.iban", "amount"]}]}})
    assert m.actionRules.untrusted_values.mode == "approve"
    assert m.actionRules.rules[0].sensitive_params == ["bank.iban", "amount"]
    assert ClientProfileSchema.model_validate({"actionRules": {"enabled": True}}).actionRules.untrusted_values is None


def test_exposicao():
    assert EXPOSURE["actionRules.rules.sensitive_params"] == "client_write"
    assert EXPOSURE["actionRules.untrusted_values.mode"] == "client_read"


def test_sensitive_params_of_limpa_e_corta():
    rule = {"sensitive_params": [" bank.iban ", "bank.iban", "x y", "", "a.b.c", 3]}
    assert ar.sensitive_params_of(rule) == ["bank.iban", "a.b.c", "3"]
    assert ar.sensitive_params_of({"sensitive_params": "iban"}) == []
    assert len(ar.sensitive_params_of({"sensitive_params": [f"p{i}" for i in range(50)]})) == ar.MAX_SENSITIVE_PARAMS


# ── problemas ───────────────────────────────────────────────────────────────

def _profile(rule, mode="approve"):
    return {"mcp": {"servers": [{"name": "sap"}]},
            "actionRules": {"enabled": True, "untrusted_values": {"mode": mode}, "rules": [rule]}}


def _codes(profile):
    return {p["code"] for p in ar.action_rules_problems(profile)}


def test_campo_sensivel_invalido_e_erro():
    assert ar.INVALID_SENSITIVE_PARAM in _codes(_profile(
        {"id": "r1", "action": "sap.x", "mode": "allow", "sensitive_params": ["a b"]}))
    assert ar.INVALID_SENSITIVE_PARAM in _codes(_profile(
        {"id": "r1", "action": "sap.x", "mode": "allow", "sensitive_params": "iban"}))
    assert ar.INVALID_SENSITIVE_PARAM not in _codes(_profile(
        {"id": "r1", "action": "sap.x", "mode": "allow", "sensitive_params": ["bank.iban"]}))


def test_permitir_sem_aprovadores_avisa_so_no_modo_aprovar():
    rule = {"id": "r1", "action": "sap.x", "mode": "allow"}
    assert ar.UNTRUSTED_BLOCKS_WITHOUT_APPROVAL in _codes(_profile(rule))
    assert ar.UNTRUSTED_BLOCKS_WITHOUT_APPROVAL not in _codes(_profile(rule, mode="log"))
    with_appr = dict(rule, approval={"queue": "aprovacoes", "roles": ["Aprovador"]})
    assert ar.UNTRUSTED_BLOCKS_WITHOUT_APPROVAL not in _codes(_profile(with_appr))
    # Ações nativas não passam pelo agente operador.
    assert ar.UNTRUSTED_BLOCKS_WITHOUT_APPROVAL not in _codes(_profile(dict(rule, action="create_ticket")))


def test_modo_desconhecido_e_erro():
    p = _profile({"id": "r1", "action": "sap.x", "mode": "approve"}, mode="sometimes")
    assert ar.INVALID_UNTRUSTED_MODE in _codes(p)


# ── cadeia v4 ───────────────────────────────────────────────────────────────

def _chain(entries_fields):
    out, prev = [], al.GENESIS_HASH
    for i, f in enumerate(entries_fields, start=1):
        e = dict(f, seq=i, client_id="cli", expires_at=10_000 + i, prev_expires_at=None if i == 1 else 10_000 + i - 1)
        e["prev_hash"] = prev
        e["hash"] = al.entry_hash(prev, e)
        prev = e["hash"]
        out.append(e)
    return out


V1 = {"ts": 1, "variant_slug": "", "event": "executed", "action": "erp.create", "actor": {"kind": "agent", "digest": "d"},
      "ref": "rq_1", "rule_id": "", "decision": "", "approver": None, "result": {"ok": True}, "params_digest": "p"}
V3 = dict(V1, chain_v=3, mission_s256=None, effect_digest=None, why_digest=None)
REC = al.provenance_record({"outcome": "approval", "findings": [
    {"param": "iban", "kind": "iban", "origin": "untrusted", "masked": "PT50…0154", "sources": ["item_email"]}]})
V4 = dict(V3, chain_v=4, provenance_digest=al.salted_digest("s", REC))


def test_v4_acrescenta_um_campo_e_mistas_verificam():
    assert al.CHAIN_V == 4
    assert al.CHAIN_FIELDS_V4 == al.CHAIN_FIELDS_V3 + ("provenance_digest",)
    assert "provenance_digest" in al.CHAIN_FIELDS_ALL
    assert "provenance" in al.ERASABLE_FIELDS
    out = al.verify_chain(_chain([V1, V3, V4, dict(V4, provenance_digest=None)]))
    assert out["ok"] is True and out["checked"] == 4


def test_mexer_na_proveniencia_parte_e_passar_por_v3_parte():
    entries = _chain([V3, V4])
    entries[1]["provenance_digest"] = al.salted_digest("s", {"x": 1})
    assert al.verify_chain(entries)["reason"] == "hash_mismatch"
    entries = _chain([V4])
    entries[0]["chain_v"] = 3
    assert al.verify_chain(entries)["reason"] == "hash_mismatch"


def test_apagar_a_proveniencia_nao_parte():
    entries = _chain([V4])
    entries[0].update(provenance=al.ERASED, salt={"provenance": al.ERASED})
    assert al.verify_chain(entries)["ok"] is True


# ── forma do registo ────────────────────────────────────────────────────────

def test_registo_forma_fechada():
    rec = al.provenance_record({"outcome": "approval", "extra": "x", "findings": [
        {"param": "iban", "kind": "iban", "origin": "untrusted", "masked": "PT50…0154",
         "sources": ["item_email", "item_email", "attachment"], "value": "PT50000201231234567890154"},
        {"param": "x", "origin": "trusted"},
        "lixo"]})
    assert rec == {"v": 1, "outcome": "approval", "findings": [
        {"param": "iban", "kind": "iban", "origin": "untrusted", "masked": "PT50…0154",
         "sources": ["attachment", "item_email"]}]}


def test_registo_sem_achados_e_none_e_outcome_desconhecido_vira_logged():
    assert al.provenance_record(None) is None
    assert al.provenance_record({"findings": []}) is None
    rec = al.provenance_record({"outcome": "?", "findings": [{"param": "a", "origin": "unknown"}]})
    assert rec["outcome"] == "logged"


def test_registo_tira_controlos_e_corta():
    rec = al.provenance_record({"findings": [{"param": "a\nb" + "x" * 500, "origin": "unknown", "masked": "\x00m"}]})
    f = rec["findings"][0]
    assert "\n" not in f["param"] and len(f["param"]) == 200 and f["masked"] == " m"
    many = al.provenance_record({"findings": [{"param": str(i), "origin": "unknown"} for i in range(40)]})
    assert len(many["findings"]) == al.PROVENANCE_MAX_FINDINGS
