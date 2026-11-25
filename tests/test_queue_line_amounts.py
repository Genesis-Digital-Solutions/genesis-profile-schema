"""reviewQueues.<fila>.lineAmounts (v0.1.179) — as regras do core recusadas ao gravar."""
import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ProfileReviewQueue
from genesis_profile_schema.queue_line_amounts import LINE_AMOUNTS_MAX

SALMON = {"source": "artigos", "target": "preco", "price": "preco_unitario",
          "priceUnit": "preco_unidade", "quantity": "quantidade",
          "quantityUnit": "unidade", "weightTons": "toneladas"}


def _q(entries):
    return ProfileReviewQueue(lineAmounts=entries)


def test_forma_da_salmon_valida():
    q = _q([SALMON])
    assert q.lineAmounts[0].target == "preco"
    assert q.lineAmounts[0].weightTons == "toneladas"


def test_ausente_e_null_sao_nenhum():
    assert ProfileReviewQueue().lineAmounts is None
    assert ProfileReviewQueue(lineAmounts=None).lineAmounts is None


def test_weight_tons_opcional():
    e = dict(SALMON)
    e.pop("weightTons")
    assert _q([e]).lineAmounts[0].weightTons is None


@pytest.mark.parametrize("campo", ["source", "target", "price", "priceUnit",
                                   "quantity", "quantityUnit"])
def test_obrigatorios(campo):
    e = dict(SALMON)
    e.pop(campo)
    with pytest.raises(ValidationError):
        _q([e])


@pytest.mark.parametrize("nome", ["_interno", "", " ", "a" * 65, "preço", "col umn",
                                  "١٢٣", "x;drop"])
def test_nome_de_coluna_invalido(nome):
    with pytest.raises(ValidationError):
        _q([dict(SALMON, target=nome)])


def test_chave_desconhecida_recusada():
    with pytest.raises(ValidationError):
        _q([dict(SALMON, multiplicar="x")])


@pytest.mark.parametrize("lida", ["preco_unitario", "preco_unidade", "quantidade",
                                  "unidade", "toneladas"])
def test_target_nunca_coluna_lida_pela_propria(lida):
    with pytest.raises(ValidationError, match="LIDA"):
        _q([dict(SALMON, target=lida)])


def test_target_nunca_coluna_lida_por_outra_entrada_da_mesma_tabela():
    outra = dict(SALMON, target="valor_extra", price="preco_especial")
    with pytest.raises(ValidationError, match="LIDA"):
        _q([outra, dict(SALMON, target="preco_especial")])


def test_outra_tabela_e_outra_coluna():
    # em `servicos`, «preco_unitario» é só o alvo (lido em `artigos`, não aqui)
    outra = dict(SALMON, source="servicos", target="preco_unitario", price="preco_servico")
    assert len(_q([SALMON, outra]).lineAmounts) == 2


def test_target_repetido_na_mesma_tabela():
    with pytest.raises(ValidationError, match="repete"):
        _q([SALMON, dict(SALMON, price="p2", priceUnit="u2")])


def test_teto_igual_ao_do_core():
    ok = [dict(SALMON, source=f"t{i}") for i in range(LINE_AMOUNTS_MAX)]
    assert len(_q(ok).lineAmounts) == LINE_AMOUNTS_MAX
    with pytest.raises(ValidationError, match="no máximo"):
        _q(ok + [dict(SALMON, source="t9")])


def test_erro_nao_ecoa_valores_longos():
    with pytest.raises(ValidationError) as ei:
        _q([dict(SALMON, target="x" * 5000)])
    assert "x" * 200 not in str(ei.value.errors()[0]["msg"])
