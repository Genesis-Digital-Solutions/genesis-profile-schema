"""
genesis_profile_schema/team_people_numbers.py — números por pessoa no painel do agente (nível 2 da P15 do
épico «Agente colega», v0.1.182, 26 Nov 2026; decisão DP-7 do Bruno).

O painel de governação do agente tem três níveis:
  1. métricas da equipa, da fila e do agente — sempre ligadas (passo 18; nada por pessoa);
  2. números individuais por colaborador — ESTE bloco: desligados por omissão, ligados cliente a cliente;
  3. nunca: pontuações, rankings, ordenação por desempenho ou apreciações da IA sobre pessoas (Anexo III 4(b)
     do AI Act). Não há campo para isso, nem nunca haverá neste bloco.

`team.people_numbers` vive só no perfil BASE (como os papéis): uma Partilhada não tem `team` e uma Separada só
`team.roles` (o genai-core recusa o resto na camada). Ligar exige DOIS registos completos (padrão do
`consent_basis` das rotinas — texto, data, canal, quem):
  • `legal_basis`      — a base legal do tratamento (ex.: interesse legítimo com AIPD feita a AAAA-MM-DD);
  • `workers_informed` — a confirmação de que os trabalhadores foram informados (como, quando, por quem).
Sem os dois, o save recusa (core E Studio, pela MESMA função `people_numbers_problems`) e o core trata o
interruptor como desligado (`people_numbers_on`) — falha fechada, nunca «ligado a meio».

Quem vê o quê (aplicado no genai-core, nunca aqui):
  • cada pessoa vê sempre os SEUS números (rota de utilizador, com login);
  • os números dos outros só a quem tem um papel com a capacidade `team.people_numbers` (catálogo em
    `team.py`; «todas as frentes», como gerir a equipa), e cada consulta fica no audit (quem, de quem, quando —
    nunca os números);
  • nenhuma rota `/admin` (api-key do Studio e do GAIBO) devolve números por pessoa.

Interno de escrita (`exposure`: o cliente lê, só a Genesis grava — como `team.insights_phase2`): ligar é uma
decisão jurídica do cliente que a Genesis regista no Studio com o texto que o cliente lhe dá. Não substitui um
parecer jurídico.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

#: A capacidade do catálogo da equipa que dá os números dos OUTROS (o próprio vê sempre os seus).
CAPABILITY = "team.people_numbers"

TEXT_MAX = 500
CHANNEL_MAX = 80
BY_MAX = 120
#: Tolerância de uma data «hoje» escrita noutro fuso (Lisboa à meia-noite = ontem em UTC).
FUTURE_TOLERANCE_DAYS = 1

# Códigos estáveis (o Studio e o core traduzem-nos; nunca levam o valor).
LEGAL_BASIS_MISSING = "people_numbers_legal_basis_missing"
WORKERS_NOT_INFORMED = "people_numbers_workers_not_informed"
DATE_IN_FUTURE = "people_numbers_date_in_future"
CODES = (LEGAL_BASIS_MISSING, WORKERS_NOT_INFORMED, DATE_IN_FUTURE)

RECORDS = ("legal_basis", "workers_informed")
_MISSING_CODE = {"legal_basis": LEGAL_BASIS_MISSING, "workers_informed": WORKERS_NOT_INFORMED}
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)


class PeopleNumbersRecord(BaseModel):
    """Um registo humano: o quê (`text`), quando (`date`, AAAA-MM-DD), por que meio (`channel`) e quem o
    registou (`by`). Os quatro são obrigatórios para contar — a forma decide-se em `record_complete`."""
    model_config = ConfigDict(extra="allow")

    text: Optional[StrictStr] = Field(default=None, max_length=TEXT_MAX)
    date: Optional[StrictStr] = Field(default=None, max_length=10, json_schema_extra={"format": "date"})
    channel: Optional[StrictStr] = Field(default=None, max_length=CHANNEL_MAX)
    by: Optional[StrictStr] = Field(default=None, max_length=BY_MAX)


class TeamPeopleNumbers(BaseModel):
    """`team.people_numbers` — números por pessoa no painel do agente (nível 2). Desligado por omissão."""
    model_config = ConfigDict(extra="allow")

    enabled: StrictBool = False
    legal_basis: Optional[PeopleNumbersRecord] = None
    workers_informed: Optional[PeopleNumbersRecord] = None


def _text_ok(value: Any, max_len: int) -> bool:
    """Texto preenchido, dentro do teto e sem caracteres de controlo/invisíveis nem separadores de linha (Cc/Cf/Zl/Zp)."""
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        return False
    return not any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for c in value)


def _date_of(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def record_complete(raw: Any) -> bool:
    """Os quatro campos preenchidos, cada um na forma certa (data real AAAA-MM-DD, algarismos ASCII)."""
    if not isinstance(raw, Mapping):
        return False
    return (_text_ok(raw.get("text"), TEXT_MAX) and _date_of(raw.get("date")) is not None
            and _text_ok(raw.get("channel"), CHANNEL_MAX) and _text_ok(raw.get("by"), BY_MAX))


def _block(team: Any) -> Mapping[str, Any]:
    pn = team.get("people_numbers") if isinstance(team, Mapping) else None
    return pn if isinstance(pn, Mapping) else {}


def people_numbers_problems(team: Any, today: Optional[str] = None) -> List[Dict[str, str]]:
    """Os problemas do bloco `team.people_numbers` de UM perfil base (o bloco `team`, ou None).

    Desligado = nada a ver (os registos podem ficar escritos). Ligado = os dois registos completos; com
    `today` (AAAA-MM-DD, quem grava passa a data dele), uma data depois de amanhã também é recusada.
    Cada problema = `{code, loc}` (loc com pontos, a partir da raiz do perfil) — nunca o valor."""
    pn = _block(team)
    if pn.get("enabled") is not True:
        return []
    out: List[Dict[str, str]] = []
    limit = _date_of(today)
    for name in RECORDS:
        rec = pn.get(name)
        loc = f"team.people_numbers.{name}"
        if not record_complete(rec):
            out.append({"code": _MISSING_CODE[name], "loc": loc})
        elif limit is not None and _date_of(rec.get("date")) > limit + timedelta(days=FUTURE_TOLERANCE_DAYS):
            out.append({"code": DATE_IN_FUTURE, "loc": f"{loc}.date"})
    return out


def people_numbers_on(team: Any) -> bool:
    """O interruptor VALE: ligado E com os dois registos completos. Qualquer outra coisa = desligado (falha
    fechada — um perfil gravado por um escritor sem a guarda nunca liga os números a meio)."""
    return _block(team).get("enabled") is True and not people_numbers_problems(team)


__all__ = [
    "CAPABILITY", "CODES", "DATE_IN_FUTURE", "LEGAL_BASIS_MISSING", "WORKERS_NOT_INFORMED", "RECORDS",
    "TEXT_MAX", "CHANNEL_MAX", "BY_MAX", "PeopleNumbersRecord", "TeamPeopleNumbers", "record_complete",
    "people_numbers_problems", "people_numbers_on",
]
