"""
presentation.py — que CONTROLO desenhar para cada campo.

Quinta camada do contrato. Responde à pergunta que faz cada UI manter uma
lista de nomes de campos à mão: isto é uma linha de texto ou um parágrafo? um
selector de cor ou uma caixa branca? uma expressão regular ou prosa?

QUASE TUDO SE DERIVA — E O QUE SE DERIVA NÃO SE ESCREVE
────────────────────────────────────────────────────────
O schema já sabe mais do que parece. Medido na v0.1.50, das 359 folhas:
67 booleanos, 56 números, 20 listas fechadas e **57 campos com o `pattern` de
cor hexadecimal** já dizem sozinhos qual é o controlo. Escrevê-los numa tabela
seria criar uma segunda fonte que envelhece — exactamente o problema que esta
camada existe para resolver.

Por isso `control_for()` deriva primeiro e só consulta a tabela para o que o
schema não consegue dizer: **qual das strings é prosa, qual é código, qual é
um endereço**. São 40 e poucas decisões em vez de 359.

O QUE A TABELA NÃO FAZ
──────────────────────
Não descreve o container. Um campo pode ser uma lista de textos longos: o
controlo é `multiline` e a colecção é `list`. Perguntam-se em separado —
`control_for()` e `collection_of()` — porque são duas decisões diferentes e
juntá-las num enum só obrigava a `list_of_multiline`, `map_of_multiline`, e por
aí fora.

Também não valida nada. `url` diz "desenha um campo de endereço"; se o valor
serve ou não é outra conversa, e para as origens do CSP está em
`field_checks.py`.
"""

from functools import lru_cache
from typing import Dict, Optional, Tuple

from genesis_profile_schema.exposure import leaf_shapes, normalise_path

TOGGLE = "toggle"
NUMBER = "number"
SELECT = "select"
COLOUR = "colour"
URL = "url"
EMAIL = "email"
DATE = "date"
DATETIME = "datetime"
CODE = "code"
MULTILINE = "multiline"
TEXT = "text"

CONTROLS: Tuple[str, ...] = (
    TOGGLE, NUMBER, SELECT, COLOUR, URL, EMAIL, DATE, DATETIME, CODE, MULTILINE, TEXT,
)

LIST = "list"
MAP = "map"


# ─────────────────────────────────────────────────────────────────────────────
# O que o schema não consegue dizer
#
# `multiline` — prosa: instruções, avisos, textos que o utilizador final lê.
# `code`      — expressões que se escrevem em monoespaçado e não se corrigem
#               ortograficamente: regex e caminhos de campo.
# `url`/`email`/`date` — o teclado e o validador certos no telemóvel.
#
# Um caminho de mapa aberto ou de lista descreve o controlo de CADA VALOR lá
# dentro (o `personality.tone_instructions` é um mapa cujos valores são
# parágrafos).
# ─────────────────────────────────────────────────────────────────────────────

CONTROL_OVERRIDES: Dict[str, str] = {
    # ── prosa ────────────────────────────────────────────────────────────
    "custom_instructions": MULTILINE,
    "domain.description": MULTILINE,
    "system_prompt_disclaimers": MULTILINE,
    "personality.tone_instructions": MULTILINE,
    "compliance.classification.justification": MULTILINE,
    "voice.greeting": MULTILINE,
    "voice.instructions": MULTILINE,
    "frontend.branding.disclaimer": MULTILINE,
    "frontend.branding.disclaimerI18n": MULTILINE,
    "frontend.aiDisclosure.text": MULTILINE,
    "frontend.aiDisclosure.textI18n": MULTILINE,
    "frontend.welcomeMessage": MULTILINE,
    "frontend.welcomeSubtitle": MULTILINE,
    "frontend.legalNotice": MULTILINE,
    "frontend.widget.greeting": MULTILINE,
    "frontend.insightsPanel.quickInsights.prompt": MULTILINE,
    "frontend.insightsPanel.quickInsights.questions.prompt": MULTILINE,
    "frontend.starterPrompts.prompt": MULTILINE,
    # Dentro do mapa aberto `tools.config` — o texto de prompt de duas tools
    # que o cliente edita (ver as excepções em exposure.py).
    "tools.config.extract_legal_terms.prompt_custom": MULTILINE,
    "tools.config.extract_legal_terms.prompt_preset": MULTILINE,
    "tools.config.generate_boq.prompt_custom": MULTILINE,
    "tools.config.generate_boq.prompt_preset": MULTILINE,

    # ── código ───────────────────────────────────────────────────────────
    "product_identification.patterns": CODE,
    "retrieval.latest_version.year_segment_regex": CODE,
    "retrieval.latest_version.intent_patterns": CODE,
    "contacts.display_name_path": CODE,
    "contacts.attribute_paths": CODE,

    # ── endereços ────────────────────────────────────────────────────────
    "identity.logo_url": URL,
    "frontend.privacyPolicyUrl": URL,
    "frontend.privacyPolicyI18n": URL,
    "frontend.widget.bubble_icon_url": URL,
    "frontend.branding.logoLight": URL,
    "frontend.branding.logoDark": URL,
    "frontend.branding.logoRail": URL,
    "frontend.branding.favicon": URL,
    "frontend.auth.authority": URL,
    "frontend.auth.providers.issuer": URL,
    "frontend.auth.providers.jwks_uri": URL,
    "mcp.servers.url": URL,
    "mcp.servers.auth.authorize_url": URL,
    "mcp.servers.auth.token_url": URL,
    "mcp.servers.auth.revocation_url": URL,
    "compliance.high_risk.oversight_procedure_url": URL,
    "compliance.annex_iv_doc_url": URL,
    "ingest.alerts.email": EMAIL,

    # ── datas ────────────────────────────────────────────────────────────
    # `classified_at` e `annex_iv_generated_at` dizem "ISO datetime" no
    # comentário do schema. Os outros dois NÃO declaram formato: o controlo
    # está inferido do propósito do campo ("re-avaliar anualmente"), e é a
    # única entrada desta tabela que não vem de uma afirmação do contrato.
    "compliance.classification.classified_at": DATETIME,
    "compliance.annex_iv_generated_at": DATETIME,
    "compliance.classification.legal_review_date": DATE,
    "compliance.classification.next_review_due": DATE,
}

# `human_oversight_contact` e `serious_incident_contact` ficam de fora de
# propósito: o schema diz "responsável humano designado", não "email". Um
# controlo de email obrigaria um formato que o contrato não pede.


@lru_cache(maxsize=1)
def _shapes() -> Dict[str, Dict[str, object]]:
    return leaf_shapes()


@lru_cache(maxsize=1)
def _colour_pattern() -> str:
    """O `pattern` que o contrato usa nos campos de cor.

    Vai buscá-lo ao próprio schema em vez de o repetir aqui: escrito à mão,
    bastava o contrato passar a aceitar `#RGB` para esta camada continuar a
    desenhar caixas de texto sem ninguém dar por isso. (E a primeira versão
    disto comparava a string em minúsculas, o que nunca batia certo com
    `[0-9A-Fa-f]` — repetir strings do contrato é assim.)
    """
    from genesis_profile_schema import client_profile_schema as cps

    return getattr(cps, "_HEX_COLOR_REGEX", r"^#[0-9A-Fa-f]{6}$")


def control_for(path: str) -> str:
    """O controlo de UM valor deste campo. Default `text`.

    Ordem: a tabela ganha ao derivado (uma string com prosa continua a ser uma
    string), e o derivado ganha ao default.
    """
    norm = normalise_path(path)
    if not norm:
        return TEXT
    if norm in CONTROL_OVERRIDES:
        return CONTROL_OVERRIDES[norm]

    shape = _shapes().get(norm)
    if shape is None:
        # Caminho dentro de um mapa aberto: herda a decisão do mapa, se houver.
        parts = norm.split(".")
        for i in range(len(parts) - 1, 0, -1):
            ancestor = ".".join(parts[:i])
            if ancestor in CONTROL_OVERRIDES:
                return CONTROL_OVERRIDES[ancestor]
        return TEXT

    if shape.get("enum"):
        return SELECT
    tipo = shape.get("type")
    item = shape.get("items_type")
    efectivo = item if tipo == "array" and item else tipo
    if efectivo == "boolean":
        return TOGGLE
    if efectivo in ("integer", "number"):
        return NUMBER
    pattern = shape.get("pattern")
    if isinstance(pattern, str) and pattern == _colour_pattern():
        return COLOUR
    return TEXT


def collection_of(path: str) -> Optional[str]:
    """`'list'`, `'map'` ou `None` — o container, não o valor."""
    shape = _shapes().get(normalise_path(path))
    if not shape:
        return None
    tipo = shape.get("type")
    if tipo == "array":
        return LIST
    if tipo == "object":
        return MAP
    return None


def orphan_overrides() -> Tuple[str, ...]:
    """Entradas da tabela que já não correspondem a nada.

    Uma entrada é legítima se for folha ou se viver dentro de um mapa aberto —
    as de `tools.config` são o caso.
    """
    from genesis_profile_schema.exposure import open_map_paths

    folhas = set(_shapes())
    mapas = open_map_paths()
    return tuple(
        p for p in CONTROL_OVERRIDES
        if p not in folhas and not any(p.startswith(m + ".") for m in mapas)
    )
