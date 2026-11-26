"""v0.1.182 — `agentic.user_mandates` (passo 8 do épico «Agente colega»)."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.agentic import AgenticUserMandates, ProfileAgentic
from genesis_profile_schema.exposure import EXPOSURE, unclassified_paths
from genesis_profile_schema.i18n_fields import i18n_field_paths


def _cat(**kw):
    base = {"id": "leads-pendentes", "label": {"pt": "Tratar das minhas leads"},
            "actions": ["crm.mark_contacted", "contact.ask"], "max_days": 30}
    base.update(kw)
    return base


def test_ausente_e_desligado():
    a = ProfileAgentic()
    assert a.user_mandates is None
    assert AgenticUserMandates().enabled is False


def test_categoria_valida():
    m = AgenticUserMandates(enabled=True, categories=[_cat()])
    assert m.categories[0].max_days == 30


@pytest.mark.parametrize("bad", [
    {"id": "Leads"}, {"id": "a" * 41}, {"actions": []}, {"actions": ["sem_ponto"]},
    {"actions": ["a.b", "a.b"]}, {"max_days": 0}, {"max_days": 91}, {"label": {}},
])
def test_categoria_invalida(bad):
    with pytest.raises(ValidationError):
        AgenticUserMandates(enabled=True, categories=[_cat(**bad)])


def test_ids_repetidos_e_teto():
    with pytest.raises(ValidationError):
        AgenticUserMandates(categories=[_cat(), _cat()])
    with pytest.raises(ValidationError):
        AgenticUserMandates(categories=[_cat(id=f"c{i}") for i in range(21)])


def test_exposicao_interna_e_classificada():
    for leaf in ("enabled", "categories.id", "categories.label", "categories.actions", "categories.max_days"):
        assert EXPOSURE[f"agentic.user_mandates.{leaf}"] == "internal"
    assert not [p for p in unclassified_paths() if p.startswith("agentic.user_mandates")]


def test_nome_da_categoria_e_multilingue():
    assert "agentic.user_mandates.categories.label" in i18n_field_paths()
