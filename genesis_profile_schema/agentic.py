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

v0.1.133 (A4 do core agêntico, 28 Out 2026): `events.sources` — as fontes
do webhook de entrada que acorda tarefas do agente (`POST /agent-events/<id>`
no core). Cada fonte: `id` (minúsculas, dígitos, hífen; dá o nome do segredo
`AGENT-EVENTS-<ID>-SECRET` no Key Vault do cliente, gravado pelo Studio),
`events` (os eventos que pode mandar — allowlist), `ips` (redes de onde pode
chamar; vazio = qualquer uma, a assinatura continua obrigatória) e `enabled`.
O passo `agent` dos triggers das filas fica na lista `do` (não tipada, como os
outros passos).
"""

from __future__ import annotations

from typing import Optional

import ipaddress
import re
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


SOURCE_ID_RE = re.compile(r"^(?=.{1,40}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
EVENT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MAX_SOURCES = 20
MAX_EVENTS = 30
MAX_NETWORKS = 20


class AgenticEventSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str                                   # obrigatório: sem ele o core ignorava a fonte
    enabled: bool = True
    events: List[str] = Field(default_factory=list)
    ips: List[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not SOURCE_ID_RE.match(v or ""):
            raise ValueError("id da fonte: minúsculas e dígitos, separados por um hífen (até 40)")
        return v

    @field_validator("events")
    @classmethod
    def _events(cls, v: List[str]) -> List[str]:
        if len(v) > MAX_EVENTS:
            raise ValueError(f"no máximo {MAX_EVENTS} eventos por fonte")
        for e in v:
            if not EVENT_NAME_RE.match(str(e or "")):
                raise ValueError(f"nome de evento inválido: {str(e)[:40]!r}")
        return v

    @field_validator("ips")
    @classmethod
    def _ips(cls, v: List[str]) -> List[str]:
        if len(v) > MAX_NETWORKS:
            raise ValueError(f"no máximo {MAX_NETWORKS} redes por fonte")
        for n in v:
            try:
                ipaddress.ip_network(str(n), strict=False)
            except ValueError:
                raise ValueError(f"rede inválida: {str(n)[:45]!r}") from None
        return v


class AgenticEvents(BaseModel):
    model_config = ConfigDict(extra="allow")

    sources: List[AgenticEventSource] = Field(default_factory=list)

    @field_validator("sources")
    @classmethod
    def _unique(cls, v: List[AgenticEventSource]) -> List[AgenticEventSource]:
        if len(v) > MAX_SOURCES:
            raise ValueError(f"no máximo {MAX_SOURCES} fontes")
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("fontes com o mesmo id")
        return v


class ProfileAgentic(BaseModel):
    """`agentic` do perfil. `null`/ausente = desligado."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    budget: Optional[AgenticBudget] = None
    plan_visible: Optional[bool] = None
    verify: Optional[bool] = None
    events: Optional[AgenticEvents] = None


__all__ = ["ProfileAgentic", "AgenticBudget", "AgenticEvents", "AgenticEventSource", "SOURCE_ID_RE",
           "EVENT_NAME_RE", "MAX_STEPS", "MAX_WRITES", "MAX_WALL_CLOCK_HOURS", "MAX_COST_EUR"]
