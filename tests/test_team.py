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


# ── v0.1.121: quem pode usar o assistente (saída limpa) ──────────────────────

def test_entrada_por_omissao_qualquer_conta():
    assert T.ProfileTeam().entry == "anyone"
    assert T.ProfileTeam(entry="team").entry == "team"
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        T.ProfileTeam(entry="todos")
    assert EXPOSURE["team.entry"] == "client_write"
    for loc in ("pt-PT", "en-GB"):
        t = text_for("team.entry", loc)
        assert t and t.get("label") and len(t.get("help") or "") <= 240


# ── v0.1.122: F2 — CVs, Atas, Ferramentas de documentos e «Ver a fila» ──────

def test_areas_novas_desligadas_por_omissao():
    m = T.TeamModules()
    assert (m.cv, m.minutes, m.documents) == (False, False, False)
    assert {T.MODULE_CV, T.MODULE_MINUTES, T.MODULE_DOCUMENTS} <= set(T.MODULES)


def test_areas_novas_pelas_ferramentas():
    base = {"team": {"enabled": True, "modules": {"cv": True, "documents": True}}}
    loja = {"tools": {"enabled": ["analyse_cv", "transcribe_audio", "generate_boq"]}}
    a = _areas(base, {"loja": loja})
    assert a["cv"] == (True, True) and a["minutes"] == (True, False) and a["documents"] == (True, True)
    assert _areas({"tools": {"enabled": ["extract_invoice"]}})["documents"] == (True, False)
    # Só o interruptor da transcrição ao vivo, sem a ferramenta: o core não a liga.
    assert _areas({"audio": {"live_transcription_enabled": True}})["minutes"] == (False, False)
    # Equipa desligada: nunca «gerida».
    off = {"tools": {"enabled": ["analyse_cv"]}, "team": {"enabled": False, "modules": {"cv": True}}}
    assert _areas(off)["cv"] == (True, False)


def test_papeis_prontos_novos():
    def caps(module, rid):
        return next(r["capabilities"] for r in T.role_templates(module) if r["id"] == rid)
    assert caps(T.MODULE_QUEUES, "consulta-fila") == ["queue.view"]
    assert caps(T.MODULE_QUEUES, "operador-fila") == ["queue.operate"]
    assert caps(T.MODULE_CV, "recrutador") == ["cv.use"]
    assert caps(T.MODULE_MINUTES, "utilizador-atas") == ["minutes.use"]
    assert caps(T.MODULE_DOCUMENTS, "utilizador-documentos") == ["documents.use"]
    # «Ver a fila» aceita uma fila como alvo, como «Tratar».
    assert T.team_problems({"team": {"roles": [{"id": "a", "capabilities": ["queue.view:reclamacoes"]}]}}) == []


def test_area_nova_ligada_sem_papel_avisa():
    p = T.team_problems({"team": {"enabled": True, "modules": {"minutes": True},
                                  "roles": [{"id": "g", "capabilities": ["team.manage"]}]}})
    assert {"role_id": "minutes", "code": "module_without_role", "severity": "warning"} in p


def test_textos_de_todas_as_capacidades_cabem_no_popover_do_gaibo():
    """O GAIBO mostra a ajuda num popover de 240 caracteres (ui_text.CLIENT_HELP_MAX_CHARS)."""
    from genesis_profile_schema.ui_text import CLIENT_HELP_MAX_CHARS
    for c in T.CAPABILITIES:
        for lang in ("pt", "en"):
            assert 0 < len(c["label"][lang]) <= 60, (c["id"], lang)
            assert 0 < len(c["help"][lang]) <= CLIENT_HELP_MAX_CHARS, (c["id"], lang)


def test_textos_das_areas_novas():
    for m in ("cv", "minutes", "documents", "queues"):
        path = f"team.modules.{m}"
        assert EXPOSURE[path] == "client_write"
        for loc in ("pt-PT", "en-GB"):
            t = text_for(path, loc)
            assert t and t.get("label") and 0 < len(t.get("help") or "") <= 240, (path, loc)
            if m != "queues":
                assert t.get("note"), (path, loc)          # o detalhe para o operador vai para a nota


# ── v0.1.123: fase 2 da «Saúde da equipa» — interruptor interno ─────────────

def test_fase2_desligada_e_so_da_genesis():
    assert T.ProfileTeam().insights_phase2 is False
    assert T.ProfileTeam(insights_phase2=True).insights_phase2 is True
    assert EXPOSURE["team.insights_phase2"] == "internal"
    for loc in ("pt-PT", "en-GB"):
        t = text_for("team.insights_phase2", loc)
        assert t and t.get("label") and len(t.get("help") or "") <= 240
