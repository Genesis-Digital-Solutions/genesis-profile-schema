"""
agentic.py — o bloco `agentic` do perfil (A1 do core agêntico, 20 Out 2026;
`codigo/CONTEXT_PACK_agentico_core.md`).

Liga as tarefas duráveis do core: hoje, a automação de uma fila que continua
DEPOIS de uma aprovação (os ramos `on_success`/`on_error` correm e os passos
seguintes só correm depois da decisão). Desligado por omissão = comportamento
de hoje. Lido por frente (base e variantes).

Orçamento por tarefa (tetos fora do modelo): `steps` (passos), `writes`
(chamadas com efeito) e `wall_clock_hours` (desde a criação, incluindo o tempo
à espera de pessoas). Sem valor → os do core (12 passos, 3 escritas, 720 h); a
automação de uma fila nunca fica abaixo das chamadas que ela própria define.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

MAX_STEPS = 200
MAX_WRITES = 50
MAX_WALL_CLOCK_HOURS = 720


class AgenticBudget(BaseModel):
    model_config = ConfigDict(extra="allow")

    steps: Optional[int] = Field(default=None, ge=1, le=MAX_STEPS)
    writes: Optional[int] = Field(default=None, ge=1, le=MAX_WRITES)
    wall_clock_hours: Optional[float] = Field(default=None, gt=0, le=MAX_WALL_CLOCK_HOURS)


class ProfileAgentic(BaseModel):
    """`agentic` do perfil. `null`/ausente = desligado."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    budget: Optional[AgenticBudget] = None


__all__ = ["ProfileAgentic", "AgenticBudget", "MAX_STEPS", "MAX_WRITES", "MAX_WALL_CLOCK_HOURS"]
