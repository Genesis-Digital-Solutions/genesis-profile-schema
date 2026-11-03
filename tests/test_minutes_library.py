"""tests/test_minutes_library.py — a biblioteca de modelos de ata (D11; prazos legais da F3.6/R10, 3 Nov 2026)."""

import pytest

from genesis_profile_schema import minutes_library as ml


def test_carrega_e_os_tipos_de_orgao_apontam_para_um_modelo():
    ids = [m["id"] for m in ml.list_models()]
    assert ids == ["associacao", "autarquia", "condominio", "ipss", "orgao_colegial", "sociedade_comercial"]
    for organ in ("camara_municipal", "assembleia_municipal", "junta_freguesia", "assembleia_freguesia"):
        assert ml.model_for_organ_type(organ)["id"] == "autarquia"
    assert ml.model_for_organ_type("orgao_colegial")["deadlines"] == []
    assert ml.model_for_organ_type("outro") is None


def test_prazos_da_lei_75_2013():
    d = {x["id"]: x for x in ml.get_model("autarquia")["deadlines"]}
    assert (d["edital"]["days"], d["edital"]["window"], d["edital"]["unit"]) == (10, 5, "calendar")
    assert d["publicacao"]["days"] == 30 and "art.º 56.º, n.º 2" in d["publicacao"]["law"]


def test_copias():
    m = ml.get_model("autarquia")
    m["deadlines"].clear()
    assert ml.get_model("autarquia")["deadlines"]


@pytest.mark.parametrize("bad", [
    {"id": "x", "from": "meeting_date", "days": 0, "unit": "calendar", "law": "L", "label": {"pt": "a", "en": "b"}},
    {"id": "x", "from": "meeting_date", "days": 5, "window": 6, "unit": "calendar", "law": "L", "label": {"pt": "a", "en": "b"}},
    {"id": "x", "from": "outro", "days": 5, "unit": "calendar", "law": "L", "label": {"pt": "a", "en": "b"}},
    {"id": "x", "from": "meeting_date", "days": 5, "unit": "semanas", "law": "L", "label": {"pt": "a", "en": "b"}},
    {"id": "x", "from": "meeting_date", "days": 5, "unit": "calendar", "law": "", "label": {"pt": "a", "en": "b"}},
    {"id": "x", "from": "meeting_date", "days": 5, "unit": "calendar", "law": "L", "label": {"pt": "a"}},
])
def test_prazo_invalido_rebenta_ao_carregar(bad):
    with pytest.raises(ValueError):
        ml._check({"id": "m", "name": {"pt": "a", "en": "b"}, "deadlines": [bad]}, "m.json")


# ── F4 (v0.1.146, 3 Nov 2026): os tipos de reunião por dados ──────────────────────────────────────────

def test_organ_type_do_perfil_e_a_biblioteca_sao_os_mesmos():
    from typing import get_args
    from genesis_profile_schema.client_profile_schema import ProfileMunicipalMinutes
    literal = set(get_args(ProfileMunicipalMinutes.model_fields["organ_type"].annotation))
    assert literal == set(ml.organ_types())
    assert len(ml.organ_types()) == len(set(ml.organ_types()))          # nenhum órgão em dois modelos


def test_todos_os_modelos_publicados_tem_regime_e_orgaos():
    for m in ml.list_models():
        assert m["family"] in ml.FAMILIES and m["organs"], m["id"]
        if m["family"] == "private":
            assert m["regime"] and m["member_term"] and m["rules"], m["id"]
        for o in m["organs"]:
            assert o["preside"] and o["signatures"] and o["roles"], o["id"]
            # quem preside tem de estar entre os cargos (senão a ata sai sempre «[PRESIDENTE A CONFIRMAR]»)
            cargos = [r.lower() for r in o["roles"]]
            assert any(c == p or c.startswith(p + " ") for p in o["preside"] for c in cargos), o["id"]


def test_peso_so_no_condominio_e_nas_sociedades():
    pesos = {m["id"]: (m.get("weight") or {}).get("unit") for m in ml.list_models()}
    assert pesos == {"associacao": None, "autarquia": None, "condominio": "permilagem", "ipss": None,
                     "orgao_colegial": None, "sociedade_comercial": "capital"}
    info = ml.organ_info("assembleia_condominos")
    assert info["model"] == "condominio" and info["family"] == "private" and info["weight"]["unit"] == "permilagem"
    assert ml.organ_info("nada") is None


def test_ipss_reproduz_a_deliberacao_na_integra_e_o_condominio_diz_presentes_e_ausentes():
    assert any("NA ÍNTEGRA" in r and "21.º-D" in r for r in ml.get_model("ipss")["rules"])
    assert any("presentes e os ausentes" in r for r in ml.get_model("condominio")["rules"])
    d = {x["id"]: x for x in ml.get_model("condominio")["deadlines"]}
    assert d["comunicacao_ausentes"]["days"] == 30


def test_membro_com_peso():
    from genesis_profile_schema.client_profile_schema import ProfileMunicipalMember
    assert ProfileMunicipalMember(name="A", weight=125.5).weight == 125.5
    assert ProfileMunicipalMember(name="A").weight is None
    with pytest.raises(Exception):
        ProfileMunicipalMember(name="A", weight=-1)


@pytest.mark.parametrize("bad", [
    {"family": "outra", "organs": []},
    {"family": "private", "organs": [{"id": "x", "label": {"pt": "a", "en": "b"}, "default_name": "X",
                                      "preside": ["p"], "roles": ["p"], "signatures": ["s"]}]},   # privado sem regime
    {"family": "public", "organs": [{"id": "x", "label": {"pt": "a", "en": "b"}, "default_name": "X",
                                     "preside": [], "roles": ["p"], "signatures": ["s"]}]},
    {"family": "public", "weight": {"unit": "votos"}, "organs": [{"id": "x", "label": {"pt": "a", "en": "b"},
                                     "default_name": "X", "preside": ["p"], "roles": ["p"], "signatures": ["s"]}]},
])
def test_regime_invalido_rebenta_ao_carregar(bad):
    with pytest.raises(ValueError):
        ml._check({"id": "m", "name": {"pt": "a", "en": "b"}, "deadlines": [], **bad}, "m.json")


def test_ca_e_gerencia_votam_por_cabeca_e_organ_info_e_copia():
    for organ in ("conselho_administracao", "gerencia"):
        i = ml.organ_info(organ)
        assert i["weight"] is None and i["member_term"] != "sócio"
        assert not any("capital" in r and "contam" in r for r in i["rules"])
    assert ml.organ_info("assembleia_geral_sq")["weight"]["unit"] == "capital"
    i = ml.organ_info("assembleia_condominos"); i["roles"].clear()
    assert ml.organ_info("assembleia_condominos")["roles"]
    assert any("164.º" in r for r in ml.organ_info("direcao_associacao")["rules"])
    assert not any("164.º" in r for r in ml.organ_info("assembleia_geral_associacao")["rules"])


_ORGAO = {"id": "x", "label": {"pt": "a", "en": "b"}, "default_name": "X", "preside": ["p"], "roles": ["p"],
          "signatures": ["s"]}
_PRAZO = {"id": "p1", "from": "meeting_date", "days": 5, "unit": "calendar", "law": "L",
          "label": {"pt": "a", "en": "b"}}


@pytest.mark.parametrize("bad", [
    {"family": "public", "organs": [_ORGAO, dict(_ORGAO)]},                                  # órgão repetido
    {"family": "public", "organs": [_ORGAO], "deadlines": [{**_PRAZO, "organs": ["y"]}]},     # prazo de outro órgão
    {"deadlines": [{**_PRAZO, "organs": ["x"]}]},                                              # prazo com órgãos sem órgãos
    {"weight": {"unit": "capital", "label": {"pt": "a", "en": "b"}}},                         # regime sem família
    {"family": "public"},                                                                      # família sem órgãos
    {"family": "public", "organs": [{**_ORGAO, "roles": ["p"] * (ml.MAX_LIST + 1)}]},          # lista sem limite
])
def test_modelo_a_meio_rebenta_ao_carregar(bad):
    with pytest.raises(ValueError):
        ml._check({"id": "m", "name": {"pt": "a", "en": "b"}, "deadlines": [], **bad}, "m.json")


def test_prazos_por_orgao():
    assert [d["id"] for d in ml.organ_info("assembleia_geral_ipss")["deadlines"]] == ["registo_iss"]
    assert ml.organ_info("administracao_ipss")["deadlines"] == []
    assert [d["id"] for d in ml.organ_info("camara_municipal")["deadlines"]] == ["edital", "publicacao"]
    assert [d["id"] for d in ml.organ_info("assembleia_condominos")["deadlines"]] == ["comunicacao_ausentes"]


def test_assinaturas_por_presente_so_as_marcadas():
    assert ml.organ_info("assembleia_geral_sq")["sign_each_present"] == ["Os sócios que participaram na reunião"]
    assert not ml.organ_info("assembleia_geral_associacao").get("sign_each_present")
    assert not ml.organ_info("assembleia_geral_ipss").get("sign_each_present")
    with pytest.raises(ValueError):
        ml._check({"id": "m", "name": {"pt": "a", "en": "b"}, "deadlines": [], "family": "public",
                   "organs": [{**_ORGAO, "sign_each_present": ["outra"]}]}, "m.json")
    with pytest.raises(ValueError):                                  # peso do órgão sem rótulo
        ml._check({"id": "m", "name": {"pt": "a", "en": "b"}, "deadlines": [], "family": "public",
                   "organs": [{**_ORGAO, "weight": {"unit": "capital"}}]}, "m.json")
