"""
action_rules.py — regras por ação do agente (`actionRules`, v0.1.109, 14 Out 2026).

PORQUÊ
──────
Os bots passaram a AGIR (MCP com SAP/Xero/PHC, `create_ticket`, filas com
escrita no ERP). Até aqui o controlo era uma escolha por cliente
(`mcp.confirm_actions`) e quem confirmava era o próprio utilizador. Este bloco
deixa o cliente dizer, por ação: permitir, confirmar (como hoje), enviar para
aprovação de OUTRA pessoa (F2) ou bloquear — e com limites de valor
(«montante ≤ 500 € → aprovar»).

Pack `CONTEXT_PACK_acoes_regras_aprovacao_registo.md` (decisões D1–D8 e §10.6):
  • fora de `mcp.*` (que é interno: credenciais, `trusted`) — o cliente edita
    este bloco no GAIBO e a Genesis no Studio;
  • `enabled=False` (o default) = comportamento de hoje, byte a byte (D6);
  • os mínimos de segurança vivem no CÓDIGO do core e nenhuma regra os baixa
    (destrutiva nativa sempre confirmada, alto risco nunca `never`, fail-safe
    por nome nas MCP);
  • ganha o mais restritivo: block > approve > confirm > allow;
  • limite que não se consegue avaliar (parâmetro em falta, moeda diferente)
    falha FECHADO — nunca se adivinha um câmbio (semântica do Intake);
  • `log_only`: a regra é avaliada e registada, mas não muda nada — o cliente
    vê o efeito antes de a ligar.

As regras que dependem do RESTO do perfil (fila que existe, servidor `per_user`)
vivem em `action_rules_problems()`, que nunca levanta: devolve problemas com
código estável e quem chama (Studio, backoffice) decide. Um valor mau nunca
impede o perfil de carregar; o core trata uma regra inválida como falha fechada.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

# ── Vocabulário ──────────────────────────────────────────────────────────────
MODES: Tuple[str, ...] = ("allow", "confirm", "approve", "block")
OVER_MODES: Tuple[str, ...] = ("confirm", "approve", "block")
OPS: Tuple[str, ...] = ("lte", "lt", "gte", "gt", "eq", "in")
# Ordem de força: ganha o maior.
STRENGTH: Dict[str, int] = {"allow": 0, "confirm": 1, "approve": 2, "block": 3}

MAX_RULES = 100
MAX_LIMITS = 10
MAX_IN_VALUES = 50
NOTE_MAX = 300

_RULE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$", re.ASCII)
# `<servidor>.<tool>` (MCP) ou o nome de uma tool nativa.
_ACTION = re.compile(r"^[A-Za-z0-9_-]{1,64}(\.[A-Za-z0-9_.-]{1,128})?$", re.ASCII)
_CURRENCY = re.compile(r"^[A-Z]{3}$", re.ASCII)

# Problemas (códigos estáveis — o Studio e o backoffice traduzem-nos).
ERROR = "error"
WARNING = "warning"
INVALID_ID = "invalid_id"
DUPLICATE_ID = "duplicate_id"
INVALID_ACTION = "invalid_action"
INVALID_MODE = "invalid_mode"
APPROVE_WITHOUT_QUEUE = "approve_without_queue"     # aprovar sem fila escolhida
UNKNOWN_QUEUE = "unknown_queue"                     # fila que não existe no perfil
APPROVE_PER_USER = "approve_per_user"               # D2: servidor com login por utilizador
UNKNOWN_SERVER = "unknown_server"                   # servidor MCP que já não existe
INVALID_LIMIT = "invalid_limit"
IN_NEEDS_LIST = "in_needs_list"
NUMERIC_OP_ON_TEXT = "numeric_op_on_text"           # `≤` com um valor que não é número
INVALID_CURRENCY = "invalid_currency"
TOO_MANY_RULES = "too_many_rules"
TOO_MANY_LIMITS = "too_many_limits"


# ── Modelos ──────────────────────────────────────────────────────────────────

class ActionRuleLimit(BaseModel):
    """Um limite sobre um parâmetro da ação: «montante ≤ 500 EUR → aprovar»."""
    model_config = ConfigDict(extra="allow")

    param: str = ""                              # campo do inputSchema da tool
    op: Literal["lte", "lt", "gte", "gt", "eq", "in"] = "lte"
    value: Optional[Union[float, int, str, List[Union[float, int, str]]]] = None
    # Quando o campo é dinheiro: a moeda do limite (ISO 4217). Um valor noutra
    # moeda NÃO se converte — falha fechada (passa a `over`).
    currency: Optional[str] = None
    # O que acontece quando o limite é ultrapassado (ou não se consegue ler).
    over: Literal["confirm", "approve", "block"] = "approve"


class ActionRuleApproval(BaseModel):
    model_config = ConfigDict(extra="allow")

    queue: str = ""                              # chave de `reviewQueues`


class ActionRule(BaseModel):
    """Regra para UMA ação. `id` é estável (vai para o registo de cada decisão)."""
    model_config = ConfigDict(extra="allow")

    id: str = ""
    # `<servidor>.<tool>` para MCP (o nome do servidor em `mcp.servers`) ou o
    # nome de uma tool nativa que age (`create_ticket`, `forget`…). Escolhido
    # de uma lista no editor, nunca escrito à mão.
    action: str = ""
    mode: Literal["allow", "confirm", "approve", "block"] = "confirm"
    limits: List[ActionRuleLimit] = Field(default_factory=list)
    approval: Optional[ActionRuleApproval] = None   # só com approve (F2)
    variants: List[str] = Field(default_factory=list)  # vazio = todas
    # Só registar: avalia e regista o que TERIA feito, sem mudar nada.
    log_only: bool = False
    note: str = ""                               # porquê, em linguagem de negócio


class ProfileActionRules(BaseModel):
    """`actionRules` do perfil. Desligado por omissão = comportamento de hoje."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    rules: List[ActionRule] = Field(default_factory=list)


# ── Regras que dependem do resto do perfil ──────────────────────────────────

def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _mcp_servers(profile: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    servers = ((profile or {}).get("mcp") or {}).get("servers") or []
    out: Dict[str, Mapping[str, Any]] = {}
    if isinstance(servers, list):
        for s in servers:
            if isinstance(s, Mapping) and s.get("name"):
                out[str(s["name"])] = s
    return out


def _limit_problems(limit: Any) -> List[Tuple[str, str]]:
    if not isinstance(limit, Mapping):
        return [(INVALID_LIMIT, ERROR)]
    out: List[Tuple[str, str]] = []
    param = str(limit.get("param") or "").strip()
    op = str(limit.get("op") or "lte")
    value = limit.get("value")
    if not param or op not in OPS or value is None or (isinstance(value, str) and not value.strip()):
        out.append((INVALID_LIMIT, ERROR))
    if str(limit.get("over") or "approve") not in OVER_MODES:
        out.append((INVALID_MODE, ERROR))
    if op == "in":
        if not isinstance(value, list) or not value or len(value) > MAX_IN_VALUES:
            out.append((IN_NEEDS_LIST, ERROR))
    elif op in ("lte", "lt", "gte", "gt") and value is not None and not _is_number(value):
        # «≤ 'abc'» nunca é verdade nem falso com sentido. Aviso: o core trata
        # como não avaliável (falha fechada), não rebenta.
        out.append((NUMERIC_OP_ON_TEXT, WARNING))
    cur = limit.get("currency")
    if cur not in (None, "") and not _CURRENCY.match(str(cur)):
        out.append((INVALID_CURRENCY, ERROR))
    return out


def action_rules_problems(profile: Mapping[str, Any]) -> List[Dict[str, str]]:
    """Problemas do bloco `actionRules` à luz do RESTO do perfil.

    Devolve `[{"rule_id", "code", "severity"}]` (lista vazia = tudo bem). Nunca
    levanta. `rule_id` vazio para problemas do bloco inteiro."""
    out: List[Dict[str, str]] = []

    def add(rule_id: str, code: str, severity: str) -> None:
        out.append({"rule_id": rule_id, "code": code, "severity": severity})

    try:
        block = (profile or {}).get("actionRules") or {}
        rules = block.get("rules") if isinstance(block, Mapping) else None
        if not isinstance(rules, list):
            return out
        if len(rules) > MAX_RULES:
            add("", TOO_MANY_RULES, ERROR)
        queues = (profile or {}).get("reviewQueues") or {}
        queues = queues if isinstance(queues, Mapping) else {}
        servers = _mcp_servers(profile)
        seen: set = set()
        for raw in rules:
            if not isinstance(raw, Mapping):
                add("", INVALID_ACTION, ERROR)
                continue
            rid = str(raw.get("id") or "")
            if not _RULE_ID.match(rid):
                add(rid, INVALID_ID, ERROR)
            elif rid in seen:
                add(rid, DUPLICATE_ID, ERROR)
            seen.add(rid)

            action = str(raw.get("action") or "")
            if not _ACTION.match(action):
                add(rid, INVALID_ACTION, ERROR)
            mode = str(raw.get("mode") or "confirm")
            if mode not in MODES:
                add(rid, INVALID_MODE, ERROR)

            server = action.split(".", 1)[0] if "." in action else ""
            if server:
                if server not in servers:
                    # Assinalado, nunca apagado: o servidor pode voltar.
                    add(rid, UNKNOWN_SERVER, WARNING)

            limits = raw.get("limits") or []
            if not isinstance(limits, list):
                add(rid, INVALID_LIMIT, ERROR)
                limits = []
            if len(limits) > MAX_LIMITS:
                add(rid, TOO_MANY_LIMITS, ERROR)
            for lim in limits:
                for code, sev in _limit_problems(lim):
                    add(rid, code, sev)

            uses_approve = mode == "approve" or any(
                isinstance(l, Mapping) and str(l.get("over") or "approve") == "approve"
                for l in limits)
            if uses_approve:
                queue = str(((raw.get("approval") or {}) if isinstance(raw.get("approval"), Mapping)
                             else {}).get("queue") or "")
                if not queue:
                    add(rid, APPROVE_WITHOUT_QUEUE, ERROR)
                elif queue not in queues:
                    add(rid, UNKNOWN_QUEUE, ERROR)
                # D2: a aprovação corre fora da conversa, sem o login de quem
                # pediu — um servidor `per_user` ficaria sem token.
                srv = servers.get(server) if server else None
                if srv and ((srv.get("auth") or {}).get("per_user") is True):
                    add(rid, APPROVE_PER_USER, ERROR)
    except Exception:  # noqa: BLE001 — nunca levanta (contrato do módulo)
        add("", INVALID_ACTION, ERROR)
    return out
