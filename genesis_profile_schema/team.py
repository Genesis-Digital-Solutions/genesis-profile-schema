"""
genesis_profile_schema/team.py — Equipa e papéis do produto (v0.1.114, pack
«Equipa e papéis», 14 Out 2026).

UM sítio para «quem pode fazer o quê» em todo o produto: o cliente define
PAPÉIS com nomes do negócio («Aprovadores», «Revisores do Intake»), cada um
com CAPACIDADES de qualquer módulo; as PESSOAS e o ÂMBITO de cada atribuição
(todas as frentes ou uma variante) vivem no genai-core (membros do produto,
ligados a `tid`+`oid`), geridos no GAIBO e no Studio pela mesma API.

Simples de propósito (decisão do Bruno): os papéis vivem só no perfil BASE
(um catálogo por cliente); a separação por variante faz-se na atribuição.
Cada módulo tem um interruptor (`modules`): desligado = exatamente como hoje;
ligado = as capacidades dos papéis JUNTAM-SE ao que o módulo já tem
configurado. Um papel pode também aceitar papéis/grupos do Entra
(`entra`, «Avançado») para clientes cuja TI o exija.

O catálogo (`CAPABILITIES`) é a fonte de verdade das capacidades: o core
aplica-as, o Studio e o GAIBO mostram-nas em palavras (`label`, `help`).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

# ── Módulos e capacidades ────────────────────────────────────────────────────
MODULE_TEAM = "team"
MODULE_APPROVALS = "approvals"
MODULE_QUEUES = "queues"
MODULE_INTAKE = "intake"
MODULE_DOCVER = "docver"
MODULE_VARIANT_ACCESS = "variant_access"
MODULES: Tuple[str, ...] = (MODULE_APPROVALS, MODULE_QUEUES, MODULE_INTAKE, MODULE_DOCVER,
                            MODULE_VARIANT_ACCESS)


def _cap(cid: str, module: str, pt: str, en: str, hpt: str, hen: str, target: str = "") -> Dict[str, Any]:
    return {"id": cid, "module": module, "label": {"pt": pt, "en": en},
            "help": {"pt": hpt, "en": hen}, "target": target}


#: O catálogo. `target` = o que se pode escrever depois de `:` para limitar a
#: capacidade (ex.: `queue.operate:reclamacoes`); vazio = sem alvo.
CAPABILITIES: Tuple[Dict[str, Any], ...] = (
    _cap("team.manage", MODULE_TEAM, "Gerir a equipa", "Manage the team",
         "Convidar pessoas e dar ou tirar papéis.", "Invite people and give or remove roles."),
    _cap("variant.enter", MODULE_VARIANT_ACCESS, "Entrar na frente", "Enter the front",
         "Usar o assistente desta frente.", "Use this front's assistant."),
    _cap("actions.approve", MODULE_APPROVALS, "Aprovar ações do assistente", "Approve assistant actions",
         "Decidir os pedidos de aprovação (nunca os próprios).", "Decide approval requests (never your own).",
         target="rule"),
    _cap("queue.operate", MODULE_QUEUES, "Tratar pedidos da fila", "Handle queue requests",
         "Reclamar e decidir os pedidos da fila.", "Claim and decide the queue's requests.", target="queue"),
    _cap("intake.view", MODULE_INTAKE, "Intake: ver processos", "Intake: view cases",
         "Ver os processos e as respostas.", "See cases and answers."),
    _cap("intake.create", MODULE_INTAKE, "Intake: criar e convidar", "Intake: create and invite",
         "Abrir processos e convidar quem responde.", "Open cases and invite respondents."),
    _cap("intake.review", MODULE_INTAKE, "Intake: 1.ª validação", "Intake: first review",
         "Validar o resultado proposto.", "Review the proposed outcome."),
    _cap("intake.second_review", MODULE_INTAKE, "Intake: 2.ª validação", "Intake: second review",
         "Confirmar quando a regra pede uma 2.ª pessoa.", "Confirm when a second person is required."),
    _cap("intake.export", MODULE_INTAKE, "Intake: documentos", "Intake: documents",
         "Descarregar os documentos dos processos.", "Download the cases' documents."),
    _cap("intake.quality", MODULE_INTAKE, "Intake: controlo de qualidade", "Intake: quality control",
         "Fazer o controlo de qualidade mensal.", "Run the monthly quality control."),
    _cap("docver.read", MODULE_DOCVER, "Casos: ver", "Cases: view",
         "Listar e ver os casos de verificação.", "List and view verification cases."),
    _cap("docver.write", MODULE_DOCVER, "Casos: criar e trabalhar", "Cases: create and work",
         "Criar casos, carregar documentos e exportar.", "Create cases, upload documents and export."),
    _cap("docver.decide", MODULE_DOCVER, "Casos: decidir", "Cases: decide",
         "Marcar as conclusões dos requisitos.", "Mark the requirements' conclusions."),
    _cap("docver.evidence", MODULE_DOCVER, "Casos: registo de evidência", "Cases: evidence register",
         "Gerir as fichas de evidência (certidões, alvarás…).", "Manage evidence records (certificates…)."),
    _cap("docver.admin", MODULE_DOCVER, "Casos: administrar", "Cases: administer",
         "Tudo nos casos, incluindo apagar.", "Everything on cases, including delete."),
)
CAPABILITY_IDS: Tuple[str, ...] = tuple(c["id"] for c in CAPABILITIES)
_TARGETED = {c["id"] for c in CAPABILITIES if c["target"]}

MAX_ROLES = 50
MAX_CAPABILITIES = 40
MAX_ENTRA = 20

_ROLE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$", re.ASCII)
_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", re.ASCII)
_ENTRA_ROLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$", re.ASCII)
_GROUP = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", re.ASCII)

# Problemas (códigos estáveis; o Studio e o GAIBO traduzem-nos).
ERROR = "error"
WARNING = "warning"
INVALID_ROLE_ID = "invalid_role_id"
DUPLICATE_ROLE_ID = "duplicate_role_id"
UNKNOWN_CAPABILITY = "unknown_capability"
INVALID_TARGET = "invalid_target"
INVALID_ENTRA = "invalid_entra"
TOO_MANY = "too_many"
MODULE_WITHOUT_ROLE = "module_without_role"     # módulo ligado, nenhum papel com capacidade dele
NO_TEAM_MANAGER = "no_team_manager"             # ninguém pode gerir a equipa


# ── Modelos ──────────────────────────────────────────────────────────────────

class TeamEntra(BaseModel):
    """«Avançado»: papéis/grupos do Entra que também valem como este papel."""
    model_config = ConfigDict(extra="allow")

    roles: List[str] = Field(default_factory=list)     # claim `roles`
    groups: List[str] = Field(default_factory=list)    # claim `groups` (id do objeto)


class TeamRole(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = ""                                       # estável (vai para as atribuições)
    label: str = ""                                    # nome do negócio
    # Capacidades do catálogo; com alvo: `queue.operate:reclamacoes`.
    capabilities: List[str] = Field(default_factory=list)
    entra: Optional[TeamEntra] = None


class TeamModules(BaseModel):
    """Interruptores por módulo — desligado = exatamente como hoje."""
    model_config = ConfigDict(extra="allow")

    approvals: bool = False
    queues: bool = False
    intake: bool = False
    docver: bool = False
    variant_access: bool = False


class ProfileTeam(BaseModel):
    """`team` do perfil (só o BASE conta). Desligado por omissão."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    modules: TeamModules = Field(default_factory=TeamModules)
    roles: List[TeamRole] = Field(default_factory=list)


# ── Papéis prontos (simples de usar) ─────────────────────────────────────────

_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    MODULE_TEAM: [{"id": "gestor-equipa", "label": "Gestor da equipa", "capabilities": ["team.manage"]}],
    MODULE_APPROVALS: [{"id": "aprovador", "label": "Aprovador", "capabilities": ["actions.approve"]}],
    MODULE_QUEUES: [{"id": "operador-fila", "label": "Operador da fila", "capabilities": ["queue.operate"]}],
    MODULE_VARIANT_ACCESS: [{"id": "utilizador", "label": "Utilizador", "capabilities": ["variant.enter"]}],
    MODULE_INTAKE: [
        {"id": "intake-comercial", "label": "Intake — Comercial", "capabilities": ["intake.view", "intake.create"]},
        {"id": "intake-revisor", "label": "Intake — Revisor", "capabilities": ["intake.view", "intake.review"]},
        {"id": "intake-supervisor", "label": "Intake — Supervisor",
         "capabilities": ["intake.view", "intake.review", "intake.second_review", "intake.export"]},
        {"id": "intake-compliance", "label": "Intake — Compliance",
         "capabilities": ["intake.view", "intake.export", "intake.quality"]},
    ],
    MODULE_DOCVER: [
        {"id": "casos-leitor", "label": "Casos — Leitor", "capabilities": ["docver.read"]},
        {"id": "casos-analista", "label": "Casos — Analista", "capabilities": ["docver.read", "docver.write"]},
        {"id": "casos-decisor", "label": "Casos — Decisor", "capabilities": ["docver.read", "docver.decide"]},
        {"id": "casos-evidencia", "label": "Casos — Gestor de evidência",
         "capabilities": ["docver.read", "docver.evidence"]},
        {"id": "casos-admin", "label": "Casos — Administrador", "capabilities": ["docver.admin"]},
    ],
}


def role_templates(module: str) -> List[Dict[str, Any]]:
    """Os papéis prontos de um módulo (cópias novas)."""
    return [dict(r, capabilities=list(r["capabilities"])) for r in _TEMPLATES.get(module, [])]


def capability_of(entry: str) -> Tuple[str, str]:
    """`queue.operate:reclamacoes` → (`queue.operate`, `reclamacoes`)."""
    cid, _, target = str(entry or "").partition(":")
    return cid.strip(), target.strip()


def capability_module(cid: str) -> str:
    for c in CAPABILITIES:
        if c["id"] == cid:
            return c["module"]
    return ""


# ── Problemas ────────────────────────────────────────────────────────────────

def team_problems(profile: Mapping[str, Any]) -> List[Dict[str, str]]:
    """`[{"role_id", "code", "severity"}]` do bloco `team` (vazio = tudo bem).
    Nunca levanta."""
    out: List[Dict[str, str]] = []

    def add(role_id: str, code: str, severity: str) -> None:
        out.append({"role_id": role_id, "code": code, "severity": severity})

    try:
        team = (profile or {}).get("team") or {}
        if not isinstance(team, Mapping):
            return out
        roles = team.get("roles") or []
        if not isinstance(roles, list):
            add("", INVALID_ROLE_ID, ERROR)
            return out
        if len(roles) > MAX_ROLES:
            add("", TOO_MANY, ERROR)
        seen: set = set()
        granted: set = set()
        for raw in roles:
            if not isinstance(raw, Mapping):
                add("", INVALID_ROLE_ID, ERROR)
                continue
            rid = str(raw.get("id") or "")
            if not _ROLE_ID.match(rid):
                add(rid, INVALID_ROLE_ID, ERROR)
            elif rid in seen:
                add(rid, DUPLICATE_ROLE_ID, ERROR)
            seen.add(rid)
            caps = raw.get("capabilities") or []
            if not isinstance(caps, list) or len(caps) > MAX_CAPABILITIES:
                add(rid, TOO_MANY, ERROR)
                caps = []
            for entry in caps:
                cid, target = capability_of(entry)
                if cid not in CAPABILITY_IDS:
                    add(rid, UNKNOWN_CAPABILITY, ERROR)
                    continue
                if target and (cid not in _TARGETED or not _TARGET.match(target)):
                    add(rid, INVALID_TARGET, ERROR)
                granted.add(cid)
            entra = raw.get("entra") or {}
            if isinstance(entra, Mapping):
                eroles = entra.get("roles") or []
                egroups = entra.get("groups") or []
                if (not isinstance(eroles, list) or not isinstance(egroups, list)
                        or len(eroles) + len(egroups) > MAX_ENTRA
                        or any(not _ENTRA_ROLE.match(str(x)) for x in eroles)
                        or any(not _GROUP.match(str(x)) for x in egroups)):
                    add(rid, INVALID_ENTRA, ERROR)
        if team.get("enabled") is True:
            if "team.manage" not in granted:
                add("", NO_TEAM_MANAGER, WARNING)
            mods = team.get("modules") or {}
            for m in MODULES:
                if isinstance(mods, Mapping) and mods.get(m) is True and not any(
                        capability_module(c) == m for c in granted):
                    add(m, MODULE_WITHOUT_ROLE, WARNING)
    except Exception:  # noqa: BLE001 — nunca levanta
        add("", INVALID_ROLE_ID, ERROR)
    return out
