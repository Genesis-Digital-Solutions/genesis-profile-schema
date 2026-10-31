"""Avisos de documentos do GAIBO apagados pela Genesis (v0.1.138)."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from genesis_profile_schema import gaibo_index as gi

SRC = gi.source_file_for("j-abcdefgh", "A RE_MAX.pdf")


def _notice(**kw):
    base = dict(notice_id="gr-abcdefgh12", client_id="remax-v2-dev", environment="dev",
                source_file=SRC, origin_ref="run-abcdefgh", removed_chunks=4, original_removed=True,
                removed_at=datetime(2026, 10, 31, 1, 0, tzinfo=timezone.utc))
    base.update(kw)
    return gi.GenesisRemovalNotice(**base)


def test_aviso_valido_e_caminho():
    n = _notice(reason="pedido do cliente")
    assert n.schema_version == gi.CONTRACT_VERSION and n.environment == "dev"
    assert gi.removal_blob("gr-abcdefgh12") == "genesis-removals/gr-abcdefgh12.json"
    assert gi.REMOVALS_PREFIX == "genesis-removals/"
    assert _notice(environment="prod", origin_ref=None).origin_ref is None


@pytest.mark.parametrize("bad", ["gr-ABC", "pr-abcdefgh12", "gr-abc", "gr-" + "a" * 41, ""])
def test_ids_invalidos(bad):
    assert not gi.is_valid_notice_id(bad)
    with pytest.raises(ValueError):
        gi.removal_blob(bad)
    with pytest.raises(ValidationError):
        _notice(notice_id=bad)


def test_so_documentos_do_gaibo_e_campos_fechados():
    with pytest.raises(ValidationError):
        _notice(source_file="input/Manual.pdf")                # um documento do Studio nunca
    with pytest.raises(ValidationError):
        _notice(environment="staging")
    with pytest.raises(ValidationError):
        _notice(origin_ref="a b")
    with pytest.raises(ValidationError):
        _notice(removed_chunks=-1)
    with pytest.raises(ValidationError):
        _notice(removed_at=datetime(2026, 10, 31))             # sem fuso
    with pytest.raises(ValidationError):
        gi.GenesisRemovalNotice(**{**_notice().model_dump(), "extra": 1})
    with pytest.raises(ValidationError):
        _notice(reason="x" * 301)
