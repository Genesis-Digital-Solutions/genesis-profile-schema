"""tests/test_action_ledger_chain_v3.py — a cadeia v3 do registo de ações (v0.1.155,
5 Nov 2026, passo 5A do épico «Agente colega»): `effect_digest` (o efeito que o
sistema devolveu) e `why_digest` (a justificação do agente) nas entradas novas,
SEM partir as cadeias já escritas (v1, v2) nem as mistas."""

from genesis_profile_schema import action_ledger as al


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
V2 = dict(V1, chain_v=2, mission_s256=None)
V3 = dict(V1, chain_v=3, mission_s256=None, effect_digest=al.salted_digest("s1", "4500001234"),
          why_digest=al.salted_digest("s2", "O cliente pediu 10 kg"))


def test_listas_antigas_nao_mudaram_e_a_v3_acrescenta_dois():
    assert al.CHAIN_FIELDS_V2 == al.CHAIN_FIELDS + ("chain_v", "mission_s256")
    assert al.CHAIN_FIELDS_V3 == al.CHAIN_FIELDS_V2 + ("effect_digest", "why_digest")
    assert al.CHAIN_V == 3


def test_campos_de_todas_as_versoes_para_projecoes():
    assert set(al.CHAIN_FIELDS_ALL) == set(al.CHAIN_FIELDS_V3)
    assert len(al.CHAIN_FIELDS_ALL) == len(set(al.CHAIN_FIELDS_ALL))


def test_cadeia_mista_v1_v2_v3_verifica():
    out = al.verify_chain(_chain([V1, V2, V3, dict(V3, effect_digest=None, why_digest=None)]))
    assert out["ok"] is True and out["checked"] == 4


def test_mexer_no_efeito_ou_na_justificacao_parte():
    for field in ("effect_digest", "why_digest"):
        entries = _chain([V2, V3, V3])
        entries[1][field] = al.salted_digest("s1", "outra")
        out = al.verify_chain(entries)
        assert (out["ok"], out["broken_at"], out["reason"]) == (False, 2, "hash_mismatch")


def test_fazer_passar_uma_v3_por_v2_parte():
    entries = _chain([V3])
    entries[0]["chain_v"] = 2
    assert al.verify_chain(entries)["reason"] == "hash_mismatch"


def test_apagar_efeito_e_justificacao_nao_parte():
    entries = _chain([V3])
    entries[0].update(effect=al.ERASED, why=al.ERASED, salt={"effect": al.ERASED, "why": al.ERASED})
    assert al.verify_chain(entries)["ok"] is True
    assert {"effect", "why"} <= set(al.ERASABLE_FIELDS)


def test_effect_norm():
    assert al.effect_norm("0045000123") == "45000123"
    assert al.effect_norm(45000123) == "45000123"
    assert al.effect_norm("  FT 2026/12 ") == "FT 2026/12"
    assert al.effect_norm("000") == "0" and al.effect_norm("0") == "0" and al.effect_norm(0) == "0"
    assert al.effect_norm(True) == "" and al.effect_norm(None) == "" and al.effect_norm({"a": 1}) == ""
    assert len(al.effect_norm("x" * 500)) == al.EFFECT_REF_MAX
