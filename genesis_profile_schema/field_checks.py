"""
field_checks.py — verificações de VALOR que os consumidores aplicam ao escrever.

Deliberadamente FORA do Pydantic. O modelo valida forma; isto valida conteúdo
perigoso, e a diferença importa: o `client_profile_schema` é usado pelo core
para carregar o perfil que serve o bot. Um validador novo a rejeitar um valor
que hoje passa não protege ninguém — impede o perfil de carregar, e um bot que
não arranca é pior do que o problema que se queria resolver.

Por isso estas funções nunca levantam nem rejeitam sozinhas. Devolvem o que é
seguro e o que não é, e quem chama decide:
  - o Studio, ao ESCREVER o cabeçalho, descarta o que não passa e regista;
  - o editor e o backoffice avisam quem está a escrever, antes de gravar;
  - o core continua a carregar tudo, como sempre carregou.

─────────────────────────────────────────────────────────────────────────────
1. Origens que entram no CSP
─────────────────────────────────────────────────────────────────────────────
`frontend.widget.allowed_origins` e `frontend.csp.extra*` são interpoladas
LITERALMENTE numa directiva do Content-Security-Policy quando o Studio escreve
o `staticwebapp.config.json` (creator.py, `_csp_add_sources` e o bloco de
`frame-ancestors`). Um valor com `;` fecha a directiva e abre outra: um único
campo de perfil consegue reescrever o `script-src` da aplicação inteira.

`allowed_origins` é editável pelo cliente, o que torna isto alcançável a partir
do backoffice dele. A defesa é uma ALLOWLIST — uma gramática do que é uma
origem — e não uma lista de caracteres proibidos.

Uma entrada com vários tokens separados por espaços é dividida antes de
validar, em vez de rejeitada em bloco: hoje uma entrada assim funciona por
acidente (aterra no cabeçalho como várias origens) e recusá-la inteira
retiraria a um site a autorização para embeber que ele já tinha.

─────────────────────────────────────────────────────────────────────────────
2. Regex do cliente
─────────────────────────────────────────────────────────────────────────────
`product_identification.patterns` são regex escritas pelo cliente e compiladas
do nosso lado (core/agent/product_identification.py). O core já apanha
`re.error` e ignora a regex má — o que ele NÃO tem é limite de tempo de
execução, por isso uma regex com quantificadores encaixados pode pôr um worker
a girar. `regex_risk()` serve para avisar quem a escreve; o limite de execução
é trabalho do core e não se resolve aqui.
"""

import re
from typing import List, Optional, Tuple

# Rótulo de domínio: letras/dígitos ASCII, hífen e underscore no meio. O
# underscore não é DNS válido mas existe em intranets, e não permite injecção.
# Domínios internacionais entram em punycode (`xn--…`), como o CSP exige.
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9])?"
_DOTTED = rf"(?:\*\.)?{_LABEL}(?:\.{_LABEL})+"
_PORT = r"(?::\d{1,5})?"

# Caminho opcional. É gramática válida de CSP (source com caminho) e o
# `frame-ancestors` ignora-o — recusá-lo tirava a autorização a quem tivesse
# colado um URL completo. Os caracteres perigosos já foram barrados antes.
_PATH = r"(?:/[^\s;'\"<>`\\]*)?"

# COM esquema, um host de rótulo único é legítimo (`https://intranet`).
# SEM esquema, exige-se um ponto — é o que impede `script-src` ou
# `unsafe-inline` de passarem por hosts.
_WITH_SCHEME = re.compile(rf"^https?://(?:{_DOTTED}|{_LABEL}){_PORT}{_PATH}$")
_NO_SCHEME = re.compile(rf"^{_DOTTED}{_PORT}{_PATH}$")

# `localhost:4200` não tem ponto e é legítimo em dev, mesmo sem esquema.
_LOCAL = re.compile(rf"^(?:https?://)?localhost{_PORT}{_PATH}$")

_SEPARATORS = re.compile(r"[\s,]+")


def split_csp_sources(raw: str) -> List[str]:
    """Parte uma entrada em tokens. Vazio se não houver nada aproveitável."""
    if not isinstance(raw, str):
        return []
    return [tok for tok in _SEPARATORS.split(raw.strip()) if tok]


def is_valid_csp_source(token: str) -> bool:
    """Um token é uma origem que se pode pôr num cabeçalho CSP sem o partir.

    Recusa por omissão: palavras-chave entre plicas (`'self'`, `'unsafe-inline'`),
    esquemas soltos (`data:`, `blob:`, `javascript:`), o wildcard nu (`*`), e
    tudo o que traga `;`, plicas ou espaços. O que o cabeçalho precisa de ter
    de fixo é o código do Studio que o põe lá — nunca um campo de perfil.
    """
    if not isinstance(token, str) or not token:
        return False
    if any(ch in token for ch in (";", "'", '"', "\\", "<", ">", "`")):
        return False
    return bool(_WITH_SCHEME.match(token) or _NO_SCHEME.match(token)
                or _LOCAL.match(token))


def sanitise_csp_sources(values) -> Tuple[List[str], List[str]]:
    """`(aceites, recusados)` a partir da lista bruta do perfil.

    Os aceites vêm sem barra final e sem repetições, pela ordem de entrada —
    é essa lista que pode ir para o cabeçalho. Os recusados vão para o log de
    quem chama, para que a rejeição seja visível em vez de silenciosa.
    """
    aceites: List[str] = []
    recusados: List[str] = []
    for value in (values or []):
        tokens = split_csp_sources(value if isinstance(value, str) else "")
        if not tokens:
            # Uma string vazia é uma linha em branco no formulário — não vale
            # a pena reportar. Qualquer outra coisa que não dê tokens (None,
            # números, dicts) é dado com o tipo errado e tem de aparecer no
            # log: engolir isso em silêncio é como não ter verificação.
            if not isinstance(value, str):
                marca = repr(value)
                if marca not in recusados:
                    recusados.append(marca)
            continue
        for token in tokens:
            if is_valid_csp_source(token):
                limpo = token.rstrip("/")
                if limpo not in aceites:
                    aceites.append(limpo)
            elif token not in recusados:
                recusados.append(token)
    return aceites, recusados


# ─────────────────────────────────────────────────────────────────────────────
# Regex do cliente
# ─────────────────────────────────────────────────────────────────────────────

# Quantificador aplicado a um grupo que já tem quantificador lá dentro —
# a forma clássica do backtracking catastrófico: (a+)+, (a*)*, (\d+|x)+
_NESTED_QUANTIFIER = re.compile(r"\([^()]*[*+][^()]*\)\s*[*+]")
_NESTED_ALTERNATION = re.compile(r"\([^()]*\|[^()]*\)\s*[*+]")

# Generoso de propósito: é um aviso, não um limite. Nunca apertar isto para
# "poupar" — a regra da casa é que limites só sobem.
REGEX_LENGTH_WARN = 500


def regex_risk(pattern: str) -> Optional[str]:
    """Motivo pelo qual esta regex é arriscada, ou `None`.

    Heurística, não prova: apanha as formas clássicas de backtracking
    catastrófico e o que não compila. Uma regex que passe aqui pode ainda
    assim ser lenta — a garantia tem de vir de um limite de tempo na execução,
    que vive no core.
    """
    if not isinstance(pattern, str) or not pattern.strip():
        return "padrão vazio"
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"não compila: {exc}"
    if len(pattern) > REGEX_LENGTH_WARN:
        return f"muito longa ({len(pattern)} caracteres) — difícil de rever"
    if _NESTED_QUANTIFIER.search(pattern) or _NESTED_ALTERNATION.search(pattern):
        return ("quantificador sobre grupo já quantificado — pode entrar em "
                "backtracking catastrófico e prender um worker")
    return None


def regex_risks(patterns) -> List[Tuple[str, str]]:
    """`[(padrão, motivo)]` para os que merecem aviso. Lista vazia = tudo bem."""
    saida = []
    for pattern in (patterns or []):
        motivo = regex_risk(pattern if isinstance(pattern, str) else "")
        if motivo:
            saida.append((str(pattern), motivo))
    return saida


# ─────────────────────────────────────────────────────────────────────────────
# Códigos de língua
#
# NÃO há lista fechada, e isso é desenho, não omissão: a estratégia
# `auto_detect` é multilíngua total e `language.allowed` aceita `["*"]`. Um
# `Literal` fecharia um campo que o produto abre de propósito.
#
# Também não se pode validar `language.fallback` com esta função: o default do
# próprio schema é a FRASE "Portuguese (European Portuguese - pt-PT)", porque
# esse campo é instrução para o modelo, não um código. `allowed` e `aliases`
# é que falam em códigos. São dois espaços de valores no mesmo bloco — saber
# qual é qual é metade do trabalho de quem desenha o formulário.
# ─────────────────────────────────────────────────────────────────────────────

_LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|\d{3}))?$")

# Locales para os quais o produto já traz voz configurada de fábrica
# (`voices.by_locale`). São SUGESTÕES para uma caixa de selecção editável —
# nunca um limite. Um cliente pode legitimamente querer uma língua que aqui
# não está.
SUGGESTED_LOCALES: Tuple[str, ...] = ("pt-PT", "pt-BR", "en-GB", "en-US", "es-ES", "fr-FR")


def looks_like_language_tag(value: str) -> bool:
    """Forma de etiqueta BCP-47 (`pt`, `pt-PT`, `zh-Hant-TW`). Não confirma
    que a língua existe — confirma que não é `pt_PT` nem `portugues`."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value or value == "*":
        return False
    return bool(_LANGUAGE_TAG.match(value))


def language_tag_problems(values) -> List[str]:
    """Entradas de uma lista de códigos que não têm forma de etiqueta BCP-47.

    Para `language.allowed` e as chaves/valores de `language.aliases`. O `"*"`
    é legítimo em `allowed` e não é reportado.
    """
    return [
        str(v) for v in (values or [])
        if isinstance(v, str) and v.strip() != "*" and not looks_like_language_tag(v)
    ]
