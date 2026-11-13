"""
digits.py — dígitos de qualquer escrita → ASCII (v0.1.168, 13 Nov 2026).

Em Python o `\\d` sobre `str` casa QUALQUER dígito decimal Unicode (árabe-oriental
`٢٠٢٦`, persa `۲۰۲۶`, devanágari, largura total `２０２６`…), e o `\\d` do
`Field(pattern=)` (motor de regex do pydantic-core) também. O NFKC não converte
os árabe-orientais — são caracteres distintos, não formas de compatibilidade.
Resultado: `٢٠٢٦-٠١-٠١` passava como data; depois ou não batia com `2026-01-01`
(comparações de texto, deduplicação, o editor do Studio), ou rebentava mais à
frente (`date.fromisoformat` recusa-o).

A regra do pacote: as regex de validação usam `[0-9]`, nunca `\\d` (o teste
`test_ascii_digits.py` parte se aparecer um `\\d` novo), e os campos de data/mês
escritos por pessoas NORMALIZAM os dígitos com isto antes de validar — o valor
fica guardado na forma canónica ASCII e um perfil antigo nunca deixa de carregar.

É a mesma conversão de dígitos do `to_ascii_digits` do core
(`core/agent/claim_verification.py`), sem os separadores árabes `٫`/`٬`: aqui
não há números decimais, só datas, meses e números inteiros.
"""

import unicodedata
from typing import Any


def ascii_digits(text: str) -> str:
    """Cada dígito decimal não-ASCII passa ao dígito ASCII com o mesmo valor
    (`٢٠٢٦-٠١-٠١` → `2026-01-01`). O resto fica como está. `isdecimal()` e não
    `isdigit()`: o segundo apanharia `²`, que não é um dígito de um número."""
    if not isinstance(text, str) or text.isascii():
        return text
    return "".join(
        str(unicodedata.decimal(c)) if (not c.isascii() and c.isdecimal()) else c
        for c in text
    )


def ascii_digits_before(value: Any) -> Any:
    """Para `BeforeValidator`: só mexe em texto; o resto segue para a validação
    normal (que o recusa ou aceita como antes)."""
    return ascii_digits(value) if isinstance(value, str) else value
