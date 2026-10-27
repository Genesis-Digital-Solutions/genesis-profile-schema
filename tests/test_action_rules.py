"""v0.1.109 (14 Out 2026): regras por ação do agente (`actionRules`).

Pack das Ações, F1. Desligado por omissão = comportamento de hoje; as regras que
dependem do resto do perfil devolvem problemas e nunca levantam."""
from genesis_profile_schema import action_rules as ar
from genesis_profile_schema.client_profile_schema import ClientProfileSchema
from genesis_profile_schema.exposure import EXPOSURE, CLIENT_WRITE


def _profile(rules, queues=None, servers=None):
    return {
        "actionRules": {"enabled": True, "rules": rules},
        # A fila de aprovação como o Studio a cria (F2 verifica a forma).
        "reviewQueues": queues if queues is not None else {"aprovacoes": ar.approval_queue_template()},
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
            "approval": {"queue": "aprovacoes", "roles": ["Acoes.Aprovador"]}}
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


# ── F2 (v0.1.113): aprovadores, prazo, emails e a fila de aprovação ─────────

def _approve_profile(approval, queue=None):
    from genesis_profile_schema.action_rules import approval_queue_template
    return {"actionRules": {"enabled": True, "rules": [
        {"id": "r1", "action": "erp.create_order", "mode": "approve", "approval": approval}]},
        "reviewQueues": {"aprov": queue if queue is not None else approval_queue_template()},
        "mcp": {"servers": [{"name": "erp"}]}}


def _f2_codes(profile):
    from genesis_profile_schema.action_rules import action_rules_problems
    return {p["code"] for p in action_rules_problems(profile)}


def test_f2_defaults_e_modelo():
    from genesis_profile_schema.action_rules import ActionRuleApproval
    a = ActionRuleApproval(queue="aprov")
    assert a.roles == [] and a.groups == [] and a.expires_hours == 24 and a.notify_emails == []


def test_f2_template_da_fila_e_valido_e_reconhecido():
    from genesis_profile_schema.action_rules import approval_queue_shape_ok, approval_queue_template
    from genesis_profile_schema.client_profile_schema import ProfileReviewQueue
    from genesis_profile_schema.field_definition import FieldDefinition
    t = approval_queue_template()
    ProfileReviewQueue(**t)
    for f in t["fields"]:
        FieldDefinition(**f)
        assert f["editable"] is False                       # nunca se editam
    assert approval_queue_shape_ok(t)
    t2 = approval_queue_template()
    t2["actions"] = [a for a in t2["actions"] if a["id"] != "expire"]
    assert not approval_queue_shape_ok(t2)


def test_f2_problemas():
    ok = {"queue": "aprov", "roles": ["Acoes.Aprovador"]}
    assert _f2_codes(_approve_profile(ok)) == set()
    assert "approve_without_approvers" in _f2_codes(_approve_profile({"queue": "aprov"}))
    assert _f2_codes(_approve_profile({"queue": "aprov", "groups": ["0b1c2d3e-0000-4000-8000-000000000001"]})) == set()
    assert "invalid_approver" in _f2_codes(_approve_profile({"queue": "aprov", "groups": ["não-é-guid"]}))
    assert "invalid_notify_email" in _f2_codes(_approve_profile({**ok, "notify_emails": ["x"]}))
    assert "approval_queue_shape" in _f2_codes(_approve_profile(ok, queue={"states": [], "actions": []}))


def test_f2_exposicao_e_textos():
    from genesis_profile_schema.exposure import EXPOSURE
    from genesis_profile_schema.ui_text import text_for
    for f in ("roles", "groups", "expires_hours", "notify_emails"):
        path = f"actionRules.rules.approval.{f}"
        assert EXPOSURE[path] == "client_write"
        for loc in ("pt-PT", "en-GB"):
            t = text_for(path, loc)
            assert t and t.get("label") and len(t.get("help") or "") <= 240


# ── F4 (v0.1.116): limites por período ─────────────────────────────────────

def test_limites_por_periodo_validam():
    from genesis_profile_schema.action_rules import (
        INVALID_PERIOD_LIMIT, TOO_MANY_PERIOD_LIMITS, ActionRule, action_rules_problems)
    r = ActionRule(id="r1", action="erp.criar", period_limits=[{"period": "week", "per": "client", "max": 5000,
                                                              "sum_param": "total", "currency": "EUR"}])
    assert r.period_limits[0].over == "block" and r.period_limits[0].per == "client"

    def codes(pls):
        prof = {"actionRules": {"enabled": True, "rules": [{"id": "r1", "action": "create_ticket", "mode": "allow",
                                                            "period_limits": pls}]}}
        return {p["code"] for p in action_rules_problems(prof)}
    assert codes([{"period": "day", "per": "user", "max": 3}]) == set()
    assert INVALID_PERIOD_LIMIT in codes([{"period": "ano", "max": 3}])
    assert INVALID_PERIOD_LIMIT in codes([{"period": "day", "max": -1}])
    assert TOO_MANY_PERIOD_LIMITS in codes([{"period": "day", "max": 1}] * 6)


def test_aprovar_num_limite_por_periodo_pede_fila():
    from genesis_profile_schema.action_rules import APPROVE_WITHOUT_QUEUE, action_rules_problems
    prof = {"actionRules": {"enabled": True, "rules": [{"id": "r1", "action": "erp.create_order", "mode": "allow",
                                                        "period_limits": [{"period": "day", "max": 3,
                                                                           "over": "approve"}]}]}}
    assert APPROVE_WITHOUT_QUEUE in {p["code"] for p in action_rules_problems(prof)}


def test_retirar_template_e_filas_antigas():
    """v0.1.132: «retirado» — o template novo tem-no; uma fila criada antes
    ganha-o numa CÓPIA ao ler; uma fila editada com outra forma não se mexe."""
    import copy
    from genesis_profile_schema import action_rules as ar
    t = ar.approval_queue_template()
    assert ar.approval_queue_shape_ok(t) and ar.approval_queue_can_withdraw(t)
    # cópias: mexer num template não muda o seguinte
    t["actions"][-1]["from"].append("approved")
    assert ar.approval_queue_template()["actions"][-1]["from"] == ["pending"]
    # fila antiga (antes da v0.1.132)
    old = ar.approval_queue_template()
    old["states"] = [s for s in old["states"] if s["id"] != "withdrawn"]
    old["actions"] = [a for a in old["actions"] if a["id"] != "withdraw"]
    snap = copy.deepcopy(old)
    assert ar.approval_queue_shape_ok(old) and not ar.approval_queue_can_withdraw(old)
    up = ar.approval_queue_with_withdraw(old)
    assert ar.approval_queue_can_withdraw(up) and ar.approval_queue_shape_ok(up)
    assert old == snap                                   # o perfil lido não muda
    assert ar.approval_queue_with_withdraw(up) == up      # idempotente
    # uma fila que não é de aprovação volta igual
    other = {"states": [{"id": "novo", "kind": "open"}], "actions": []}
    assert ar.approval_queue_with_withdraw(other) == other
    # «retirar» editado para outro destino: não se acrescenta nem se aceita
    bad = ar.approval_queue_template()
    for a in bad["actions"]:
        if a["id"] == "withdraw":
            a["to"] = "approved"
    assert not ar.approval_queue_can_withdraw(ar.approval_queue_with_withdraw(bad))
    # «retirar» só a partir de pendente
    bad2 = ar.approval_queue_template()
    for a in bad2["actions"]:
        if a["id"] == "withdraw":
            a["from"] = ["approved"]
    assert not ar.approval_queue_can_withdraw(bad2)
