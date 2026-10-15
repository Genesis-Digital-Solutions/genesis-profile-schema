"""approve numa ação nativa (sem servidor MCP) é erro (15 Out 2026) — o core bloqueia-a sempre."""
from genesis_profile_schema.action_rules import action_rules_problems


def _codes(rule):
    return {p["code"] for p in action_rules_problems({"actionRules": {"rules": [rule]}})}


def test_approve_em_acao_nativa_e_erro_e_nao_pede_fila():
    codes = _codes({"id": "r1", "action": "create_ticket", "mode": "approve"})
    assert "approve_native" in codes
    assert "approve_without_queue" not in codes and "approve_without_approvers" not in codes


def test_confirm_em_acao_nativa_nao_e_erro():
    assert "approve_native" not in _codes({"id": "r1", "action": "create_ticket", "mode": "confirm"})


def test_approve_em_acao_de_conector_continua_a_pedir_fila():
    codes = _codes({"id": "r1", "action": "erp.create_order", "mode": "approve"})
    assert "approve_native" not in codes and "approve_without_queue" in codes
