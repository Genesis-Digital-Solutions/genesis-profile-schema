"""
tests/test_intake_library.py — a biblioteca de modelos do Intake (v0.1.91):
uma só fonte para o Studio e o GAIBO. Protege: todos os modelos carregam e
validam como `IntakeDefinition`; são genéricos (nenhum cliente, «[entidade]»
para trocar); os que têm regras trazem casos de teste; quem chama recebe
cópias; o pacote instalado leva os JSON; e os modelos de investimento propõem
a partir do documento de identificação e do CV como a proposta Quadrantis
(§3.1/§3.2) — nunca nas declarações.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from genesis_profile_schema import intake_library as lib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_todos_carregam_por_ordem():
    tpls = lib.list_templates()
    assert [t["id"] for t in tpls] == ["appropriateness_basic", "onboarding_kyc", "conflict_of_interest",
                                       "eligibility_grid", "supplier_due_diligence", "informed_consent"]
    for t in tpls:
        assert t["definition"]["languages"] == ["pt", "en"]
        if t["rules"]:
            assert len(t["definition"]["methodology"]["reference_cases"]) >= 3, t["id"]


def test_genericos():
    raw = json.dumps(lib.list_templates(), ensure_ascii=False)
    assert "[entidade]" in raw
    assert not re.search(r"quadrantis|indaqua|salmon|sodarca|genpolar", raw, re.I)


def test_copias():
    a = lib.get_template("conflict_of_interest")
    a["definition"]["title"]["pt"] = "X"
    assert lib.get_template("conflict_of_interest")["definition"]["title"]["pt"] != "X"
    assert lib.get_template("nao_existe") is None


def test_documento_e_cv_nos_modelos_de_investimento():
    qs = {q["key"]: q for q in lib.get_template("onboarding_kyc")["definition"]["questions"]}
    assert (qs["1.1"]["prefill_from"], qs["1.1"]["prefill_document_field"]) == (["id_document", "invitation"], "full_name")
    assert qs["1.3"]["prefill_document_field"] == "nationality"
    assert qs["2.1"]["prefill_from"] == ["cv"]
    assert "prefill_from" not in qs["2.4"]                                  # declaração (PEP): nunca proposta
    qa = {q["key"]: q for q in lib.get_template("appropriateness_basic")["definition"]["questions"]}
    assert "cv" in qa["2.1"]["prefill_from"] and "cv" not in qa["2.4"]["prefill_from"]


@pytest.mark.parametrize("mutate,err", [
    (lambda d: d.update(id="Outro"), "id"),
    (lambda d: d["name"].pop("en"), "name"),
    (lambda d: d.update(rules=not d["rules"]), "rules"),
    (lambda d: d["definition"].update(use_case="nope"), "use_case"),
])
def test_modelo_invalido_rebenta_ao_carregar(mutate, err):
    doc = lib.get_template("conflict_of_interest")
    mutate(doc)
    with pytest.raises(Exception):
        lib._check(doc, "conflict_of_interest.json")


def test_o_pacote_leva_os_json():
    toml = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"intake_library/*.json"' in toml
    assert len(list((ROOT / "genesis_profile_schema" / "intake_library").glob("*.json"))) == len(lib.list_templates())
