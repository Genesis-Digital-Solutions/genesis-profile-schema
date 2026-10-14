"""v0.1.110 (14 Out 2026) — `voice.transfer_summary_emails`: lista vazia por
omissão (nunca None no blob), escrita pelo cliente, com textos nas duas línguas."""
from genesis_profile_schema.client_profile_schema import ProfileVoice
from genesis_profile_schema.exposure import EXPOSURE
from genesis_profile_schema.ui_text import text_for


def test_default_e_lista_vazia():
    v = ProfileVoice()
    assert v.transfer_summary_emails == []
    assert ProfileVoice(transfer_summary_emails=["a@b.pt"]).transfer_summary_emails == ["a@b.pt"]
    assert "transfer_summary_emails" in v.model_dump()
    # O pedido na fila é opt-in: nada muda a quem já tem voz e fila.
    assert v.transfer_summary_to_queue is False


def test_exposicao_e_textos():
    for field in ("voice.transfer_summary_emails", "voice.transfer_summary_to_queue"):
        assert EXPOSURE[field] == "client_write"
        for loc in ("pt-PT", "en-GB"):
            t = text_for(field, loc)
            assert t and t.get("label") and len(t.get("help") or "") <= 240
