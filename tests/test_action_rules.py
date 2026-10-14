"""v0.1.109 (14 Out 2026): regras por ação do agente (`actionRules`).

Pack das Ações, F1. Desligado por omissão = comportamento de hoje; as regras que
dependem do resto do perfil devolvem problemas e nunca levantam."""
from genesis_profile_schema import action_rules as ar
from genesis_profile_schema.client_profile_schema import ClientProfileSchema
from genesis_profile_schema.exposure import EXPOSURE, CLIENT_WRITE


def _profile(rules, queues=None, servers=None):
    return {
        "actionRules": {"enabled": True, "rules": rules},
        "reviewQueues": queues if queues is not None else {"aprovacoes": {}},
        "mcp": {"servers": servers if servers is not None else [
            {"name": "sap", "url": "https://x"},
            {"name": "crm", "url": "https://y", "auth": {"per_user": True}}]},
    }


def _codes(profile):
    return {(p["rule_id"], p["code"]) for p in ar.action_rules_problems(profile)}


def test_default_is_off_and_null_is_accepted():
    assert ClientProfileSchema.model_validate({"client_id": "x"}).actionRules is None
    assert ClientProfileSchema.model_validate({"client_id": "x", "actionRules": None}).actionRules is None
    p = ClientProfileSchema.model_validate({"client_id": "x", "actionRules": {}})
    assert p.actionRules.enabled is False and p.actionRules.rules == []


def test_null_in_the_blob_does_not_change_behaviour():
    # campo-opcional-novo-vira-null-no-blob: um null gravado vale o default.
    p = ClientProfileSchema.model_validate({"client_id": "x", "actionRules": {
        "enabled": False, "rules": [{"id": "r1", "action": "sap.erp_create_sales_order",
                                     "approval": None, "limits": []}]}})
    assert p.actionRules.rules[0].mode == "confirm"
    assert p.actionRules.rules[0].approval is None


def test_valid_rule_has_no_problems():
    rule = {"id": "encomendas-500", "action": "sap.erp_create_sales_order", "mode": "confirm",
            "limits": [{"param": "total", "op": "lte", "value": 500, "currency": "EUR",
                        "over": "approve"}],
            "approval": {"queue": "aprovacoes"}}
    assert ar.action_rules_problems(_profile([rule])) == []


def test_approve_needs_an_existing_queue():
    assert ("r1", ar.APPROVE_WITHOUT_QUEUE) in _codes(_profile(
        [{"id": "r1", "action": "sap.x", "mode": "approve"}]))
    assert ("r1", ar.UNKNOWN_QUEUE) in _codes(_profile(
        [{"id": "r1", "action": "sap.x", "mode": "approve", "approval": {"queue": "nao-existe"}}]))
    # um limite que manda aprovar também precisa de fila
    assert ("r1", ar.APPROVE_WITHOUT_QUEUE) in _codes(_profile(
        [{"id": "r1", "action": "sap.x", "limits": [{"param": "total", "op": "lte", "value": 5}]}]))


def test_approve_refused_on_per_user_server():
    assert ("r1", ar.APPROVE_PER_USER) in _codes(_profile(
        [{"id": "r1", "action": "crm.create_lead", "mode": "approve",
          "approval": {"queue": "aprovacoes"}}]))


def test_unknown_server_is_flagged_not_removed():
    probs = ar.action_rules_problems(_profile([{"id": "r1", "action": "xero.create_bill"}]))
    assert {"rule_id": "r1", "code": ar.UNKNOWN_SERVER, "severity": ar.WARNING} in probs


def test_native_action_has_no_server():
    assert ar.action_rules_problems(_profile([{"id": "r1", "action": "create_ticket",
                                               "mode": "block"}])) == []


def test_ids_and_limits():
    codes = _codes(_profile([
        {"id": "Mau Id", "action": "sap.x"},
        {"id": "r2", "action": "sap.x", "mode": "block"},
        {"id": "r2", "action": "sap.y", "mode": "block"},
        {"id": "r3", "action": "sap.x", "mode": "block",
         "limits": [{"param": "", "op": "lte", "value": 1, "over": "block"},
                    {"param": "estado", "op": "in", "value": "a", "over": "block"},
                    {"param": "total", "op": "gte", "value": "muito", "over": "block"},
                    {"param": "total", "op": "lte", "value": 1, "currency": "eur", "over": "block"}]},
    ]))
    assert ("Mau Id", ar.INVALID_ID) in codes
    assert ("r2", ar.DUPLICATE_ID) in codes
    assert ("r3", ar.INVALID_LIMIT) in codes
    assert ("r3", ar.IN_NEEDS_LIST) in codes
    assert ("r3", ar.NUMERIC_OP_ON_TEXT) in codes
    assert ("r3", ar.INVALID_CURRENCY) in codes


def test_never_raises():
    assert ar.action_rules_problems(None) == []
    assert ar.action_rules_problems({"actionRules": {"rules": "x"}}) == []
    assert ar.action_rules_problems({"actionRules": {"rules": [None]}})


def test_client_writes_the_block():
    paths = [k for k in EXPOSURE if k.startswith("actionRules.")]
    assert paths and all(EXPOSURE[k] == CLIENT_WRITE for k in paths)
    assert "mcp.confirm_actions" not in paths
