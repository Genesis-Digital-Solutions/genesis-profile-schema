"""tests/test_minutes_library.py — a biblioteca de modelos de ata (D11; prazos legais da F3.6/R10, 3 Nov 2026)."""

import pytest

from genesis_profile_schema import minutes_library as ml


def test_carrega_e_os_tipos_de_orgao_apontam_para_um_modelo():
    ids = [m["id"] for m in ml.list_models()]
    assert ids == ["autarquia", "orgao_colegial"]
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
