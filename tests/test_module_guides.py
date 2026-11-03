"""Percursos de configuração por módulo (v0.1.140): a fonte única do ecrã guiado, do manual,
do agente do Studio e do backoffice do cliente."""

import copy
import json
from importlib import resources

import pytest

from genesis_profile_schema import module_guides as mg


def _raw(module="review_queues"):
    folder = resources.files("genesis_profile_schema").joinpath("module_guides")
    return json.loads(folder.joinpath(f"{module}.json").read_text(encoding="utf-8"))


def test_todos_os_percursos_carregam():
    guides = mg.list_guides()
    assert [g["module"] for g in guides] == ["ingest", "review_queues", "intake", "cv_screening", "doc_verification",
                                             "retrieval", "auth", "audio"]


def test_filas_cobrem_todos_os_campos_de_uma_fila():
    from genesis_profile_schema.client_profile_schema import ProfileReviewQueue
    g = mg.get_guide("review_queues")
    placed = {f for s in g["steps"] for f in s.get("essential", []) + s.get("advanced", [])}
    assert placed == set(ProfileReviewQueue.model_fields) | set(g["item_extras"])


def test_filas_comecam_pelo_caso_e_acabam_no_rever():
    steps = mg.get_guide("review_queues")["steps"]
    assert steps[0]["kind"] == "cases" and steps[-1]["kind"] == "review"


def test_ligacoes_vistas_dos_dois_lados():
    into_queue = {l["key"]: l for l in mg.links_for("review_queues")}
    assert into_queue["ingest_email"]["direction"] == "in"
    from_ingest = mg.links_for("ingest")
    assert ("ingest_email", "out", "review_queues") in [(l["key"], l["direction"], l["module"]) for l in from_ingest]


def test_copias():
    g = mg.get_guide("review_queues")
    g["steps"].clear()
    assert mg.get_guide("review_queues")["steps"]


def _invalid(mutate, match):
    doc = _raw()
    mutate(doc)
    with pytest.raises(ValueError, match=match):
        mg._check(doc, "review_queues.json")


def test_campo_inexistente():
    _invalid(lambda d: d["steps"][1]["essential"].append("inventado"), "não existem")


def test_campo_sem_passo():
    def drop(d):
        for s in d["steps"]:
            for part in ("essential", "advanced"):
                if "sla" in s.get(part, []):
                    s[part].remove("sla")
    _invalid(drop, "sem passo")


def test_campo_em_dois_passos():
    _invalid(lambda d: d["steps"][2].setdefault("essential", []).append("label"), "dois passos")


def test_texto_so_numa_lingua():
    _invalid(lambda d: d["steps"][1]["title"].pop("en"), "en")


def test_ligacao_inexistente_num_passo():
    _invalid(lambda d: d["steps"][2]["links"].append("fantasma"), "ligações inexistentes")


def test_caminho_de_ligacao_inexistente():
    _invalid(lambda d: d["links"][0].update(path="ingest.inventado.queue"), "caminhos inexistentes")


def test_caso_inexistente_na_condicao():
    def bad(d):
        for s in d["steps"]:
            if s["key"] == "erp":
                s["show_if"]["case_in"] = ["fantasma"]
    _invalid(bad, "casos inexistentes")


def test_nome_do_ficheiro_tem_de_bater():
    with pytest.raises(ValueError, match="nome do ficheiro"):
        mg._check(copy.deepcopy(_raw()), "outro.json")


# ── predefinições (geradas pelo editor do Studio; paridade lá) ──────────────

def _preset_raw(name="review_queues.simple.pt.json"):
    folder = resources.files("genesis_profile_schema").joinpath("module_guides").joinpath("presets")
    return json.loads(folder.joinpath(name).read_text(encoding="utf-8"))


def _guides():
    return {g["module"]: g for g in mg.list_guides()}


def test_predefinicoes_das_filas_carregam_nas_duas_linguas():
    got = {(p["case"], p["lang"]) for p in mg.list_presets("review_queues")}
    assert got == {(c, l) for c in ("orders_erp", "citizen_requests", "simple") for l in ("pt", "en")}


def test_cada_caso_com_predefinicao_existe_no_percurso():
    cases = {c["key"] for c in mg.get_guide("review_queues")["cases"]}
    assert {p["case"] for p in mg.list_presets("review_queues")} <= cases


def test_get_preset_e_copia():
    p = mg.get_preset("review_queues", "citizen_requests", "en")
    assert p["item"]["states"][0]["label"] == "New"
    p["item"].clear()
    assert mg.get_preset("review_queues", "citizen_requests", "en")["item"]


def test_encomendas_deixa_o_servidor_do_erp_para_uma_pessoa():
    assert mg.get_preset("review_queues", "orders_erp", "pt")["human"] == ["onValidate.server"]


@pytest.mark.parametrize("mutate,match", [
    (lambda d: d.update(case="fantasma"), "nome diferente|caso inexistente"),
    (lambda d: d.update(links=["fantasma"]), "ligações inexistentes"),
    (lambda d: d["item"].update(states=[{"id": "x", "kind": "inventado"}]), "kind"),
    (lambda d: d.update(key="Maiúsculas"), "key"),
])
def test_predefinicao_invalida(mutate, match):
    doc = _preset_raw()
    mutate(doc)
    name = f"{doc['module']}.{doc['case']}.{doc['lang']}.json"
    with pytest.raises(ValueError, match=match):
        mg._check_preset(doc, name, _guides())


def test_condicao_ou_feito_com_gralha():
    _invalid(lambda d: d["steps"][1]["done_if"].append("labell"), "condições ou «feito»")


def test_extra_que_o_core_le_entra_num_passo():
    g = mg.get_guide("review_queues")
    assert g["item_extras"] == ["numberFields"]
    placed = [f for s in g["steps"] for f in s.get("essential", []) + s.get("advanced", [])]
    assert "numberFields" in placed


def test_preset_com_feature_ou_human_inexistente():
    doc = _preset_raw()
    doc["features"] = {"inventada": True}
    with pytest.raises(ValueError, match="features inexistentes"):
        mg._check_preset(doc, "review_queues.simple.pt.json", _guides())
    doc = _preset_raw()
    doc["human"] = ["inventado.server"]
    with pytest.raises(ValueError, match="human"):
        mg._check_preset(doc, "review_queues.simple.pt.json", _guides())


# ── Intake (31 Out 2026): um questionário de `intake.definitions` por item ──

def test_intake_cobre_todos_os_campos_de_um_questionario():
    from genesis_profile_schema.intake_schema import IntakeDefinition
    g = mg.get_guide("intake")
    placed = {f for s in g["steps"] for f in s.get("essential", []) + s.get("advanced", [])}
    assert placed == set(IntakeDefinition.model_fields)


def test_intake_casos_partem_da_biblioteca():
    from genesis_profile_schema import intake_library
    ids = {t["id"] for t in intake_library.list_templates()}
    cases = mg.get_guide("intake")["cases"]
    assert cases and all(c["preset"] in ids for c in cases)


def test_intake_regras_so_nos_casos_com_regras():
    from genesis_profile_schema import intake_library
    rules = mg.get_guide("intake")["steps"]
    step = next(s for s in rules if s["key"] == "rules")
    by_id = {t["id"]: t for t in intake_library.list_templates()}
    with_rules = {c["key"] for c in mg.get_guide("intake")["cases"]
                  if by_id[c["preset"]]["definition"].get("methodology")}
    assert set(step["show_if"]["case_in"]) == with_rules
    assert step["show_if"]["any_present"] == ["methodology"]


def test_intake_ligacoes_dos_dois_lados():
    assert [(l["key"], l["direction"], l["module"]) for l in mg.links_for("contacts")] == [
        ("contacts_timeline", "in", "intake")]


def test_preset_inexistente_na_biblioteca():
    doc = _raw("intake")
    doc["cases"][0]["preset"] = "nao_existe"
    with pytest.raises(ValueError, match="não existe na biblioteca"):
        mg._check(doc, "intake.json")


def test_preset_num_modulo_sem_biblioteca():
    doc = _raw()
    doc["cases"][0]["preset"] = "onboarding_kyc"
    with pytest.raises(ValueError, match="sem biblioteca"):
        mg._check(doc, "review_queues.json")


# ── Ingestão (31 Out 2026): uma fonte de `ingest.sources` por item ──

def test_ingestao_cobre_todas_as_chaves_que_o_core_le():
    from genesis_profile_schema.ingest_source import IngestSource
    g = mg.get_guide("ingest")
    placed = {f for s in g["steps"] for f in s.get("essential", []) + s.get("advanced", [])}
    assert placed == set(IngestSource.model_fields)


def test_ingestao_ligacoes_dos_dois_lados():
    got = {(l["key"], l["direction"], l["module"]) for l in mg.links_for("ingest")}
    assert got == {("aging_alerts", "out", "review_queues"), ("ingest_email", "out", "review_queues")}


def test_forma_da_fonte_ida_e_volta_sem_perder_nada():
    from genesis_profile_schema.ingest_source import IngestSource
    src = {"id": "enc", "mailbox": "a@b.pt", "queue": "encomendas", "transport": "imap", "imap": {"folder": "INBOX"},
           "accept": {"rules": [{"in": ["subject"], "contains": ["Omya"]}], "ocr": False},
           "extraction": {"schema": {"header": [{"key": "cliente", "hint": "h"}]}, "numbers_rule": "verbatim",
                          "reconcile": {"qty": "q"}, "attachments": {"ocr": "auto", "vision_dpi": 200}},
           "reply": {"enabled": True, "channel": "graph", "agent": {"enabled": True, "mode": "draft"}},
           "resolver": {"learn_from_operator": {"enabled": True, "ttl_days": 365}}, "chave_nova": 1}
    out = IngestSource.model_validate(src).model_dump(by_alias=True, exclude_none=True)
    assert out == src


# ── Triagem de CVs (1 Nov 2026): percurso de perfil sobre `tools.config.analyse_cv` ──

def test_cvs_cobrem_todos_os_campos_da_configuracao():
    from genesis_profile_schema import tool_config_models
    g = mg.get_guide("cv_screening")
    placed = {f.rsplit(".", 1)[1] for s in g["steps"] for f in s.get("essential", []) + s.get("advanced", [])}
    assert placed == set(tool_config_models()["analyse_cv"].model_fields)


def test_cvs_ligacoes_aos_modulos_de_que_dependem():
    keys = {l["key"] for l in mg.get_guide("cv_screening")["links"]}
    assert keys == {"workspace", "login", "high_risk", "recruiters"}


def test_ligacao_com_valor_esperado():
    links = {l["key"]: l for l in mg.get_guide("cv_screening")["links"]}
    assert links["login"]["expects"] == "required" and links["high_risk"]["expects"] == "high"
    assert "expects" not in links["workspace"]


# ── Pesquisa (1 Nov 2026): percurso de perfil sobre `retrieval` ──

def test_pesquisa_cobre_todos_os_campos_lidos_pelo_core():
    from genesis_profile_schema.client_profile_schema import ProfileRetrieval
    g = mg.get_guide("retrieval")
    placed = {f.split(".", 1)[1] for s in g["steps"] for f in s.get("essential", []) + s.get("advanced", [])}
    # `min_score` fica fora de propósito: o core não o lê (campo morto).
    assert placed == set(ProfileRetrieval.model_fields) - {"min_score"}


def test_pesquisa_ferramenta_ligada_pelo_valor_esperado():
    link = next(l for l in mg.get_guide("retrieval")["links"] if l["key"] == "kb_tool")
    assert link["path"] == "tools.enabled" and link["expects"] == "search_knowledge_base"


# ── Autenticação (1 Nov 2026): percurso de perfil sobre `frontend.auth` + `access` ──

def test_autenticacao_cobre_todos_os_campos_do_login_e_do_acesso():
    from genesis_profile_schema import exposure
    g = mg.get_guide("auth")
    placed = {f for s in g["steps"] for f in s.get("essential", []) + s.get("advanced", [])}
    wanted = {p for p in exposure.leaf_paths() if p.startswith(("frontend.auth.", "access."))}
    assert placed == wanted


def test_autenticacao_so_a_equipa_pelo_valor_esperado():
    link = next(l for l in mg.get_guide("auth")["links"] if l["key"] == "team_only")
    assert link["path"] == "team.entry" and link["expects"] == "team"


def test_reunioes_e_atas():
    """O percurso «Reuniões e atas» (2 Nov 2026): o órgão só nos casos com formato legal, e a
    ligação das ações das atas à fila aparece dos dois lados (declarada uma vez, na fila)."""
    g = mg.get_guide("audio")
    steps = {s["key"]: s for s in g["steps"]}
    assert g["steps"][0]["kind"] == "cases" and g["steps"][-1]["kind"] == "review"
    assert set(steps["legal_model"]["show_if"]["case_in"]) == {"municipal", "public_body", "private_body"}   # F4
    # nada depende de um booleano «com valor» (no Studio um `false` gravado conta como valor)
    assert not steps["legal_model"]["show_if"].get("any_present") and not steps["live"].get("done_if")
    tool = [l for l in g["links"] if l["key"] == "tool"][0]
    assert tool["path"] == "tools.enabled" and tool["expects"] == "transcribe_audio"
    links = {(l["key"], l["direction"], l["module"]) for l in mg.links_for("audio")}
    assert ("minutes_items", "out", "review_queues") in links
    assert ("workspace", "in", "frontend") in links


# ── Verificação documental (3 Nov 2026): percurso de perfil sobre `tools.config.verify_documents` ──

def test_verificacao_cobre_todos_os_campos_da_configuracao():
    """Nenhum campo do módulo fica fora de um passo (nada sem ecrã)."""
    from genesis_profile_schema import tool_config_models
    g = mg.get_guide("doc_verification")
    placed = {f.rsplit(".", 1)[1] for s in g["steps"] for f in s.get("essential", []) + s.get("advanced", [])}
    assert placed == set(tool_config_models()["verify_documents"].model_fields)


def test_verificacao_casos_de_uso_e_o_que_esta_em_preparacao():
    g = mg.get_guide("doc_verification")
    cases = {c["key"]: c for c in g["cases"]}
    assert set(cases) == {"bidder", "support_applications", "tender_evaluation"}
    assert cases["tender_evaluation"]["available"] is False and "preset" not in cases["tender_evaluation"]
    assert cases["bidder"]["available"] is True
    raw = _raw("doc_verification")
    raw["cases"][2]["available"] = "false"
    with pytest.raises(ValueError):
        mg.ModuleGuide.model_validate(raw)
    assert g["steps"][0]["kind"] == "cases" and g["steps"][-1]["kind"] == "review"


def test_verificacao_ligacoes():
    links = {l["key"]: l for l in mg.get_guide("doc_verification")["links"]}
    assert set(links) == {"tool", "workspace", "login", "people"}
    assert links["tool"]["expects"] == "verify_documents" and links["login"]["expects"] == "required"
    assert links["people"]["path"] == "team.modules.docver"


def test_verificacao_predefinicoes_por_caso_disponivel():
    got = {(p["case"], p["lang"]): p for p in mg.list_presets("doc_verification")}
    assert set(got) == {(c, l) for c in ("bidder", "support_applications") for l in ("pt", "en")}
    assert got[("bidder", "pt")]["config"]["scheme"] == "concursos"
    assert got[("support_applications", "en")]["config"]["scheme"] == "fem"
    assert all(p["features"] == {"toolWorkspace": True} for p in got.values())


def test_caso_em_preparacao_nao_tem_predefinicao():
    raw = _raw("doc_verification")
    raw["cases"][2]["preset"] = "x"
    with pytest.raises(ValueError, match="em preparação"):
        mg.ModuleGuide.model_validate(raw)
    doc = mg.get_preset("doc_verification", "bidder", "pt")
    doc["case"] = "tender_evaluation"
    with pytest.raises(ValueError, match="em preparação"):
        mg._check_preset(doc, "doc_verification.tender_evaluation.pt.json", _guides())


@pytest.mark.parametrize("mutate,match", [
    (lambda d: d["config"].update(parallelism=99), "parallelism"),
    (lambda d: d.pop("config"), "falta `config`"),
    (lambda d: d.update(item={}), "só em módulos de mapa"),
    (lambda d: d.update(human=["fantasma"]), "`human`"),
    (lambda d: d["config"].update(paralelism=4), "campos inexistentes"),
    (lambda d: d.update(extra=1), "chaves desconhecidas"),
])
def test_predefinicao_de_perfil_invalida(mutate, match):
    doc = mg.get_preset("doc_verification", "support_applications", "pt")
    mutate(doc)
    with pytest.raises(ValueError, match=match):
        mg._check_preset(doc, "doc_verification.support_applications.pt.json", _guides())
