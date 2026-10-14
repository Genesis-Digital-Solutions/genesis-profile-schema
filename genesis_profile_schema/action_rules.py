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
MAX_PERIOD_LIMITS = 5
PERIODS: Tuple[str, ...] = ("day", "week", "month")
PER: Tuple[str, ...] = ("user", "client")
MAX_IN_VALUES = 50
NOTE_MAX = 300

_RULE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$", re.ASCII)
# `<servidor>.<tool>` (MCP) ou o nome de uma tool nativa.
_ACTION = re.compile(r"^[A-Za-z0-9_-]{1,64}(\.[A-Za-z0-9_.-]{1,128})?$", re.ASCII)
_CURRENCY = re.compile(r"^[A-Z]{3}$", re.ASCII)
# Valor de uma app role do Entra (o que vem na claim `roles`).
_ROLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$", re.ASCII)
# Object id de um grupo do Entra (o que vem na claim `groups`).
_GROUP = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", re.ASCII)
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")

MAX_APPROVERS = 20
MAX_NOTIFY_EMAILS = 10
APPROVAL_EXPIRES_HOURS = 24          # prazo por omissão de um pedido de aprovação
APPROVAL_EXPIRES_MAX_HOURS = 720     # 30 dias

# ── Fila de aprovação (F2, 14 Out 2026) ──────────────────────────────────────
# A máquina de estados que o core reconhece numa fila de aprovação. O Studio
# cria a fila a partir de `approval_queue_template()`; o core só executa a
# ação quando um pedido `chat_action` chega a APPROVAL_APPROVED.
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_EXPIRED = "expired"
APPROVAL_ACTION_APPROVE = "approve"
APPROVAL_ACTION_REJECT = "reject"
APPROVAL_ACTION_EXPIRE = "expire"

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
APPROVE_WITHOUT_APPROVERS = "approve_without_approvers"  # nem papel nem grupo (F2)
INVALID_APPROVER = "invalid_approver"               # papel/grupo com formato inválido
INVALID_NOTIFY_EMAIL = "invalid_notify_email"
APPROVAL_QUEUE_SHAPE = "approval_queue_shape"       # a fila não tem os estados/ações da aprovação
INVALID_PERIOD_LIMIT = "invalid_period_limit"       # F4: período, quem, máximo ou campo inválidos
TOO_MANY_PERIOD_LIMITS = "too_many_period_limits"


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


class ActionRulePeriodLimit(BaseModel):
    """F4 (v0.1.116): «no máximo N por dia/semana/mês», por pessoa ou para o
    cliente todo — a contar as ações FEITAS, ou a somar um campo
    («encomendas até 5 000 € por dia»). Os períodos são de calendário no fuso
    do cliente (`identity.timezone`; semana = segunda a domingo). Quando a ação
    passaria o máximo vale o `over`. Contagem ilegível (contentor do registo em
    falta, pessoa anónima com `per=user`, valor do campo ilegível ou noutra
    moeda) → falha FECHADA: vale o `over`."""
    model_config = ConfigDict(extra="allow")

    period: Literal["day", "week", "month"] = "day"
    per: Literal["user", "client"] = "user"
    max: float = Field(default=1, ge=0)
    # Vazio = contar ações; senão o campo (do inputSchema da tool) a somar.
    sum_param: str = ""
    currency: Optional[str] = None
    over: Literal["confirm", "approve", "block"] = "block"


class ActionRuleApproval(BaseModel):
    model_config = ConfigDict(extra="allow")

    queue: str = ""                              # chave de `reviewQueues`
    # Quem pode decidir (F2): app roles do Entra (claim `roles`) e/ou object
    # ids de grupos (claim `groups`). Pelo menos um — sem aprovadores o core
    # recusa decidir (falha fechada). Quem pediu nunca aprova.
    roles: List[str] = Field(default_factory=list)
    groups: List[str] = Field(default_factory=list)
    # Prazo do pedido; depois disto a ação já não corre (passa a «expirado»).
    expires_hours: int = Field(default=APPROVAL_EXPIRES_HOURS, ge=1, le=APPROVAL_EXPIRES_MAX_HOURS)
    # Email aos aprovadores quando chega um pedido (até 10).
    notify_emails: List[str] = Field(default_factory=list)


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
    # F4 (v0.1.116): limites por período (contagem ou soma).
    period_limits: List[ActionRulePeriodLimit] = Field(default_factory=list)
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


def _period_limit_problems(pl: Any) -> List[Tuple[str, str]]:
    if not isinstance(pl, Mapping):
        return [(INVALID_PERIOD_LIMIT, ERROR)]
    out: List[Tuple[str, str]] = []
    mx = pl.get("max")
    if (str(pl.get("period") or "day") not in PERIODS or str(pl.get("per") or "user") not in PER
            or not _is_number(mx) or mx < 0):
        out.append((INVALID_PERIOD_LIMIT, ERROR))
    if str(pl.get("over") or "block") not in OVER_MODES:
        out.append((INVALID_MODE, ERROR))
    cur = pl.get("currency")
    if cur not in (None, "") and not _CURRENCY.match(str(cur)):
        out.append((INVALID_CURRENCY, ERROR))
    return out


def approval_queue_template() -> Dict[str, Any]:
    """A fila de aprovação que o Studio cria (estados e ações que o core
    reconhece; os campos são só de leitura — os parâmetros de uma ação a
    aprovar nunca se editam). Rótulos em português; o editor traduz."""
    def field(key, pt, en, order, ftype="text"):
        return {"key": key, "label": {"pt": pt, "en": en}, "type": ftype,
                "editable": False, "order": order}
    return {
        "label": "Aprovações",
        "states": [
            {"id": APPROVAL_PENDING, "kind": "open", "label": "Pendente"},
            {"id": APPROVAL_APPROVED, "kind": "final", "label": "Aprovado"},
            {"id": APPROVAL_REJECTED, "kind": "final", "label": "Recusado"},
            {"id": APPROVAL_EXPIRED, "kind": "final", "label": "Expirado"},
        ],
        "actions": [
            {"id": APPROVAL_ACTION_APPROVE, "from": [APPROVAL_PENDING], "to": APPROVAL_APPROVED,
             "label": "Aprovar"},
            {"id": APPROVAL_ACTION_REJECT, "from": [APPROVAL_PENDING], "to": APPROVAL_REJECTED,
             "label": "Recusar", "note_required": True},
            {"id": APPROVAL_ACTION_EXPIRE, "from": [APPROVAL_PENDING], "to": APPROVAL_EXPIRED,
             "label": "Expirar"},
        ],
        "businessKey": {"prefix": "APR"},
        "fields": [
            field("pedido", "Pedido", "Request", 1),
            field("acao", "Ação", "Action", 2),
            field("parametros", "Parâmetros", "Parameters", 3, "textarea"),
            field("regra", "Regra", "Rule", 4),
            field("motivo", "Motivo", "Reason", 5),
            field("pedido_por", "Pedido por", "Requested by", 6),
            field("prazo", "Prazo", "Deadline", 7, "datetime"),
        ],
    }


def approval_queue_shape_ok(queue: Mapping[str, Any]) -> bool:
    """A fila tem os estados e as ações que o core reconhece?"""
    try:
        states = {str(s.get("id")): str(s.get("kind") or "open")
                  for s in (queue.get("states") or []) if isinstance(s, Mapping)}
        actions = {str(a.get("id")): a for a in (queue.get("actions") or []) if isinstance(a, Mapping)}
        if states.get(APPROVAL_PENDING) not in ("open", "parked"):
            return False
        for sid in (APPROVAL_APPROVED, APPROVAL_REJECTED, APPROVAL_EXPIRED):
            if states.get(sid) != "final":
                return False
        for aid, to in ((APPROVAL_ACTION_APPROVE, APPROVAL_APPROVED),
                        (APPROVAL_ACTION_REJECT, APPROVAL_REJECTED),
                        (APPROVAL_ACTION_EXPIRE, APPROVAL_EXPIRED)):
            a = actions.get(aid)
            if not a or str(a.get("to") or "") != to:
                return False
        return True
    except Exception:  # noqa: BLE001
        return False


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

            plimits = raw.get("period_limits") or []
            if not isinstance(plimits, list):
                add(rid, INVALID_PERIOD_LIMIT, ERROR)
                plimits = []
            if len(plimits) > MAX_PERIOD_LIMITS:
                add(rid, TOO_MANY_PERIOD_LIMITS, ERROR)
            for pl in plimits:
                for code, sev in _period_limit_problems(pl):
                    add(rid, code, sev)
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
                for l in limits) or any(
                isinstance(pl, Mapping) and str(pl.get("over") or "block") == "approve"
                for pl in plimits)
            if uses_approve:
                queue = str(((raw.get("approval") or {}) if isinstance(raw.get("approval"), Mapping)
                             else {}).get("queue") or "")
                if not queue:
                    add(rid, APPROVE_WITHOUT_QUEUE, ERROR)
                elif queue not in queues:
                    add(rid, UNKNOWN_QUEUE, ERROR)
                elif not approval_queue_shape_ok(queues.get(queue) or {}):
                    add(rid, APPROVAL_QUEUE_SHAPE, ERROR)
                appr = raw.get("approval") if isinstance(raw.get("approval"), Mapping) else {}
                roles = appr.get("roles") or []
                groups = appr.get("groups") or []
                roles = roles if isinstance(roles, list) else []
                groups = groups if isinstance(groups, list) else []
                if not roles and not groups:
                    add(rid, APPROVE_WITHOUT_APPROVERS, ERROR)
                if (len(roles) + len(groups) > MAX_APPROVERS
                        or any(not _ROLE.match(str(r)) for r in roles)
                        or any(not _GROUP.match(str(g)) for g in groups)):
                    add(rid, INVALID_APPROVER, ERROR)
                emails = appr.get("notify_emails") or []
                if (not isinstance(emails, list) or len(emails) > MAX_NOTIFY_EMAILS
                        or any(not _EMAIL.match(str(e)) for e in emails)):
                    add(rid, INVALID_NOTIFY_EMAIL, WARNING)
                # D2: a aprovação corre fora da conversa, sem o login de quem
                # pediu — um servidor `per_user` ficaria sem token.
                srv = servers.get(server) if server else None
                if srv and ((srv.get("auth") or {}).get("per_user") is True):
                    add(rid, APPROVE_PER_USER, ERROR)
    except Exception:  # noqa: BLE001 — nunca levanta (contrato do módulo)
        add("", INVALID_ACTION, ERROR)
    return out
