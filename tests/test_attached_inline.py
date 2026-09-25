"""
tests/test_attached_inline.py — `tool_limits.attached_inline` (v0.1.72, 25 Set
2026; C5 do parecer GPT-6 Astra: documento anexado INTEIRO no contexto).

O que protege: o lever é OFF por omissão (default desligado = prompt de hoje no
core); o tecto default é o MÁXIMO que o core honra (decisão D2: 190 000) e o
schema não aceita mais do que isso — um zero a mais (1 900 000) chumba em vez
de ser cortado em silêncio no core; `extra="allow"` como os irmãos; a
exposição é interna (D6); e o `max_attached_doc_chars` da frota subiu para
800 000 (D3) — nunca desce.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema import exposure as exp
from genesis_profile_schema.attached_inline import (
    ATTACHED_INLINE_MAX_TOKENS,
    ProfileAttachedInline,
)
from genesis_profile_schema.client_profile_schema import (
    ClientProfileSchema,
    ProfileToolLimits,
)


def test_off_por_default_e_tecto_no_maximo():
    c = ProfileAttachedInline()
    assert c.enabled is False
    assert c.max_tokens == 190_000 == ATTACHED_INLINE_MAX_TOKENS


def test_montado_em_tool_limits_e_no_blob_por_default():
    prof = ClientProfileSchema.model_validate({"client_id": "x"})
    assert prof.tool_limits.attached_inline.enabled is False
    blob = prof.to_blob_dict()
    assert blob["tool_limits"]["attached_inline"] == {"enabled": False, "max_tokens": 190_000}


def test_tecto_aceita_os_extremos():
    assert ProfileAttachedInline(max_tokens=1_000).max_tokens == 1_000
    assert ProfileAttachedInline(max_tokens=190_000).max_tokens == 190_000


@pytest.mark.parametrize("valor", [0, 999, 190_001, 1_900_000])
def test_tecto_recusa_fora_do_intervalo(valor):
    with pytest.raises(ValidationError):
        ProfileAttachedInline(max_tokens=valor)


def test_extra_allow():
    c = ProfileAttachedInline.model_validate({"enabled": True, "futuro": 1})
    assert c.enabled is True
    assert c.model_dump().get("futuro") == 1


def test_perfil_antigo_sem_o_bloco_valida_com_defaults():
    tl = ProfileToolLimits.model_validate({"max_attached_doc_chars": 250_000})
    assert tl.attached_inline.enabled is False
    # Um valor explícito do perfil é respeitado (nunca se reescreve o do cliente).
    assert tl.max_attached_doc_chars == 250_000


def test_max_attached_doc_chars_da_frota_subiu_para_800k():
    assert ProfileToolLimits().max_attached_doc_chars == 800_000


def test_exposicao_interna():
    assert exp.exposure_of("tool_limits.attached_inline.enabled") == exp.INTERNAL
    assert exp.exposure_of("tool_limits.attached_inline.max_tokens") == exp.INTERNAL
    assert not exp.is_client_visible("tool_limits.attached_inline.enabled")
