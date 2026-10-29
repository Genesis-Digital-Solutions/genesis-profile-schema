# -*- coding: utf-8 -*-
"""tools.config.search_web — tecto por resposta e leitura de páginas (v0.1.136, 29 Out 2026)."""

import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import ProfileToolSearchWebConfig, ProfileTools


def test_omissoes_sao_as_do_core():
    c = ProfileToolSearchWebConfig()
    assert (c.max_calls_per_turn, c.read_pages, c.max_page_reads_per_turn) == (2, False, 3)


def test_null_vale_o_mesmo_que_ausente():
    c = ProfileToolSearchWebConfig(read_pages=None, max_calls_per_turn=None, max_page_reads_per_turn="")
    assert (c.max_calls_per_turn, c.read_pages, c.max_page_reads_per_turn) == (2, False, 3)


@pytest.mark.parametrize("campo", ["max_calls_per_turn", "max_page_reads_per_turn"])
def test_tectos_com_piso_1(campo):
    with pytest.raises(ValidationError):
        ProfileToolSearchWebConfig(**{campo: 0})
    assert getattr(ProfileToolSearchWebConfig(**{campo: 5}), campo) == 5


def test_o_bloco_gravado_fica_byte_a_byte():
    raw = {"mode": "native", "allowed_domains": ["dgaep.gov.pt"], "read_pages": True}
    t = ProfileTools(enabled=["search_web"], config={"search_web": dict(raw)})
    assert t.config["search_web"] == raw


def test_formato_errado_e_recusado_no_save():
    with pytest.raises(ValidationError):
        ProfileTools(enabled=["search_web"], config={"search_web": {"max_calls_per_turn": "muitas"}})
