"""
genesis_profile_schema/error_summary.py — resumo de um erro de validação SEM os
valores recusados (Finding 62 do core / F-S56 do Studio, 12 Nov 2026).

O `str()` de um `pydantic.ValidationError` traz `input_value=<valor>` de cada
campo. Um validador que o embrulhe noutra mensagem (`f"... {e}"`) leva esses
valores para a `msg` do erro exterior — e daí para respostas HTTP, logs e
traços. Num perfil, os valores podem ser segredos (a config de uma tool, um
token MCP literal). Por isso quem embrulha um erro interno usa este resumo e
`raise ... from None`.
"""

from __future__ import annotations

from pydantic import ValidationError

MAX_SUMMARY_ERRORS = 5


def error_summary_without_values(exc: BaseException) -> str:
    """`loc: msg` dos erros internos (até `MAX_SUMMARY_ERRORS`, e quantos
    ficaram de fora), sem `input`, `ctx` nem `url`.

    Para uma exceção que não seja `ValidationError` devolve só o nome da classe:
    o texto dela pode trazer o valor. A `msg` de um `ValueError` levantado por
    um validador do pacote vai tal como está — esses validadores não ecoam
    valores de configuração (no máximo identificadores: chaves, domínios).
    """
    if not isinstance(exc, ValidationError):
        return type(exc).__name__
    try:
        errors = exc.errors(include_input=False, include_url=False, include_context=False)
    except TypeError:  # pydantic antigo sem estes parâmetros: só se lê loc e msg
        errors = exc.errors()
    parts = []
    for err in errors[:MAX_SUMMARY_ERRORS]:
        loc = ".".join(str(p) for p in err.get("loc") or ()) or "(raiz)"
        parts.append(f"{loc}: {err.get('msg', '')}")
    extra = len(errors) - MAX_SUMMARY_ERRORS
    if extra > 0:
        parts.append(f"(+{extra} erro(s) não mostrado(s))")
    return "; ".join(parts) or type(exc).__name__
