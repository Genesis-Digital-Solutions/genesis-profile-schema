"""v0.1.133 (Quadrantis 27 Out 2026): fundo «em subscrição», fonte oficial das
paridades fixas e prazo dos nunca submetidos a contar do convite."""
import pytest
from pydantic import ValidationError

from genesis_profile_schema.intake_schema import IntakeDefinition, IntakeFxPolicy, IntakeRetention


def _base():
    return {"title": {"pt": "Q", "en": "Q"}, "use_case": "appropriateness", "languages": ["pt", "en"],
            "sections": [{"key": "s1", "title": {"pt": "S", "en": "S"}}],
            "questions": [{"key": "q1", "section": "s1", "type": "text", "label": {"pt": "A", "en": "A"}}]}


def test_fundo_ativo_por_omissao_e_inativo_aceite():
    d = _base()
    d["funds"] = [{"key": "a", "name": {"pt": "A", "en": "A"}},
                  {"key": "b", "name": {"pt": "B", "en": "B"}, "active": False}]
    funds = IntakeDefinition.model_validate(d).funds
    assert [f.active for f in funds] == [True, False]
    # O omitido não aparece no dump sem os valores por omissão (a impressão não muda).
    assert "active" not in funds[0].model_dump(exclude_defaults=True)


def test_fonte_das_paridades_so_para_moedas_com_paridade():
    p = IntakeFxPolicy.model_validate({"via_usd": {"QAR": 3.64}, "via_usd_sources": {"QAR": "Banco Central do Qatar"}})
    assert p.via_usd_sources == {"QAR": "Banco Central do Qatar"}
    with pytest.raises(ValidationError):
        IntakeFxPolicy.model_validate({"via_usd": {"QAR": 3.64}, "via_usd_sources": {"AED": "x"}})
    with pytest.raises(ValidationError):
        IntakeFxPolicy.model_validate({"via_usd": {"QAR": 3.64}, "via_usd_sources": {"QAR": ""}})
    # Sem fontes: igual a antes (a impressão das metodologias existentes não muda).
    assert IntakeFxPolicy.model_validate({"via_usd": {"AED": 3.6725}}).model_dump(exclude_defaults=True) == {
        "via_usd": {"AED": 3.6725}}


def test_prazo_dos_nunca_submetidos():
    assert IntakeRetention().unsubmitted_from == "link_end"
    assert IntakeRetention.model_validate({"years": 5, "unevaluated_days": 30,
                                           "unsubmitted_from": "invite"}).unsubmitted_from == "invite"
    with pytest.raises(ValidationError):
        IntakeRetention.model_validate({"unsubmitted_from": "creation"})


def test_metas_das_metricas():
    from genesis_profile_schema.intake_schema import IntakeMetricTargets
    d = _base()
    d["metric_targets"] = {"completion_rate": 0.9, "fill_minutes_mean": 25, "prefill_unchanged_rate": 0.9,
                           "agreement_rate": 1}
    assert IntakeDefinition.model_validate(d).metric_targets.fill_minutes_mean == 25
    d["metric_targets"] = None                                   # forma do blob gravado sem metas
    assert IntakeDefinition.model_validate(d).metric_targets is None
    for bad in ({"completion_rate": 1.5}, {"fill_minutes_mean": 0}, {"agreement_rate": -0.1}, {"outra": 1}):
        with pytest.raises(ValidationError):
            IntakeMetricTargets.model_validate(bad)
