"""
agentic.py — o bloco `agentic` do perfil (A1 do core agêntico, 20 Out 2026;
`codigo/CONTEXT_PACK_agentico_core.md`).

Liga as tarefas duráveis do core: hoje, a automação de uma fila que continua
DEPOIS de uma aprovação (os ramos `on_success`/`on_error` correm e os passos
seguintes só correm depois da decisão). Desligado por omissão = comportamento
de hoje. Lido por frente (base e variantes).

Orçamento por tarefa (tetos fora do modelo): `steps` (passos — no chat, as
chamadas a ferramentas), `writes` (chamadas com efeito), `wall_clock_hours`
(desde a criação, incluindo o tempo à espera de pessoas) e `cost_eur` (custo de
modelo da tarefa, v0.1.132). Sem valor → os do core (20 passos, 3 escritas,
720 h, 0,50 € — decisão do Bruno na A3, 27 Out 2026); a automação de uma fila
nunca fica abaixo das chamadas que ela própria define.

v0.1.132 (A3 do core agêntico): `plan_visible` — a lista de passos que o
agente mantém num pedido com vários passos aparece no chat (ausente = sim;
`false` esconde-a, o core usa-a na mesma); `verify` (A2, 22 Out 2026) — reler
o sistema depois de cada escrita (ausente = sim; `false` desliga). O core já
lia os dois do dicionário; ficam tipados.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

MAX_STEPS = 200
MAX_WRITES = 50
MAX_WALL_CLOCK_HOURS = 720
MAX_COST_EUR = 50.0


class AgenticBudget(BaseModel):
    model_config = ConfigDict(extra="allow")

    steps: Optional[int] = Field(default=None, ge=1, le=MAX_STEPS)
    writes: Optional[int] = Field(default=None, ge=1, le=MAX_WRITES)
    wall_clock_hours: Optional[float] = Field(default=None, gt=0, le=MAX_WALL_CLOCK_HOURS)
    cost_eur: Optional[float] = Field(default=None, gt=0, le=MAX_COST_EUR)


class ProfileAgentic(BaseModel):
    """`agentic` do perfil. `null`/ausente = desligado."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    budget: Optional[AgenticBudget] = None
    plan_visible: Optional[bool] = None
    verify: Optional[bool] = None


__all__ = ["ProfileAgentic", "AgenticBudget", "MAX_STEPS", "MAX_WRITES", "MAX_WALL_CLOCK_HOURS", "MAX_COST_EUR"]
