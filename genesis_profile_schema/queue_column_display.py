"""
genesis_profile_schema/queue_column_display.py — como se APRESENTAM as colunas
das tabelas de uma fila na /fila (v0.1.184, 27 Nov 2026). Só ecrã: nada disto
muda o que se grava nem o que segue para o ERP.

- `reviewQueues.<fila>.columnPlaceholders` — exemplo de formato nas células
  VAZIAS e editáveis de uma tabela (ex.: «1000 KG» na unidade do preço, «EUR»
  na moeda, «6,5» no preço). Nunca é um valor.
      {"artigos": {"preco_moeda": "EUR",
                   "preco_unidade": {"pt": "1000 KG", "en": "1000 KG"}}}
- `reviewQueues.<fila>.leadColumns` — colunas que ABREM a tabela, por esta
  ordem, quando existem nas linhas (a 1.ª fica fixa no scroll). As outras
  ficam na ordem de sempre. Ausente = a ordem de hoje.
      {"artigos": ["material"]}

O PRODUTOR do contrato é o genai-core (`review_queue_placeholders.
public_column_placeholders`, `review_queue_lead_columns.public_lead_columns`):
valida a forma e passa-a ao fecore em `queue_options[<fila>]`
(`column_placeholders`, `lead_columns`). O core larga em silêncio (só aviso no
log) o que vier partido; aqui as MESMAS regras recusam o perfil ao gravar, com
a razão — nunca cortar em silêncio. Limites iguais aos do core.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Dict, List, Union

from pydantic import AfterValidator

#: O mesmo padrão do core (`_KEY_RE`), só ASCII; nunca uma coluna interna `_…`.
_COL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", re.ASCII)
_LANG_RE = re.compile(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})?", re.ASCII)
#: Tetos do core: acima deles o core cortava sem dizer.
DISPLAY_MAX_TABLES = 5
PLACEHOLDER_MAX_COLS = 30
PLACEHOLDER_MAX_LANGS = 10
#: Um exemplo de formato cabe na célula.
PLACEHOLDER_MAX_TEXT = 40
LEAD_MAX_COLS = 10
#: Controlo e invisíveis (bidi, zero-width, tags, surrogates soltos) — o core tira-os.
_INVISIBLE = ("Cc", "Cf", "Cs", "Zl", "Zp")


def _col(where: str, v: object) -> str:
    if not isinstance(v, str) or not _COL_RE.fullmatch(v):
        raise ValueError(
            f"{where}: nome de coluna/tabela inválido ({str(v)[:40]!r}) — letras, "
            f"algarismos, «.», «_» ou «-», até 64, a começar por letra ou algarismo")
    return v


def _tables(where: str, v: dict) -> None:
    if len(v) > DISPLAY_MAX_TABLES:
        raise ValueError(f"{where}: no máximo {DISPLAY_MAX_TABLES} tabelas "
                         f"(recebidas {len(v)})")
    for t in v:
        _col(where, t)


def _text(where: str, v: str) -> str:
    if any(unicodedata.category(ch) in _INVISIBLE for ch in v):
        raise ValueError(f"{where}: o texto tem caracteres de controlo ou invisíveis")
    s = v.strip()
    if not s:
        raise ValueError(f"{where}: texto vazio")
    if len(s) > PLACEHOLDER_MAX_TEXT:
        raise ValueError(f"{where}: no máximo {PLACEHOLDER_MAX_TEXT} caracteres — é "
                         f"um exemplo de formato, não um texto (recebidos {len(s)})")
    return s


def _check_placeholders(v: Dict[str, Dict[str, Union[str, Dict[str, str]]]]):
    where = "columnPlaceholders"
    _tables(where, v)
    out: Dict[str, Dict[str, Union[str, Dict[str, str]]]] = {}
    for table, cols in v.items():
        if not cols:
            raise ValueError(f"{where}.{table}: sem colunas")
        if len(cols) > PLACEHOLDER_MAX_COLS:
            raise ValueError(f"{where}.{table}: no máximo {PLACEHOLDER_MAX_COLS} "
                             f"colunas (recebidas {len(cols)})")
        good: Dict[str, Union[str, Dict[str, str]]] = {}
        for col, text in cols.items():
            w = f"{where}.{table}.{_col(where, col)}"
            if isinstance(text, str):
                good[col] = _text(w, text)
                continue
            if not text:
                raise ValueError(f"{w}: sem línguas")
            if len(text) > PLACEHOLDER_MAX_LANGS:
                raise ValueError(f"{w}: no máximo {PLACEHOLDER_MAX_LANGS} línguas")
            by_lang: Dict[str, str] = {}
            for lang, t in text.items():
                if not _LANG_RE.fullmatch(lang):
                    raise ValueError(f"{w}: código de língua inválido ({lang[:20]!r}) — "
                                     f"ex.: pt, en, pt-BR")
                by_lang[lang] = _text(f"{w}.{lang}", t)
            good[col] = by_lang
        out[table] = good
    return out


def _check_lead(v: Dict[str, List[str]]):
    where = "leadColumns"
    _tables(where, v)
    for table, cols in v.items():
        if not cols:
            raise ValueError(f"{where}.{table}: lista vazia — retirar a tabela")
        if len(cols) > LEAD_MAX_COLS:
            raise ValueError(f"{where}.{table}: no máximo {LEAD_MAX_COLS} colunas "
                             f"(recebidas {len(cols)})")
        for c in cols:
            _col(f"{where}.{table}", c)
        if len(set(cols)) != len(cols):
            raise ValueError(f"{where}.{table}: coluna repetida")
    return v


QueueColumnPlaceholders = Annotated[
    Dict[str, Dict[str, Union[str, Dict[str, str]]]], AfterValidator(_check_placeholders)]
QueueLeadColumns = Annotated[Dict[str, List[str]], AfterValidator(_check_lead)]
