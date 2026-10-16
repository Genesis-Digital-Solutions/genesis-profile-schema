"""v0.1.114 — Equipa e papéis do produto (`team`)."""
from genesis_profile_schema import team as T
from genesis_profile_schema.client_profile_schema import ClientProfileSchema as ClientProfile
from genesis_profile_schema.exposure import EXPOSURE
from genesis_profile_schema.ui_text import text_for


def test_desligado_por_omissao_e_none_no_perfil():
    assert T.ProfileTeam().enabled is False and T.TeamModules().approvals is False
    assert ClientProfile().team is None


def test_papeis_prontos_validos_e_sem_problemas():
    roles = []
    for m in (T.MODULE_TEAM,) + T.MODULES:
        roles += T.role_templates(m)
    prof = {"team": {"enabled": True, "modules": {m: True for m in T.MODULES}, "roles": roles}}
    assert T.team_problems(prof) == []
    T.ProfileTeam(**prof["team"])


def test_problemas():
    def codes(roles, **team):
        return {p["code"] for p in T.team_problems({"team": {"roles": roles, **team}})}
    assert "invalid_role_id" in codes([{"id": "Mau Id", "capabilities": []}])
    assert "duplicate_role_id" in codes([{"id": "a", "capabilities": []}, {"id": "a", "capabilities": []}])
    assert "unknown_capability" in codes([{"id": "a", "capabilities": ["voar"]}])
    assert "invalid_target" in codes([{"id": "a", "capabilities": ["team.manage:x"]}])
    assert codes([{"id": "a", "capabilities": ["queue.operate:reclamacoes"]}]) == set()
    assert "invalid_entra" in codes([{"id": "a", "capabilities": [], "entra": {"groups": ["x"]}}])
    c = codes([{"id": "a", "capabilities": ["intake.view"]}], enabled=True, modules={"approvals": True})
    assert {"no_team_manager", "module_without_role"} <= c


def test_catalogo_com_textos_e_exposicao():
    for c in T.CAPABILITIES:
        assert c["label"]["pt"] and c["label"]["en"] and c["help"]["pt"] and c["help"]["en"]
    for path in ("team.enabled", "team.modules.queues", "team.roles.capabilities", "team.roles.entra.groups"):
        assert EXPOSURE[path] == "client_write"
        for loc in ("pt-PT", "en-GB"):
            t = text_for(path, loc)
            assert t and t.get("label") and len(t.get("help") or "") <= 240


# ── v0.1.120: áreas disponíveis e «Intake — Auditor» ─────────────────────────

def test_auditor_do_intake_igual_ao_papel_do_entra():
    from genesis_profile_schema.intake_schema import _default_roles, default_roles
    assert default_roles() == _default_roles() and default_roles() is not default_roles()
    caps = {f"intake.{c}" for c, names in default_roles().items() if "Intake.Auditor" in names}
    aud = next(r for r in T.role_templates(T.MODULE_INTAKE) if r["id"] == "intake-auditor")
    assert set(aud["capabilities"]) == caps == {"intake.view", "intake.export"}


def _areas(base, variants=None):
    return {a["id"]: (a["available"], a["managed"]) for a in T.team_areas(base, variants)}


def test_areas_nada_configurado():
    assert _areas({}) == {m: (False, False) for m in T.MODULES}
    assert _areas(None) == {m: (False, False) for m in T.MODULES}             # nunca levanta
    assert [a["id"] for a in T.team_areas({})] == list(T.MODULES)


def test_areas_pelo_base_e_pelas_variantes():
    base = {"intake": {"definitions": {"adequacao": {}}},
            "multiProfile": {"enabled": True, "slugs": ["rh"], "disabledSlugs": []},
            "team": {"enabled": True, "modules": {"intake": True, "queues": True}}}
    rh = {"frontend": {"features": {"reviewQueue": True}}, "tools": {"enabled": ["verify_documents"]},
          "actionRules": {"enabled": True, "rules": [{"mode": "confirm"}, {"mode": "approve"}]}}
    a = _areas(base, {"rh": rh})
    assert a["intake"] == (True, True) and a["variant_access"] == (True, False)
    assert a["queues"] == (True, True) and a["docver"] == (True, False) and a["approvals"] == (True, False)
    # sem as variantes, só o base conta
    assert _areas(base)["queues"] == (False, True)


def test_areas_casos_limite():
    assert _areas({"actionRules": {"enabled": False, "rules": [{"mode": "approve"}]}})["approvals"][0] is False
    assert _areas({"actionRules": {"enabled": True, "rules": [{"mode": "confirm"}]}})["approvals"][0] is False
    assert _areas({"multiProfile": {"enabled": True, "slugs": ["a"], "disabledSlugs": ["a"]}})["variant_access"][0] is False
    assert _areas({"multiProfile": {"enabled": False, "slugs": ["a"]}})["variant_access"][0] is False
    assert _areas({"intake": {"definitions": {}}})["intake"][0] is False
    assert _areas({"frontend": {"features": {"reviewQueue": "true"}}})["queues"][0] is False   # só True
    # equipa desligada → nada é gerido, mesmo com o interruptor do módulo
    assert _areas({"team": {"enabled": False, "modules": {"queues": True}}})["queues"][1] is False


def test_aprovacoes_tambem_pelos_limites():
    lim = {"actionRules": {"enabled": True, "rules": [{"mode": "confirm", "limits": [{"field": "x", "max": 1}]}]}}
    assert _areas(lim)["approvals"][0] is True                      # `over` por omissão = approve
    per = {"actionRules": {"enabled": True, "rules": [{"mode": "confirm", "period_limits": [{"over": "approve"}]}]}}
    assert _areas(per)["approvals"][0] is True
    blk = {"actionRules": {"enabled": True, "rules": [{"mode": "confirm", "limits": [{"over": "block"}],
                                                      "period_limits": [{}]}]}}
    assert _areas(blk)["approvals"][0] is False                     # período por omissão = block
