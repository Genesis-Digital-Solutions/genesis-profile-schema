"""
Espaços de valores das línguas — a fonte de verdade do contrato.

Existem TRÊS espaços distintos no perfil, e confundi-los é a armadilha que
este módulo veio fechar. Quem desenha um formulário precisa de saber qual é
qual antes de escolher o controlo:

    language.fallback                 → CANONICAL_NAMES        fechado (57)
    language.allowed                  → LANGUAGE_CODES + "*"   NÃO, por desenho
    language.aliases (chave e valor)  → LANGUAGE_CODES         NÃO, por desenho
    frontend.language.default         → UI_LANGS               fechado (8)
    frontend.language.enabled         → UI_LANGS               fechado (8)

`language.*` é a política de língua do BOT; `frontend.language.*` é o selector
de idioma da INTERFACE. Não são a mesma lista e não se sobrepõem limpamente:
`pt` é um locale de UI válido e NÃO é um código do detector, que fala `pt-PT` e
`pt-BR`. Há um teste a exigir que continuem separados.

"Não fechado por desenho" quer dizer o que diz: a estratégia `auto_detect` é
multilíngua total e `language.allowed` aceita `["*"]`. Estas constantes são o
que se OFERECE numa caixa editável, nunca o que se impõe — nenhuma função
deste pacote recusa um código que aqui não esteja.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# ISO ↔ nome canónico
#
# Veio do `_ISO_TO_CANONICAL` do genai-core (core/agent/language_detector.py),
# que era o único sítio onde este mapa existia — e por isso o backoffice do
# cliente não tinha como validar nem renderizar nenhum dos campos acima.
# A partir da v0.1.51 a fonte é esta e o core importa daqui: o espaço de
# valores de um campo do perfil pertence ao contrato, não ao runtime.
#
# O nome canónico não é decorativo: vai LITERALMENTE como instrução para o
# modelo no bloco de língua do system prompt. Por isso é prosa em inglês e não
# um código, e por isso `language.fallback` é `client_read` — ver exposure.py.
# ─────────────────────────────────────────────────────────────────────────────

ISO_TO_CANONICAL: Dict[str, str] = {
    "pt-PT": "Portuguese (European Portuguese - pt-PT)",
    "pt-BR": "Portuguese (Brazilian - pt-BR)",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "ro": "Romanian",
    "ru": "Russian",
    "uk": "Ukrainian",
    "el": "Greek",
    "tr": "Turkish",
    "ar": "Arabic",
    "he": "Hebrew",
    "fa": "Persian",
    "hi": "Hindi",
    "bn": "Bengali",
    "ja": "Japanese",
    "ko": "Korean",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "cs": "Czech",
    "sk": "Slovak",
    "hu": "Hungarian",
    "bg": "Bulgarian",
    "hr": "Croatian",
    "sr": "Serbian",
    "sl": "Slovenian",
    "et": "Estonian",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "ca": "Catalan",
    "gl": "Galician",
    "eu": "Basque",
    "is": "Icelandic",
    "ga": "Irish",
    "cy": "Welsh",
    "mt": "Maltese",
    "sq": "Albanian",
    "mk": "Macedonian",
    "bs": "Bosnian",
    "hy": "Armenian",
    "ka": "Georgian",
    "az": "Azerbaijani",
    "kk": "Kazakh",
    "uz": "Uzbek",
    "be": "Belarusian",
}

# A inversão só é lossless porque não há dois códigos com o mesmo nome — há um
# teste a garanti-lo, senão uma entrada nova desaparecia daqui em silêncio.
CANONICAL_TO_ISO: Dict[str, str] = {v: k for k, v in ISO_TO_CANONICAL.items()}

#: Códigos para `language.allowed` e para as chaves/valores de `language.aliases`.
LANGUAGE_CODES: Tuple[str, ...] = tuple(sorted(ISO_TO_CANONICAL))

#: Nomes para `language.fallback`. O valor a gravar é a string inteira.
CANONICAL_NAMES: Tuple[str, ...] = tuple(sorted(ISO_TO_CANONICAL.values()))

#: Aceite em `language.allowed` e significa "qualquer língua".
ANY_LANGUAGE = "*"


# ─────────────────────────────────────────────────────────────────────────────
# Locales da interface
#
# Espelha o `UI_LANGS` do fecore (src/app/i18n/strings.ts) — as línguas para as
# quais existem strings de interface traduzidas. Esta lista É fechada: o
# `frontend.language.enabled` chega ao selector do chat SEM filtro, e um código
# que não esteja aqui renderiza uma entrada cujas strings caem para inglês ou
# português. Um código com região (`pt-PT`) degrada em silêncio no `pickLang`
# do client-config.service, que faz procura exacta por chave.
#
# É uma cópia deliberada: o fecore é TypeScript e não há como importá-lo. Quem
# acrescentar uma língua de interface no fecore tem de acrescentar aqui — e o
# `ui_text` tem de ganhar a etiqueta correspondente, senão a opção fica sem
# nome no backoffice.
# ─────────────────────────────────────────────────────────────────────────────

UI_LANGS: Tuple[str, ...] = ("pt", "en", "es", "fr", "de", "it", "nl", "ar")

#: Locale BCP-47 por língua de interface — espelha o `LANG_LOCALES` do fecore.
UI_LANG_LOCALES: Dict[str, str] = {
    "pt": "pt-PT", "en": "en-GB", "es": "es-ES", "fr": "fr-FR",
    "de": "de-DE", "it": "it-IT", "nl": "nl-NL", "ar": "ar-AE",
}

#: Línguas de interface escritas da direita para a esquerda.
RTL_UI_LANGS: Tuple[str, ...] = ("ar",)


# ─────────────────────────────────────────────────────────────────────────────
# Consultas
# ─────────────────────────────────────────────────────────────────────────────

def canonical_for(iso: str) -> Optional[str]:
    """Nome canónico de um código, ou `None` se o código não for conhecido."""
    if not isinstance(iso, str):
        return None
    return ISO_TO_CANONICAL.get(iso.strip())


def iso_for(canonical: str) -> Optional[str]:
    """Código de um nome canónico, ou `None`. Comparação exacta: o nome vai
    para o prompt tal e qual, e um `english` minúsculo não é o mesmo valor."""
    if not isinstance(canonical, str):
        return None
    return CANONICAL_TO_ISO.get(canonical.strip())


def is_known_language_code(value: str) -> bool:
    """O código está no mapa. NÃO é validação: `allowed` aceita desconhecidos
    de propósito. Serve para o backoffice avisar, não para recusar."""
    return canonical_for(value) is not None


def is_known_canonical_name(value: str) -> bool:
    """O nome está no mapa — usar em `language.fallback`, onde um nome de fora
    dá `iso_code` vazio no core."""
    return iso_for(value) is not None


def normalise_ui_lang(value: str) -> str:
    """Reduz um código a uma língua de interface, ou `""`.

    Espelha o `normalizeUiLang` do fecore: minúsculas, corta a região, e só
    devolve o que está em `UI_LANGS`. `"pt-PT"` -> `"pt"`, `"de-CH"` -> `"de"`,
    `"zh-CN"` -> `""` (o fecore não tem strings em chinês).
    """
    if not isinstance(value, str):
        return ""
    base = value.strip().lower().split("-")[0]
    return base if base in UI_LANGS else ""


def is_rtl_ui_lang(value: str) -> bool:
    """A língua de interface escreve-se da direita para a esquerda."""
    return normalise_ui_lang(value) in RTL_UI_LANGS
