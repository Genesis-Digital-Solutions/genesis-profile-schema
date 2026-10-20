"""tests/test_agentic.py — bloco `agentic` (A1 do core agêntico, 20 Out 2026)."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.agentic import ProfileAgentic
from genesis_profile_schema.client_profile_schema import ClientProfileSchema


def test_absent_and_null_mean_off():
    assert ClientProfileSchema().agentic is None
    assert ClientProfileSchema(agentic=None).agentic is None


def test_defaults_and_budget():
    a = ProfileAgentic(enabled=True, budget={"steps": 20, "writes": 5, "wall_clock_hours": 48})
    assert a.enabled is True and a.budget.steps == 20 and a.budget.wall_clock_hours == 48
    assert ProfileAgentic().enabled is False and ProfileAgentic().budget is None


@pytest.mark.parametrize("budget", [{"steps": 0}, {"steps": 201}, {"writes": 51}, {"wall_clock_hours": 0},
                                    {"wall_clock_hours": 721}])
def test_budget_limits(budget):
    with pytest.raises(ValidationError):
        ProfileAgentic(enabled=True, budget=budget)


def test_profile_roundtrip_keeps_block():
    p = ClientProfileSchema.model_validate({"agentic": {"enabled": True, "budget": {"steps": 12}}})
    dumped = p.model_dump()
    assert dumped["agentic"]["enabled"] is True and dumped["agentic"]["budget"]["steps"] == 12
