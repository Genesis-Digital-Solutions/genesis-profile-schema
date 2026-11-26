"""
agentic_packages.py — `agentic.packages`: os PACOTES DE REGRAS subscritos (A6-c do épico «Agente colega», 26 Nov 2026;
nome no ecrã: «Pacotes de regras»).

Um pacote de regras traz regras com o artigo de onde vêm (ex.: RGPD, AI Act, defesa do consumidor, políticas internas),
assinadas pelo EMISSOR, com os casos de teste e o texto que as explica (SKILL.md). O core aplica-as a cada ação do
agente e elas só APERTAM as Regras das ações do cliente (bloquear, ou mandar a uma pessoa), nunca aliviam.

Cada entrada da lista é UMA VERSÃO de um pacote (`ref` = `emissor/id@versão`):
  • `files` — os ficheiros do pacote tal como assinados (`manifest.json`, `manifest.jws`, `rules.json`, `SKILL.md`,
    `tests.json`). O core volta a verificar a assinatura contra os emissores de confiança do AMBIENTE do core
    (`RULE_PACKAGE_ISSUERS`), nunca contra o que vem aqui: o perfil guarda o conteúdo, não a confiança;
  • `status`: `proposed` (importado, por rever) → `approved` (uma pessoa reviu os testes e as lacunas e aprovou ESTA
    versão) → `retired`; só uma versão aprovada por pacote (`emissor/id`);
  • `mode`: `log_only` (avalia e regista o que faria — o modo para começar) ou `enforce`;
  • `fronts`: onde vale — `_base` (o principal), slugs de variantes, ou `*` (todas).

Quem escreve: só o Studio, pelo ecrã «Pacotes de regras». O GAIBO não vê a área `agentic` (`AREA_FLOOR`).
Tetos: até 8 versões na lista, cada ficheiro até 256 KiB em bytes UTF-8 (o do verificador do core) e a lista inteira até 512 000
carateres — o perfil é lido em cada pedido; um pacote real mede dezenas de KiB (o exemplo, 9 KiB).
"""

from __future__ import annotations

import re
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: `emissor/id@versão` (as mesmas formas do verificador do core, `core/agent/packages/verify.py`).
PACKAGE_REF_RE = re.compile(r"^([a-z0-9][a-z0-9-]{0,63})/([a-z0-9][a-z0-9-]{0,63})@[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$",
                            re.ASCII)
PACKAGE_FILE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$", re.ASCII)
_FRONT_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$", re.ASCII)
PACKAGE_FRONT_BASE = "_base"
PACKAGE_FRONT_ALL = "*"
PACKAGE_STATUSES = ("proposed", "approved", "retired")
PACKAGE_MODES = ("log_only", "enforce")
REQUIRED_FILES = ("manifest.json", "manifest.jws")

MAX_PACKAGES = 8
MAX_FILES = 8
FILE_MAX = 256 * 1024
MAX_TOTAL_CHARS = 512_000
MAX_FRONTS = 30
WHO_MAX = 320


class AgenticPackage(BaseModel):
    """Uma versão subscrita de um pacote de regras."""
    model_config = ConfigDict(extra="allow")

    ref: str
    status: Literal["proposed", "approved", "retired"] = "proposed"
    mode: Literal["log_only", "enforce"] = "log_only"
    fronts: List[str] = Field(default_factory=lambda: [PACKAGE_FRONT_BASE])
    files: Dict[str, str]
    imported_by: Optional[str] = Field(default=None, max_length=WHO_MAX)
    imported_at: Optional[int] = None
    approved_by: Optional[str] = Field(default=None, max_length=WHO_MAX)
    approved_at: Optional[int] = None
    retired_at: Optional[int] = None

    @field_validator("ref")
    @classmethod
    def _ref(cls, v: str) -> str:
        if not PACKAGE_REF_RE.fullmatch(v or ""):
            raise ValueError("pacote: `emissor/id@versão` (minúsculas, dígitos e hífen; versão 1.2.3)")
        return v

    @field_validator("fronts")
    @classmethod
    def _fronts(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("um pacote vale pelo menos numa frente (`*` = todas)")
        if len(v) > MAX_FRONTS or len(v) != len(set(v)):
            raise ValueError(f"frentes repetidas ou mais de {MAX_FRONTS}")
        for f in v:
            if f not in (PACKAGE_FRONT_BASE, PACKAGE_FRONT_ALL) and not _FRONT_SLUG.fullmatch(str(f or "")):
                raise ValueError("frente inválida: `_base`, `*` ou o slug de uma variante")
        return v

    @field_validator("files")
    @classmethod
    def _files(cls, v: Dict[str, str]) -> Dict[str, str]:
        if not v or len(v) > MAX_FILES:
            raise ValueError(f"um pacote tem de 1 a {MAX_FILES} ficheiros")
        for name, text in v.items():
            if not PACKAGE_FILE_RE.fullmatch(str(name or "")):
                raise ValueError("nome de ficheiro do pacote inválido")
            # Em BYTES UTF-8, como o verificador do core (um texto acentuado perto do teto passava aqui e falhava lá).
            if not isinstance(text, str) or len(text.encode("utf-8")) > FILE_MAX:
                raise ValueError(f"ficheiro do pacote com mais de {FILE_MAX} bytes")
        missing = [f for f in REQUIRED_FILES if f not in v]
        if missing:
            raise ValueError("pacote sem manifesto assinado (`manifest.json` + `manifest.jws`)")
        return v

    @model_validator(mode="after")
    def _approved(self) -> "AgenticPackage":
        if self.status == "approved" and (not (self.approved_by or "").strip() or not self.approved_at):
            raise ValueError(f"pacote {self.ref}: aprovado sem quem nem quando")
        return self

    @property
    def package_id(self) -> str:
        """`emissor/id` (sem a versão)."""
        return self.ref.split("@", 1)[0]


def packages_problems(packages: List[AgenticPackage]) -> List[str]:
    """O que a lista inteira não pode ter (vazio = boa)."""
    out: List[str] = []
    if len(packages) > MAX_PACKAGES:
        out.append(f"no máximo {MAX_PACKAGES} versões de pacotes de regras")
    if sum(len(t) for p in packages for t in p.files.values()) > MAX_TOTAL_CHARS:
        out.append(f"os pacotes de regras somam mais de {MAX_TOTAL_CHARS} carateres")
    refs = [p.ref for p in packages]
    if len(refs) != len(set(refs)):
        out.append("a mesma versão de um pacote repetida")
    approved = [p.package_id for p in packages if p.status == "approved"]
    if len(approved) != len(set(approved)):
        out.append("mais do que uma versão aprovada do mesmo pacote")
    return out


__all__ = ["AgenticPackage", "packages_problems", "PACKAGE_REF_RE", "PACKAGE_FILE_RE", "PACKAGE_FRONT_BASE",
           "PACKAGE_FRONT_ALL", "PACKAGE_STATUSES", "PACKAGE_MODES", "REQUIRED_FILES", "MAX_PACKAGES", "MAX_FILES",
           "FILE_MAX", "MAX_TOTAL_CHARS", "MAX_FRONTS"]
