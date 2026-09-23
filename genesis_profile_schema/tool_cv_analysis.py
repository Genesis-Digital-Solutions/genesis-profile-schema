"""
genesis_profile_schema/tool_cv_analysis.py — `tools.config.analyse_cv`, a
Triagem de CVs (v0.1.71, 23 Set 2026 — épico Análise de CVs, Fase 4).

Módulo próprio em vez de mais um bloco no `client_profile_schema.py`; o modelo
entra no `_KNOWN_TOOL_CONFIG_MODELS` de lá.

O que NÃO está aqui, de propósito: um interruptor da máscara e da política de
texto escondido. Mascarar o que o avaliador lê (D2) e tirar o texto escondido
da avaliação são o contrato da tool, não opções — um interruptor seria a porta
para desligar a prova que o art. 10.º do AI Act vai pedir.

Os tectos das listas e dos textos são os do motor do genai-core
(`tools/cv_analysis/engine/criteria.py`: 40 critérios, 500 chars por
descrição, 30 000 chars de anúncio): um modelo de vaga maior do que isso seria
cortado em silêncio ao criar o job.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# As vagas-tipo são NOVAS (sem perfis antigos a preservar) e editáveis pelo
# cliente: `extra="forbid"`. Com `extra="allow"` a exposição por antepassado
# (`exposure_of` sobe até `job_templates`) deixava gravar chaves inventadas
# em cada item — o perfil inchava sem limite (revisão de 23 Set).
_CLOSED = ConfigDict(extra="forbid")

__all__ = [
    "ProfileToolCvCriterionScale",
    "ProfileToolCvTemplateCriterion",
    "ProfileToolCvJobTemplate",
    "ProfileToolCvAnalysisConfig",
]


class ProfileToolCvCriterionScale(BaseModel):
    """Limiar ordenável de um critério (escadas em `tools/cv_analysis/engine/scales.py`
    do genai-core): "Licenciatura em X", "Inglês ≥ B2", "≥ 3 anos"."""
    model_config = _CLOSED

    dimension: Literal["education", "language", "years"]
    # 80 = o corte do core (`criteria._scale_from`).
    min_level: str = Field(default="", max_length=80)
    subject: Optional[str] = Field(default=None, max_length=80)


class ProfileToolCvTemplateCriterion(BaseModel):
    """Um critério de um modelo de vaga — a mesma forma que o workspace confirma
    (o core normaliza-o outra vez ao criar o job e volta a correr o lint de
    discriminação: um modelo não salta o motivo obrigatório da D9)."""
    model_config = _CLOSED

    type: Literal["EDUCATION", "EXPERIENCE", "LANGUAGE", "CERTIFICATION", "SKILL",
                  "DOMAIN", "LOCATION", "AVAILABILITY", "LEGAL", "OTHER"] = "OTHER"
    # `\S`: só espaços não é critério (o core tira-os e deitava-o fora em silêncio).
    description: str = Field(min_length=1, max_length=500, pattern=r"\S")
    # Ausente = desejável: é o que o motor do core lê (`normalize_criteria`,
    # `bool(obj.get("must_have"))`) — o default do schema tem de ser o comportamento.
    must_have: bool = False
    # Só conta nos desejáveis (ordena candidatos, nunca enviesa o veredicto).
    weight: int = Field(default=1, ge=1, le=3)
    scale: Optional[ProfileToolCvCriterionScale] = None
    needs_protected_attr: Optional[Literal["work_permit", "driving_licence", "min_age"]] = None


class ProfileToolCvJobTemplate(BaseModel):
    """Vaga-tipo que o recrutador escolhe no passo 1 do workspace em vez de
    colar o anúncio. Critérios em lista: o workspace mostra-os para confirmar.
    Sem critérios não é vaga-tipo — o core deitá-la-ia fora em silêncio."""
    model_config = _CLOSED

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=200, pattern=r"\S")
    requirements: str = Field(default="", max_length=30000)
    criteria: List[ProfileToolCvTemplateCriterion] = Field(min_length=1, max_length=40)


class ProfileToolCvAnalysisConfig(BaseModel):
    """tools.config.analyse_cv — Triagem de CVs (épico Análise de CVs).

    Os pisos e tectos são os que o genai-core já aplica
    (`tools/cv_analysis/jobs/settings.py`): o schema diz o que o core honra,
    em vez de aceitar um valor que o core corta em silêncio.
    - prompt_preset / prompt_custom: overlay de domínio (tool_playbooks) sobre o
      contrato base da avaliação e da proposta de critérios — nunca o relaxa.
    - retention_days: registo do job (D3). Decisão de 23 Set 2026: 183–365. O PDF
      original apaga-se aos 200 dias pela regra de ciclo de vida do Studio.
    - max_batch / parallelism / deployment: custo e quota do cliente — internos."""
    model_config = ConfigDict(extra="allow")

    prompt_preset: str = ""
    prompt_custom: str = ""
    retention_days: int = Field(default=183, ge=183, le=365)
    # Piso = o default: um lote maior é pedido do cliente, um menor nunca.
    max_batch: int = Field(default=50, ge=50, le=500)
    parallelism: int = Field(default=4, ge=1, le=16)
    # Vazio = o modelo do agente do cliente.
    deployment: str = ""
    job_templates: List[ProfileToolCvJobTemplate] = Field(
        default_factory=list,
        max_length=200,
        json_schema_extra={"requires_tool": "analyse_cv"},
    )

    @field_validator("job_templates")
    @classmethod
    def _ids_unicos(cls, v: List[ProfileToolCvJobTemplate]) -> List[ProfileToolCvJobTemplate]:
        # O core fica com a primeira de ids repetidos e ignora as outras.
        ids = [t.id for t in v]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"ids de vagas-tipo repetidos: {', '.join(dup)}")
        return v
