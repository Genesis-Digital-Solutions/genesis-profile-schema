"""Lista de fundos por questionário (próximo bump; Quadrantis 21 Out 2026)."""
import copy

import pytest
from pydantic import ValidationError

from genesis_profile_schema.intake_schema import IntakeDefinition, MAX_FUNDS


def _base():
    return {"title": {"pt": "Q", "en": "Q"}, "use_case": "appropriateness", "languages": ["pt", "en"],
            "sections": [{"key": "s1", "title": {"pt": "S", "en": "S"}}],
            "questions": [{"key": "q1", "section": "s1", "type": "text", "label": {"pt": "A", "en": "A"}}]}


def test_sem_fundos_continua_valido():
    assert IntakeDefinition.model_validate(_base()).funds == []


def test_fundos_validos():
    d = _base()
    d["funds"] = [{"key": "fcr_i", "name": {"pt": "Fundo I", "en": "Fund I"}}]
    assert IntakeDefinition.model_validate(d).funds[0].key == "fcr_i"


@pytest.mark.parametrize("funds", [
    [{"key": "a", "name": {"pt": "A", "en": "A"}}, {"key": "a", "name": {"pt": "B", "en": "B"}}],   # repetida
    [{"key": "a", "name": {"pt": "A"}}],                                                           # sem EN
    [{"key": "a", "name": {"pt": "A", "en": "A"}, "extra": 1}],                                    # fechado
    [{"key": f"f{i}", "name": {"pt": "A", "en": "A"}} for i in range(MAX_FUNDS + 1)],               # teto
])
def test_fundos_invalidos(funds):
    d = _base()
    d["funds"] = copy.deepcopy(funds)
    with pytest.raises(ValidationError):
        IntakeDefinition.model_validate(d)
