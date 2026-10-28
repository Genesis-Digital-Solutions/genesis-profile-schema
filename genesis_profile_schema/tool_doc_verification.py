"""
genesis_profile_schema/tool_doc_verification.py — `tools.config.verify_documents`,
a Verificação Documental (v0.1.100, 8 Out 2026 — épico Verificação Documental,
Fase 4; contrato 101).

Módulo próprio em vez de mais um bloco no `client_profile_schema.py`; o modelo
entra no `_KNOWN_TOOL_CONFIG_MODELS` de lá.

O que NÃO está aqui, de propósito:
  * o login. O genai-core exige-o em todas as rotas `/doc-verification/*`, seja
    qual for o `frontend.auth.mode` — um interruptor no perfil seria a porta para
    o desligar. O editor do Studio avisa quando o perfil não pede login;
  * os nomes dos papéis do Entra (`DOCVER_ROLE_NAMES`) e os tenants permitidos
    (`DOCVER_ALLOWED_TENANTS`): são segurança, e segurança vive na env do
    Container App, nunca no perfil;
  * a deteção de marcas de classificação: é o contrato do módulo, não opção.

Todos os campos são INTERNOS (custo, quota e o caso de uso vendido); a tabela de
exposição não os abre ao cliente.
"""

from __future__ import annotations

from typing import Annotated, Dict, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .field_definition import I18nHelp

__all__ = ["DocVerificationLabels", "ProfileToolDocVerificationConfig", "MAX_LABEL_TEXT"]

#: Um nome de ecrã (título, nome do caso, exemplo): curto. A frase do subtítulo cabe nisto também.
MAX_LABEL_TEXT = 200


def _short(value: Dict[str, str]) -> Dict[str, str]:
    for lang, text in value.items():
        if len(text) > MAX_LABEL_TEXT:
            raise ValueError(f"texto em {lang!r} com mais de {MAX_LABEL_TEXT} caracteres")
    return value


class DocVerificationLabels(BaseModel):
    """Os nomes do módulo no ecrã desta variante (28 Out 2026) — {língua: texto}, todos opcionais.

    Vazio (ou a língua em falta) = o texto neutro do ESQUEMA (`engine/schemes.py` do core, `display`), que
    nunca nomeia um cliente. Serve para um cliente chamar ao caso «candidatura», «processo», «pedido»…
    - title: o título do módulo («Análise de candidaturas»);
    - subtitle: a frase por baixo do título;
    - case_singular / case_plural: o nome do caso («candidatura» / «candidaturas»), em minúsculas — o
      ecrã põe a maiúscula onde precisa («Nova candidatura», «Candidaturas»);
    - name_example: o exemplo do campo do nome ao criar um caso (sem o «ex.:»)."""
    model_config = ConfigDict(extra="forbid")

    title: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)
    subtitle: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)
    case_singular: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)
    case_plural: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)
    name_example: Annotated[I18nHelp, AfterValidator(_short)] = Field(default_factory=dict)


class ProfileToolDocVerificationConfig(BaseModel):
    """tools.config.verify_documents — Verificação Documental.

    Os limites são os que o genai-core aplica (`tools/doc_verification/jobs/
    settings.py`): o schema diz o que o core honra, em vez de
    aceitar um valor que o core corta em silêncio.
    - scheme: o esquema dos casos NOVOS («concursos» ou «concursos@2026.10» para
      fixar a versão). Um caso guarda o seu ao nascer — mudar isto não mexe nos
      casos que já existem.
    - parallelism: lotes de cada peça lidos em paralelo pelo modelo. Medido a 8 Out
      2026: 226 páginas em 20 min com 1, 7,8 min com 4. Limitado pela quota de
      tokens por minuto do modelo do cliente.
    - deployment: vazio = o modelo do agente do container (não segue a variante).
    - labels: os nomes do módulo no ecrã desta variante (vazio = os do esquema)."""
    model_config = ConfigDict(extra="allow")

    # A mesma gramática que o core aceita ao criar um caso (`create_case`). Texto
    # com sugestões (`combobox`; os esquemas da biblioteca do core estão nas
    # `options` do ui_text), NUNCA `Literal`: um esquema novo escrito pelo Studio
    # (pin mais novo) partia o carregamento do perfil inteiro num core com o pin
    # antigo. O core, que conhece a biblioteca, usa o esquema por omissão e
    # regista quando não conhece o pedido.
    scheme: str = Field(default="concursos", pattern=r"^[a-z0-9][a-z0-9_.@-]{0,63}$")
    parallelism: int = Field(default=4, ge=1, le=8)
    deployment: str = Field(default="", max_length=128)
    # Os nomes do módulo no ecrã (28 Out 2026). `None` (o que o blob gravado traz quando nunca se mexeu) =
    # os textos neutros do esquema.
    labels: Optional[DocVerificationLabels] = None
