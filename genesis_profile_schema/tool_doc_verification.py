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

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ProfileToolDocVerificationConfig"]


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
    - deployment: vazio = o modelo do agente do container (não segue a variante)."""
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
