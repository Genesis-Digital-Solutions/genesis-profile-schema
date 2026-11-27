"""reviewQueues.<fila>.columnPlaceholders e leadColumns (v0.1.184) — as regras do
core recusadas ao gravar, nunca cortadas em silêncio."""
import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ProfileReviewQueue
from genesis_profile_schema.queue_column_display import (
    DISPLAY_MAX_TABLES, LEAD_MAX_COLS, PLACEHOLDER_MAX_COLS, PLACEHOLDER_MAX_LANGS,
    PLACEHOLDER_MAX_TEXT)

SALMON_PH = {"artigos": {"preco_unitario": "6,5", "preco_moeda": "EUR",
                         "preco_unidade": {"pt": "1000 KG", "en": "1000 KG"}}}
SALMON_LEAD = {"artigos": ["material"]}


def test_formas_da_salmon_validas():
    q = ProfileReviewQueue(columnPlaceholders=SALMON_PH, leadColumns=SALMON_LEAD)
    assert q.columnPlaceholders == SALMON_PH
    assert q.leadColumns == SALMON_LEAD


def test_ausente_e_null_sao_como_hoje():
    q = ProfileReviewQueue()
    assert q.columnPlaceholders is None and q.leadColumns is None
    q = ProfileReviewQueue(columnPlaceholders=None, leadColumns=None)
    assert q.columnPlaceholders is None and q.leadColumns is None


def test_texto_sem_espacos_nas_pontas():
    q = ProfileReviewQueue(columnPlaceholders={"t": {"a": "  EUR  "}})
    assert q.columnPlaceholders == {"t": {"a": "EUR"}}


@pytest.mark.parametrize("ph", [
    {"a b": {"c": "x"}},                       # tabela inválida
    {"t": {"_motivo": "x"}},                   # coluna interna
    {"t": {"a b": "x"}},
    {"t": {"á": "x"}},                         # só ASCII
    {"t": {}},                                 # sem colunas
    {"t": {"a": "   "}},                       # vazio
    {"t": {"a": "x" * (PLACEHOLDER_MAX_TEXT + 1)}},
    {"t": {"a": "E\u200bUR"}},                 # invisível
    {"t": {"a": "E\u202eUR"}},                 # bidi
    {"t": {"a": "EUR\n"}},                     # controlo
    {"t": {"a": 6.5}},                         # tem de ser texto
    {"t": {"a": ["EUR"]}},
    {"t": {"a": {}}},                          # sem línguas
    {"t": {"a": {"PT!": "x"}}},                # língua inválida
    {"t": {"a": {"pt": ""}}},
    {"t": "EUR"},
])
def test_placeholders_partidos_recusados(ph):
    with pytest.raises(ValidationError):
        ProfileReviewQueue(columnPlaceholders=ph)


def test_placeholders_limites():
    tabelas = {f"t{i}": {"a": "x"} for i in range(DISPLAY_MAX_TABLES)}
    ProfileReviewQueue(columnPlaceholders=tabelas)
    with pytest.raises(ValidationError):
        ProfileReviewQueue(columnPlaceholders={**tabelas, "mais": {"a": "x"}})
    cols = {f"c{i}": "x" for i in range(PLACEHOLDER_MAX_COLS + 1)}
    with pytest.raises(ValidationError):
        ProfileReviewQueue(columnPlaceholders={"t": cols})
    langs = {f"l{chr(97 + i)}": "x" for i in range(PLACEHOLDER_MAX_LANGS + 1)}
    with pytest.raises(ValidationError):
        ProfileReviewQueue(columnPlaceholders={"t": {"a": langs}})


@pytest.mark.parametrize("lead", [
    {"t": []},                                 # lista vazia
    {"t": ["material", "material"]},           # repetida
    {"t": ["_x"]},
    {"t": ["a b"]},
    {"t": "material"},                         # tem de ser lista
    {"a b": ["material"]},
    {"t": [f"c{i}" for i in range(LEAD_MAX_COLS + 1)]},
    {f"t{i}": ["a"] for i in range(DISPLAY_MAX_TABLES + 1)},
])
def test_lead_partido_recusado(lead):
    with pytest.raises(ValidationError):
        ProfileReviewQueue(leadColumns=lead)


def test_mensagem_diz_o_caminho():
    with pytest.raises(ValidationError) as e:
        ProfileReviewQueue(columnPlaceholders={"artigos": {"preco_moeda": "x" * 99}})
    assert "columnPlaceholders.artigos.preco_moeda" in str(e.value)
