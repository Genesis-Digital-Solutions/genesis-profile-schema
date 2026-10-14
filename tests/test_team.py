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
