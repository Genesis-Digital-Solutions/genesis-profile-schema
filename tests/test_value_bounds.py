"""
tests/test_value_bounds.py — limites de valor (v0.1.54).

Três casos em que a validação passava e o sistema fazia outra coisa:

  1. `weight: 1e400` → `inf` (o `ge=0.0` não trava infinitos) e `0.0 * inf =
     nan` tornava a ordenação do retrieval arbitrária.
  2. `shareDefaultExpiryDays: 999999` era aceite mas o core sempre cortou em 30
     — o modal oferecia um prazo que o servidor não dava.
  3. `top_k` sem tecto: um zero a mais passava, e no caminho degradado
     (`hybrid`, quando o semantic reranker falha) o `raw_k` segue sem corte.

O que estes testes protegem é a REGRA do docstring da `ProfileRetrieval`:
tectos apanham o zero a mais, não servem para poupar — por isso ficam muito
acima de qualquer uso legítimo (a frota vive em `top_k` 5–35).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genesis_profile_schema.client_profile_schema import (
    ProfileFrontend,
    ProfileRetrieval,
    ProfileRetrievalIndex,
)


# ── 1. weight não pode ser infinito ──────────────────────────────────────────

def test_weight_rejects_infinity():
    """`1e400` em JSON vira `inf` no float do Python — e `0.0 * inf` é `nan`."""
    for bad in (float("inf"), 1e400):
        with pytest.raises(ValidationError):
            ProfileRetrievalIndex(name="idx", weight=bad)


def test_weight_accepts_real_values():
    for ok in (0.0, 1.0, 2.5, 100.0):
        assert ProfileRetrievalIndex(name="idx", weight=ok).weight == ok


# ── 2. share expiry não promete mais do que o core entrega ───────────────────

def test_share_expiry_matches_what_the_core_honours():
    """O core corta em 30 dias (`MAX_EXPIRY_DAYS`). O schema passa a dizê-lo."""
    for ok in (1, 7, 30):
        assert ProfileFrontend(shareDefaultExpiryDays=ok).shareDefaultExpiryDays == ok
    for bad in (31, 90, 999999):
        with pytest.raises(ValidationError):
            ProfileFrontend(shareDefaultExpiryDays=bad)


def test_share_expiry_options_are_bounded_item_by_item():
    """Não basta limitar o comprimento da lista — os itens também mentiam."""
    assert ProfileFrontend(shareExpiryOptionsDays=[7, 30]).shareExpiryOptionsDays == [7, 30]
    for bad in ([7, 30, 90], [999999], [0]):
        with pytest.raises(ValidationError):
            ProfileFrontend(shareExpiryOptionsDays=bad)


def test_fleet_defaults_still_validate():
    """Os 22 perfis vivos estavam todos em 7 / [7,30] quando isto foi posto.
    Se este teste falhar, o tecto passou a partir a frota."""
    fe = ProfileFrontend(shareDefaultExpiryDays=7, shareExpiryOptionsDays=[7, 30])
    assert fe.shareDefaultExpiryDays == 7


# ── 3. top_k: rede para o zero a mais, não limite útil ───────────────────────

def test_top_k_accepts_everything_legitimate():
    """5–35 é a frota; 50 é onde o reranker do Azure satura; 200 é folga."""
    for ok in (1, 5, 20, 35, 50, 200):
        assert ProfileRetrieval(top_k=ok).top_k == ok


def test_top_k_catches_the_extra_zero():
    """35 → 350 e 20 → 200000 são o erro real que isto apanha."""
    for bad in (350, 2000, 200000):
        with pytest.raises(ValidationError):
            ProfileRetrieval(top_k=bad)


def test_top_k_ceiling_is_well_above_the_useful_limit():
    """Guarda contra alguém apertar isto para 'poupar': o tecto tem de ficar
    folgado acima da saturação real (50), senão deixa de ser rede e passa a
    ser política de custo escondida no schema — que é o que a regra proíbe."""
    ceiling = next(
        m.le for m in ProfileRetrieval.model_fields["top_k"].metadata
        if getattr(m, "le", None) is not None
    )
    assert ceiling >= 4 * 50, "o tecto do top_k não é lugar para apertar custo"
