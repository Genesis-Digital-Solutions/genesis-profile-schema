"""
voice_names.py — os valores de `frontend.ttsVoiceMap` e `voices.by_locale` são
nomes de voz da Azure (v0.1.159, 6 Nov 2026; handoff do GAIBO).

O nome entra em `<voice name="...">` no SSML do core e do fecore. Um valor com
`"` ou `<` injetava markup; o core (`core/speech/ssml.is_valid_voice_name`) e o
fecore (`voice-name.ts`) já o saltam no uso — aqui é o save que o recusa.
Allowlist: locale + nome, com o sufixo HD opcional (`pt-PT-RaquelNeural`,
`zh-CN-shaanxi-XiaoniNeural`, `en-US-Ava:DragonHDLatestNeural`). As vozes HD
são permitidas de propósito (decisão de produto: HD onde existe).
Mesmo padrão nos três sítios — mudar um é mudar os três.
"""
from __future__ import annotations

import re
from typing import Any, Dict

VOICE_NAME_PATTERN = r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,40}){2,4}(?::[A-Za-z0-9][A-Za-z0-9-]{0,39})?$"
VOICE_NAME_MAX = 100
_RE = re.compile(VOICE_NAME_PATTERN)


def is_valid_voice_name(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= VOICE_NAME_MAX and bool(_RE.fullmatch(value))


def check_voice_map(value: Any) -> Any:
    """Recusa um mapa com um valor que não é nome de voz. Vazio fica (= sem voz própria)."""
    if not isinstance(value, dict):
        return value
    bad = [str(k)[:40] for k, v in value.items()
           if not (isinstance(v, str) and (v.strip() == "" or is_valid_voice_name(v.strip())))]
    if bad:
        raise ValueError(
            "nome de voz inválido para " + ", ".join(sorted(bad)[:5])
            + " (esperado um nome de voz da Azure, ex.: pt-PT-RaquelNeural ou en-US-Ava:DragonHDLatestNeural)")
    # Grava sem espaços nas pontas: o fecore compara o valor tal e qual.
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in value.items()}
