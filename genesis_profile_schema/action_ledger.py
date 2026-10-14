"""
action_ledger.py — registo durável das ações do assistente (`actionLedger`,
v0.1.115–116, 14 Out 2026; pack «Ações com regras, aprovação e registo», F3).

PORQUÊ
──────
Os bots agem (MCP com o ERP, pedidos, aprovações). Hoje a história de uma ação
está espalhada por quatro registos e ninguém a vê inteira. O F3 junta-a num
registo por cliente, uma entrada por evento (proposta, confirmação, regra,
aprovação, execução, resultado), encadeado por sha256 — o cliente pode
verificar que nada foi mudado nem tirado.

Decisões (Bruno, 13–14 Out 2026):
  • D3: contentor próprio no genai-core (`action_ledger`);
  • D4: a cadeia assenta no HASH dos valores — o apagamento RGPD apaga os
    valores e a cadeia continua válida (alinhado com as orientações do EDPB
    02/2025; nada de armazenamento imutável para os valores);
  • liga-se no Studio e no GAIBO, desligado por omissão; num cliente de ALTO
    RISCO o core regista SEMPRE (ignora o desligado) e, se não conseguir
    registar, a ação não corre;
  • retenção: alto risco → `compliance.high_risk.log_retention_days` (mínimo
    legal de 6 meses, AI Act arts. 19/26); os outros → `retention_days` deste
    bloco, 365 por omissão (uma auditoria anual).

`ledger_policy(profile)` é a regra ÚNICA (core, Studio e GAIBO usam esta):
«alto risco» = `compliance.classification.risk_level == "high"` OU
`compliance.high_risk.enabled` — a mesma do `compliance_context` do core.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_RETENTION_DAYS = 365
MIN_RETENTION_DAYS = 180          # AI Act: registos guardados pelo menos 6 meses
MAX_RETENTION_DAYS = 3650


class ProfileActionLedger(BaseModel):
    """`actionLedger` do perfil (só o BASE conta). Desligado por omissão."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    retention_days: int = Field(default=DEFAULT_RETENTION_DAYS, ge=MIN_RETENTION_DAYS, le=MAX_RETENTION_DAYS)


def is_high_risk(profile: Mapping[str, Any]) -> bool:
    """A mesma regra do `core/agent/compliance_context.py`. Nunca levanta."""
    try:
        comp = (profile or {}).get("compliance") or {}
        risk = str(((comp.get("classification") or {}).get("risk_level")) or "")
        return risk == "high" or bool((comp.get("high_risk") or {}).get("enabled"))
    except Exception:  # noqa: BLE001
        return False


def _int_in_range(value: Any, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if isinstance(value, bool):
        return default
    return min(max(n, MIN_RETENTION_DAYS), MAX_RETENTION_DAYS)


def ledger_policy(profile: Mapping[str, Any]) -> Dict[str, Any]:
    """`{on, required, retention_days}`:
      on        — regista-se (ligado no perfil, ou cliente de alto risco);
      required  — alto risco: sem registo, a ação NÃO corre (falha fechada);
      retention_days — dias até o documento expirar (TTL).
    Nunca levanta; perfil estranho → desligado, 365 dias."""
    try:
        block = (profile or {}).get("actionLedger") or {}
        if not isinstance(block, Mapping):
            block = {}
        high = is_high_risk(profile)
        if high:
            hr = ((profile or {}).get("compliance") or {}).get("high_risk") or {}
            days = _int_in_range(hr.get("log_retention_days"), DEFAULT_RETENTION_DAYS)
        else:
            days = _int_in_range(block.get("retention_days"), DEFAULT_RETENTION_DAYS)
        return {"on": high or block.get("enabled") is True, "required": high, "retention_days": days}
    except Exception:  # noqa: BLE001
        return {"on": False, "required": False, "retention_days": DEFAULT_RETENTION_DAYS}


# ── A cadeia (a MESMA conta no core, que escreve, e em quem verifica) ────────

#: Os eventos da vida de uma ação. `started` (v0.1.116): escrito ANTES de
#: executar num cliente de alto risco — se não ficar escrito, a ação não corre
#: (a falha fechada prova-se por uma escrita, não por o contentor existir).
EVENTS = ("proposed", "confirmed", "cancelled", "blocked_by_rule", "sent_for_approval", "approved",
          "rejected", "expired", "started", "executed", "failed")

#: Os campos que entram no hash (lista FECHADA: um campo novo não muda a conta
#: das entradas antigas). NADA pessoal entra em claro: os valores (`params`) e
#: as identidades (quem pediu, quem aprovou) entram só como digest COM SAL
#: (`salted_digest`). O sal é por entrada e vive na parte apagável, ao lado dos
#: valores; apagar por RGPD tira os valores, as identidades e o sal — o digest
#: fica na cadeia mas deixa de se poder ligar à pessoa (um hash sem sal de
#: «total: 500» ou de um email adivinha-se; orientações do EDPB 02/2025).
#: `actor` = `{kind: user|agent|system, digest}`; `approver` = digest ou None;
#: `result` = `{ok, code}` — só um CÓDIGO curto (`RESULT_CODE`), nunca a
#: mensagem (um erro do ERP traz nomes e NIFs; a mensagem vai para `detail`,
#: apagável). v0.1.116: `expires_at` (quando esta entrada expira, monótono:
#: nunca antes da anterior) e `prev_expires_at` (quando a anterior expira) —
#: assim a verificação distingue uma entrada que EXPIROU de uma que foi TIRADA.
CHAIN_FIELDS = ("seq", "ts", "client_id", "variant_slug", "event", "action", "actor", "ref",
                "rule_id", "decision", "approver", "result", "params_digest",
                "expires_at", "prev_expires_at")

#: Códigos aceites em `result.code` (o resto vira «error»).
RESULT_CODE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

#: A parte apagável de cada entrada (nunca entra no hash). Os sais são POR
#: PAPEL (`salt.who`, `salt.approver`, `salt.params`): apagar quem só aprovou
#: não apaga os valores nem a identidade de quem pediu.
ERASABLE_FIELDS = ("params", "detail", "salt", "who")
ERASED = "[apagado]"

GENESIS_HASH = "0" * 64


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def salted_digest(salt: str, value: Any) -> str:
    """sha256(sal + canónico(valor)) — o que a cadeia guarda em vez de valores e
    identidades. Sem o sal (apagado), não se volta ao valor."""
    return hashlib.sha256((str(salt or "") + "|" + _canonical(value if value is not None else {}))
                          .encode("utf-8")).hexdigest()


def params_digest(params: Any, salt: str = "") -> str:
    """O digest dos valores da ação (com o sal da entrada)."""
    return salted_digest(salt, params if params is not None else {})


def entry_hash(prev_hash: str, entry: Mapping[str, Any]) -> str:
    """sha256(prev_hash + canónico(campos da cadeia))."""
    chained = {k: entry.get(k) for k in CHAIN_FIELDS}
    return hashlib.sha256((str(prev_hash or "") + "|" + _canonical(chained)).encode("utf-8")).hexdigest()


def result_code(value: Any) -> str:
    """O código que pode entrar na cadeia (`RESULT_CODE`) ou «error»."""
    v = str(value or "").strip().lower()
    return v if RESULT_CODE.match(v) else ("error" if v else "")


def chain_start(first: Mapping[str, Any], now: float) -> Dict[str, Any]:
    """Onde começa a verificação de uma cadeia cuja 1.ª entrada existente é
    `first`: o início (seq 1), ou — se as anteriores já EXPIRARAM pela
    retenção (`prev_expires_at` ≤ agora, que está DENTRO da cadeia) — o elo
    que ela guarda. Uma entrada anterior em falta que ainda não devia ter
    expirado é uma entrada TIRADA. `{ok, start_prev, reason}`."""
    seq = int(first.get("seq") or 0)
    if seq <= 1:
        return {"ok": True, "start_prev": GENESIS_HASH, "reason": ""}
    pe = first.get("prev_expires_at")
    if isinstance(pe, (int, float)) and not isinstance(pe, bool) and pe <= now:
        return {"ok": True, "start_prev": str(first.get("prev_hash") or ""), "reason": ""}
    return {"ok": False, "start_prev": "", "reason": "missing_entry"}


def verify_chain(entries: Iterable[Mapping[str, Any]], *, start_prev: str = GENESIS_HASH,
                 expect_seq: Optional[int] = None) -> Dict[str, Any]:
    """Verifica entradas por ordem de `seq`. `{ok, checked, broken_at, reason, last_seq, last_hash}`:
    `broken_at` é o `seq` da 1.ª entrada que não bate (hash, elo ou buraco na
    sequência). `start_prev` + `expect_seq` deixam verificar por PÁGINAS (a
    página seguinte começa no `last_hash`/`last_seq + 1` da anterior).
    Os `params` apagados por RGPD não partem nada (só o digest conta)."""
    prev = start_prev
    expected_seq: Optional[int] = expect_seq
    checked = 0
    last_seq: Optional[int] = None
    rows: List[Mapping[str, Any]] = sorted(entries, key=lambda e: int(e.get("seq") or 0))
    for e in rows:
        seq = int(e.get("seq") or 0)
        if expected_seq is not None and seq != expected_seq:
            return {"ok": False, "checked": checked, "broken_at": expected_seq, "reason": "missing_entry",
                    "last_seq": last_seq, "last_hash": prev}
        if str(e.get("prev_hash") or "") != prev:
            return {"ok": False, "checked": checked, "broken_at": seq, "reason": "link_mismatch",
                    "last_seq": last_seq, "last_hash": prev}
        if entry_hash(prev, e) != str(e.get("hash") or ""):
            return {"ok": False, "checked": checked, "broken_at": seq, "reason": "hash_mismatch",
                    "last_seq": last_seq, "last_hash": prev}
        prev, expected_seq, checked, last_seq = str(e.get("hash")), seq + 1, checked + 1, seq
    return {"ok": True, "checked": checked, "broken_at": None, "reason": "", "last_seq": last_seq,
            "last_hash": prev}
