"""
tests/test_runtime_agent_mode.py — o vocabulário de `runtime.agent_mode`
(v0.1.62, 16 Set 2026): os cinco modos que o Studio mostra e o genai-core
traduz em esforço (core/managers/effort_modes.py). O core valida o perfil no
save com este schema — um valor fora da lista é 422, por isso o `Literal` é a
fronteira real, não um comentário.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema import ClientProfileSchema


MODOS = ("auto", "fast", "balanced", "thinking", "max")


@pytest.mark.parametrize("modo", MODOS)
def test_aceita_os_cinco_modos(modo):
    p = ClientProfileSchema.model_validate({"runtime": {"agent_mode": modo}})
    assert p.runtime.agent_mode == modo


def test_default_continua_balanced():
    assert ClientProfileSchema().runtime.agent_mode == "balanced"


@pytest.mark.parametrize("invalido", ["pro", "xhigh", "MAX", "", "high"])
def test_rejeita_o_que_nao_e_modo(invalido):
    """O esforço técnico (`xhigh`, `high`) e o modo Pro NÃO são modos do
    perfil: o cliente escolhe o nível pelo nome, a tradução é do core."""
    with pytest.raises(ValidationError):
        ClientProfileSchema.model_validate({"runtime": {"agent_mode": invalido}})
