"""
genesis_profile_schema/attached_inline.py — `tool_limits.attached_inline`, o
documento anexado INTEIRO no contexto (C5 do parecer GPT-6 Astra; v0.1.72,
25 Set 2026).

Módulo próprio em vez de mais um bloco no `client_profile_schema.py`; o modelo
monta-se em `ProfileToolLimits` com uma linha.

Quando ligado, o genai-core (`core/agent/attached_inline.py`) põe o texto
integral dos documentos anexados numa mensagem estável no início da conversa,
em vez de o modelo os consultar aos pedaços pela tool `read_attached_document`
— desde que caibam no tecto abaixo e o modelo do turno seja elegível. O que não
cabe continua pela tool; nunca se corta um documento em silêncio.

Porquê em `tool_limits` e não em `tools.config.read_attached_document`: o
`tool_limits` é tipado e os seus defaults entram no perfil que o core funde
(chave ausente = default do schema), e vive ao lado do
`max_attached_doc_chars`, que tem de acompanhar o tecto (≈4,2 chars por token
em PT: 190 000 tokens ≈ 800 000 chars).

Exposição `_I` (decisão D6 do Bruno): é uma alavanca de custo nossa — um turno
frio com 190k tokens de documento no GPT-6 Astra custa ~1,90 USD.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ProfileAttachedInline", "ATTACHED_INLINE_MAX_TOKENS"]

# O tecto que o core HONRA: `HARD_LINE − RESERVE` = 260 000 − 70 000 tokens, o
# que mantém o pedido inteiro abaixo do corte de preço dos 272k de input (acima
# dele o pedido paga 2× input e 1,5× output). O schema não aceita mais do que o
# pipeline entrega (regra dos limites): um valor acima seria cortado em silêncio.
ATTACHED_INLINE_MAX_TOKENS = 190_000


class ProfileAttachedInline(BaseModel):
    """tool_limits.attached_inline — documento anexado INTEIRO no contexto (C5)."""
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    # Tecto em tokens da SOMA dos documentos que entram inteiros. Default = o
    # máximo (decisão D2 do Bruno, 25 Set 2026): a guarda por turno do core
    # volta aos pedaços quando o pedido real se aproximaria dos 272k, e é ela
    # que torna seguro o default ser o máximo.
    max_tokens: int = Field(
        default=ATTACHED_INLINE_MAX_TOKENS, ge=1_000, le=ATTACHED_INLINE_MAX_TOKENS,
    )
