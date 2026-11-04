"""tests/test_action_ledger_chain_v2.py — a cadeia v2 do registo de ações (v0.1.153,
4 Nov 2026, passo 3 do épico «Agente colega»): `chain_v: 2` + `mission_s256` nas
entradas novas, SEM partir as cadeias já escritas (v1) nem as mistas."""

import base64
import hashlib

import pytest

from genesis_profile_schema import action_ledger as al


def _chain(entries_fields):
    """Monta uma cadeia como o core: cada entrada com seq, prev_hash e hash."""
    out, prev = [], al.GENESIS_HASH
    for i, f in enumerate(entries_fields, start=1):
        e = dict(f, seq=i, client_id="cli", expires_at=10_000 + i, prev_expires_at=None if i == 1 else 10_000 + i - 1)
        e["prev_hash"] = prev
        e["hash"] = al.entry_hash(prev, e)
        prev = e["hash"]
        out.append(e)
    return out


V1 = {"ts": 1, "variant_slug": "", "event": "executed", "action": "erp.create", "actor": {"kind": "user", "digest": "d"},
      "ref": "rq_1", "rule_id": "", "decision": "", "approver": None, "result": {"ok": True}, "params_digest": "p"}
S256 = al.mission_s256(b'{"agent":"aauth:base@x"}')


def test_a_lista_v1_nao_mudou():
    """O hash das entradas JÁ ESCRITAS depende desta lista: nunca muda."""
    assert al.CHAIN_FIELDS == ("seq", "ts", "client_id", "variant_slug", "event", "action", "actor", "ref",
                               "rule_id", "decision", "approver", "result", "params_digest",
                               "expires_at", "prev_expires_at")
    assert al.CHAIN_FIELDS_V2 == al.CHAIN_FIELDS + ("chain_v", "mission_s256")


def test_hash_de_uma_entrada_v1_e_o_de_sempre():
    e = dict(V1, seq=1, client_id="cli", expires_at=5, prev_expires_at=None)
    chained = {k: e.get(k) for k in al.CHAIN_FIELDS}
    expected = hashlib.sha256((al.GENESIS_HASH + "|" + al._canonical(chained)).encode("utf-8")).hexdigest()
    assert al.entry_hash(al.GENESIS_HASH, e) == expected


def test_cadeia_mista_verifica():
    entries = _chain([V1, V1, dict(V1, chain_v=2, mission_s256=None), dict(V1, chain_v=2, mission_s256=S256)])
    out = al.verify_chain(entries)
    assert out["ok"] is True and out["checked"] == 4


def test_mexer_na_missao_ou_tirar_a_versao_parte():
    entries = _chain([V1, dict(V1, chain_v=2, mission_s256=S256), V1])
    bad = [dict(e) for e in entries]
    bad[1]["mission_s256"] = al.mission_s256(b"outra")
    assert al.verify_chain(bad)["broken_at"] == 2
    stripped = [dict(e) for e in entries]
    del stripped[1]["chain_v"]                     # fazer passar uma v2 por v1
    out = al.verify_chain(stripped)
    assert (out["ok"], out["broken_at"], out["reason"]) == (False, 2, "hash_mismatch")


def test_versao_desconhecida_e_dita():
    entries = _chain([V1])
    entries[0]["chain_v"] = 3
    out = al.verify_chain(entries)
    assert out["ok"] is False and out["reason"] == "unknown_chain_version" and out["broken_at"] == 1
    with pytest.raises(al.UnknownChainVersion):
        al.entry_hash("x", {"chain_v": True})


def test_mission_s256_e_o_do_aauth():
    raw = b'{"a":1}'
    expected = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
    assert al.mission_s256(raw) == expected and al.MISSION_S256.fullmatch(expected) and len(expected) == 43
    assert not al.MISSION_S256.fullmatch(expected + "\n")
