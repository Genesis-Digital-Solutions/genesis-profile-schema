"""Desfechos do modo simples (v0.1.139): `review.outcomes` num questionário SEM regras."""

import copy

import pytest

from genesis_profile_schema.intake_library import get_template
from genesis_profile_schema.intake_schema import IntakeDefinition


def _kyc():
    return copy.deepcopy(get_template("onboarding_kyc")["definition"])


def _outcomes(d):
    langs = d["languages"]
    return [{"key": "aceite", "label": {l: "Aceite" for l in langs}, "kind": "positive"},
            {"key": "recusado", "label": {l: "Recusado" for l in langs}, "kind": "negative"}]


def test_sem_regras_aceita_desfechos():
    d = _kyc()
    d.setdefault("review", {})["outcomes"] = _outcomes(d)
    m = IntakeDefinition.model_validate(d)
    assert [o.key for o in m.review.outcomes] == ["aceite", "recusado"]


def test_omissao_e_vazio():
    assert IntakeDefinition.model_validate(_kyc()).review.outcomes == []


def test_com_regras_recusa():
    d = copy.deepcopy(get_template("appropriateness_basic")["definition"])
    d.setdefault("review", {})["outcomes"] = _outcomes(d)
    with pytest.raises(ValueError, match="sem regras"):
        IntakeDefinition.model_validate(d)


@pytest.mark.parametrize("bad", [
    lambda d: [*_outcomes(d), _outcomes(d)[0]],                                   # chave repetida
    lambda d: [{"key": "x", "label": {"pt": "X"}, "kind": "review"}],              # «review» não é desfecho
    lambda d: [{"key": "x", "label": {d["languages"][0]: "X"}, "kind": "positive"}] if len(d["languages"]) > 1
    else [{"key": "x", "label": {"zz": "X"}, "kind": "positive"}],                 # falta uma língua
    lambda d: [{"key": f"k{i}", "label": {l: "X" for l in d["languages"]}, "kind": "positive"} for i in range(7)],
])
def test_invalidos(bad):
    d = _kyc()
    d.setdefault("review", {})["outcomes"] = bad(d)
    with pytest.raises(ValueError):
        IntakeDefinition.model_validate(d)


def test_segunda_validacao_por_desfecho_simples():
    d = _kyc()
    d.setdefault("review", {})["outcomes"] = _outcomes(d)
    d["review"]["double_validation"] = {"outcomes": ["recusado"]}
    assert IntakeDefinition.model_validate(d).review.double_validation.outcomes == ["recusado"]
    d["review"]["double_validation"] = {"outcomes": ["inventado"]}
    with pytest.raises(ValueError, match="inexistentes"):
        IntakeDefinition.model_validate(d)
