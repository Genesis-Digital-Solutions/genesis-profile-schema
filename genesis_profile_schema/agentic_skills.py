"""
agentic_skills.py — `agentic.skills`: os PROCEDIMENTOS do agente (passo 15 do épico
«Agente colega», A6-b, 26 Nov 2026; nome no ecrã: «Procedimentos», para não colidir
com as skills do agente do Studio).

Um procedimento diz COMO se faz uma tarefa neste cliente (checklist, passos,
critérios) no formato aberto SKILL.md (agentskills.io): `name` + `description` no
cabeçalho e o corpo em Markdown. Os factos ficam na base de conhecimento, o
comportamento nas `custom_instructions` e as regras de negócio nas regras de ação.

Cada entrada da lista é UMA VERSÃO de um procedimento:
  • `status`: `proposed` (importado ou proposto, ainda por rever) → `approved`
    (uma pessoa leu e aprovou ESTA versão) → `retired` (substituída ou retirada);
  • só uma versão `approved` por nome; o core usa só as aprovadas e só se o
    `digest` bater com o texto (`skill_digest`): um texto mexido depois da
    aprovação deixa de valer (falha fechada, no core e aqui);
  • `fronts`: onde vale — `_base` (o principal) e/ou slugs de variantes. Nunca
    «todas»: uma frente Separada pode ser de outro cliente, escolhe-se à mão;
  • `source`: `import` (um `.md` de fora — texto de TERCEIROS, não confiável) ou
    `learned` (proposto pelo agente; o A6 aprendido usa o mesmo formato);
  • `license` obrigatória para aprovar uma importada, com `license_accepted`
    (P25: a licença é decidida por uma pessoa, caso a caso);
  • `allowed_tools` (o `allowed-tools` do SKILL.md) fica só registado: um
    procedimento ORIENTA, nunca autoriza — não dá ferramentas, regras nem
    permissões (regra de ouro do pack).

Quem escreve: só o Studio, pelo ecrã «Procedimentos» (o editor geral recusa mudar
esta lista). O GAIBO não vê a área `agentic` (`AREA_FLOOR`).

Tetos medidos a 26 Nov 2026 em 111 SKILL.md reais (mediana 9 300 carateres /
2 340 tokens o200k; p80 17 900 / 4 100; p90 29 000 / 7 400): o corpo até
24 000 carateres (~5 500 tokens; cabem 98 dos 111, e a especificação recomenda
menos de 5 000 tokens); a descrição até 1 024 (o máximo da especificação).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: `name` da especificação SKILL.md: 1–64, minúsculas ASCII e dígitos, hífen só entre eles.
SKILL_NAME_RE = re.compile(r"^(?=.{1,64}$)[a-z0-9]+(?:-[a-z0-9]+)*$", re.ASCII)
SKILL_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
#: Uma frente: `_base` (o principal) ou o slug de uma variante (a forma do `action_rules`).
SKILL_FRONT_BASE = "_base"
_FRONT_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$", re.ASCII)
_WARNING_CODE = re.compile(r"^[a-z][a-z0-9_]{0,39}$", re.ASCII)

SKILL_STATUSES = ("proposed", "approved", "retired")
SKILL_SOURCES = ("import", "learned")

NAME_MAX = 64
DESCRIPTION_MAX = 1024
BODY_MAX = 24_000
LICENSE_MAX = 200
ORIGIN_MAX = 200
COMPATIBILITY_MAX = 500
WHO_MAX = 320
MAX_ALLOWED_TOOLS = 30
ALLOWED_TOOL_MAX = 120
MAX_FRONTS = 30
MAX_WARNINGS = 30
#: Entradas (versões) na lista inteira, e a soma dos corpos — o perfil é lido em cada pedido.
MAX_SKILLS = 40
MAX_TOTAL_BODY = 200_000
MAX_VERSION = 100_000


def skill_digest(name: str, description: str, body: str) -> str:
    """O hash do que chega ao modelo (nome, descrição e corpo). É o que uma pessoa
    aprova; o core recalcula-o antes de usar. A mesma função no core
    (`core/agent/skills/model.py`) e no Studio (`backend/procedures/model.py`),
    presas pelo mesmo vetor de teste."""
    raw = json.dumps([str(name), str(description), str(body)], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AgenticSkill(BaseModel):
    """Uma versão de um procedimento."""
    model_config = ConfigDict(extra="allow")

    name: str
    version: int = Field(default=1, ge=1, le=MAX_VERSION)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX)
    body: str = Field(min_length=1, max_length=BODY_MAX)
    status: Literal["proposed", "approved", "retired"] = "proposed"
    source: Literal["import", "learned"] = "import"
    fronts: List[str] = Field(default_factory=lambda: [SKILL_FRONT_BASE])
    origin: Optional[str] = Field(default=None, max_length=ORIGIN_MAX)
    license: Optional[str] = Field(default=None, max_length=LICENSE_MAX)
    license_accepted: Optional[bool] = None
    compatibility: Optional[str] = Field(default=None, max_length=COMPATIBILITY_MAX)
    allowed_tools: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
    digest: Optional[str] = None
    proposed_by: Optional[str] = Field(default=None, max_length=WHO_MAX)
    proposed_at: Optional[int] = None
    approved_by: Optional[str] = Field(default=None, max_length=WHO_MAX)
    approved_at: Optional[int] = None
    retired_at: Optional[int] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not SKILL_NAME_RE.fullmatch(v or ""):
            raise ValueError("nome do procedimento: minúsculas e dígitos, separados por um hífen (até 64)")
        return v

    @field_validator("fronts")
    @classmethod
    def _fronts(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("um procedimento vale pelo menos numa frente")
        if len(v) > MAX_FRONTS or len(v) != len(set(v)):
            raise ValueError(f"frentes repetidas ou mais de {MAX_FRONTS}")
        for f in v:
            if f != SKILL_FRONT_BASE and not _FRONT_SLUG.fullmatch(str(f or "")):
                raise ValueError("frente inválida: `_base` ou o slug de uma variante")
        return v

    @field_validator("allowed_tools")
    @classmethod
    def _tools(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        if len(v) > MAX_ALLOWED_TOOLS or any(not isinstance(t, str) or not t or len(t) > ALLOWED_TOOL_MAX
                                             for t in v):
            raise ValueError(f"allowed_tools: até {MAX_ALLOWED_TOOLS} nomes, cada um até {ALLOWED_TOOL_MAX}")
        return v

    @field_validator("warnings")
    @classmethod
    def _warnings(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        if len(v) > MAX_WARNINGS or any(not _WARNING_CODE.fullmatch(str(w or "")) for w in v):
            raise ValueError("avisos: códigos curtos (minúsculas, dígitos, _)")
        return v

    @field_validator("digest")
    @classmethod
    def _digest(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not SKILL_DIGEST_RE.fullmatch(v):
            raise ValueError("digest: sha-256 em hexadecimal minúsculo")
        return v

    @model_validator(mode="after")
    def _approved(self) -> "AgenticSkill":
        if self.status != "approved":
            return self
        if not self.digest or self.digest != skill_digest(self.name, self.description, self.body):
            raise ValueError(f"procedimento {self.name} v{self.version}: o texto mudou depois de aprovado")
        if not (self.approved_by or "").strip() or not self.approved_at:
            raise ValueError(f"procedimento {self.name} v{self.version}: aprovado sem quem nem quando")
        if self.source == "import" and (not (self.license or "").strip() or self.license_accepted is not True):
            raise ValueError(f"procedimento {self.name} v{self.version}: importado sem licença aceite")
        return self


def skills_problems(skills: List[AgenticSkill]) -> List[str]:
    """O que a lista inteira não pode ter (vazio = boa)."""
    out: List[str] = []
    if len(skills) > MAX_SKILLS:
        out.append(f"no máximo {MAX_SKILLS} versões de procedimentos")
    if sum(len(s.body) for s in skills) > MAX_TOTAL_BODY:
        out.append(f"os procedimentos somam mais de {MAX_TOTAL_BODY} carateres")
    keys = [(s.name, s.version) for s in skills]
    if len(keys) != len(set(keys)):
        out.append("o mesmo procedimento com a mesma versão repetido")
    approved = [s.name for s in skills if s.status == "approved"]
    if len(approved) != len(set(approved)):
        out.append("mais do que uma versão aprovada do mesmo procedimento")
    return out


__all__ = ["AgenticSkill", "skill_digest", "skills_problems", "SKILL_NAME_RE", "SKILL_DIGEST_RE",
           "SKILL_FRONT_BASE", "SKILL_STATUSES", "SKILL_SOURCES", "NAME_MAX", "DESCRIPTION_MAX", "BODY_MAX",
           "LICENSE_MAX", "ORIGIN_MAX", "COMPATIBILITY_MAX", "MAX_SKILLS", "MAX_TOTAL_BODY", "MAX_FRONTS",
           "MAX_ALLOWED_TOOLS"]
