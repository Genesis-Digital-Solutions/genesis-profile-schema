"""
transfer_target.py — o destino da transferência de chamada (SIP REFER) a partir
do perfil (v0.1.106, 13 Out 2026).

PORQUÊ
──────
`voice.transfer_number` é editável pelo cliente (backoffice) e o core passava
o valor tal como estava para o REFER: `sip:` seguia intacto e o resto virava
`tel:` + o texto cru. Uma conta do backoffice podia desviar as chamadas para um
host SIP externo, e um número com espaços (`912 345 678`) dava um URI inválido.

Decisão do Bruno (13 Out 2026): destinos SIP são SÓ da Genesis. Ficam num campo
interno, `voice.transfer_sip_uri`, que só o Studio escreve; o campo do cliente
aceita só números de telefone (E.164 ou extensão). Quando os dois existem, o
SIP ganha — é encaminhamento decidido por nós.

As regras vivem AQUI para o core (que as aplica ao servir a chamada) e o
Studio/backoffice (que avisam antes de gravar) nunca divergirem. Como em
`field_checks`, nada aqui levanta: devolve-se o destino utilizável (ou "") e o
problema encontrado, e quem chama decide. Um valor mau nunca impede o perfil
de carregar — só deixa a chamada sem transferência.

Defesa em profundidade: um número válido pode ainda assim ser caro (premium,
internacional). Isso só se fecha no SBC (restrições de saída dos REFER).
"""

import re
from typing import Any, Mapping, Optional, Tuple

# Problemas devolvidos (estáveis: o Studio e o backoffice traduzem-nos).
EMPTY = None
SIP_STUDIO_ONLY = "sip_studio_only"      # `sip:` no campo do cliente
INVALID = "invalid"                       # não é número nem extensão
NO_PLUS = "no_plus"                       # 7+ dígitos sem `+`: funciona, é ambíguo
INVALID_SIP = "invalid_sip"               # o campo SIP não é um URI SIP aceite

# Separadores que as pessoas escrevem num número e que o URI não aceita.
_SEPARATORS = re.compile(r"[\s.\-()/]")
# Tudo `re.ASCII`: sem isto o `\d` aceita dígitos árabes/devanágari e o
# IGNORECASE aceita `K` (U+212A) e `ſ` (U+017F) por `k`/`s` — o espelho do
# editor (JS sem flag `u`) recusa-os, e as duas regras têm de bater.
# E.164: `+`, indicativo sem zero à cabeça, 8 a 15 dígitos no total.
_E164 = re.compile(r"^\+[1-9]\d{7,14}$", re.ASCII)
# Extensão curta (2–6) ou número nacional sem indicativo (7–15).
_DIGITS = re.compile(r"^\d{2,15}$", re.ASCII)
_NO_PLUS_MIN = 7

# SIP: utilizador opcional, host DNS ou IPv4, porta opcional, e só os
# parâmetros `transport` e `user` (allowlist — nada de headers `?…`).
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOST = rf"(?:{_LABEL}(?:\.{_LABEL})+|\d{{1,3}}(?:\.\d{{1,3}}){{3}})"
_USER = r"[A-Za-z0-9._~+\-]{1,64}"
_PARAM = r";(?:transport=(?:tls|tcp|udp)|user=phone)"
_SIP = re.compile(rf"^sip:(?:{_USER}@)?(?P<host>{_HOST})(?::(?P<port>\d{{1,5}}))?(?:{_PARAM}){{0,2}}$",
                  re.IGNORECASE | re.ASCII)
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$", re.ASCII)


def phone_target(raw: Any) -> Tuple[str, Optional[str]]:
    """`voice.transfer_number` (campo do cliente) → (`tel:…`, problema).

    "" quando não há destino utilizável. `NO_PLUS` devolve o destino na mesma
    (é o que funciona hoje num SBC nacional), com o aviso."""
    text = str(raw or "").strip()
    if not text:
        return "", EMPTY
    if text[:4].lower() == "sip:":
        return "", SIP_STUDIO_ONLY
    if text[:4].lower() == "tel:":
        text = text[4:]
    number = _SEPARATORS.sub("", text)
    if _E164.match(number):
        return f"tel:{number}", None
    if _DIGITS.match(number):
        return f"tel:{number}", (NO_PLUS if len(number) >= _NO_PLUS_MIN else None)
    return "", INVALID


def sip_target(raw: Any) -> Tuple[str, Optional[str]]:
    """`voice.transfer_sip_uri` (campo interno) → (`sip:…`, problema)."""
    text = str(raw or "").strip()
    if not text:
        return "", EMPTY
    m = _SIP.match(text)
    if not m:
        return "", INVALID_SIP
    host, port = m.group("host"), m.group("port")
    if _IPV4.match(host) and any(int(o) > 255 for o in host.split(".")):
        return "", INVALID_SIP
    if port is not None and not 1 <= int(port) <= 65535:
        return "", INVALID_SIP
    return "sip:" + text[4:], None


def voice_transfer_target(voice: Any) -> Tuple[str, Optional[str], str]:
    """O destino efetivo da secção `voice` do perfil (dict cru ou modelo):
    (uri, problema, origem), origem = "sip" | "number" | "".

    O SIP (Studio) ganha quando é válido. Um SIP inválido é ignorado (com o
    problema) e vale o número do cliente, se houver."""
    def _get(key: str) -> Any:
        if isinstance(voice, Mapping):
            return voice.get(key)
        return getattr(voice, key, None)

    sip, sip_problem = sip_target(_get("transfer_sip_uri"))
    if sip:
        return sip, None, "sip"
    number, problem = phone_target(_get("transfer_number"))
    if number:
        return number, problem or sip_problem, "number"
    return "", problem or sip_problem, ""
